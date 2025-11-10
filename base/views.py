from django.http import FileResponse, Http404, HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.views.decorators.http import require_http_methods, require_POST
from django.views.decorators.csrf import csrf_protect
from django.core.exceptions import PermissionDenied
from django.utils.decorators import method_decorator
from django.db.models import Q
from .forms import JDUploadForm, GoogleSheetForm, CandidateMatchForm
from .models import JobDescription, GoogleSheetDatabase
from .utils import (cleanup_old_matched_files, extract_text_from_file, extract_skills_from_jd, save_jd_to_excel, 
                    generate_linkedin_search_strings, match_candidates_from_google_sheet,
                    export_matched_candidates, fetch_google_sheet_data)
from datetime import datetime
from django.conf import settings
from django.utils import timezone
import json
import os
from pathlib import Path
import logging

# Configure logging
logger = logging.getLogger(__name__)

# Constants
ALLOWED_FILE_EXTENSIONS = ['.pdf', '.docx', '.doc', '.txt']
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
MAX_SESSION_CANDIDATES = 100

def validate_file_upload(uploaded_file):
    """Validate uploaded file for security"""
    # Check file extension
    ext = os.path.splitext(uploaded_file.name)[1].lower()
    if ext not in ALLOWED_FILE_EXTENSIONS:
        return False, f"File type not allowed. Allowed types: {', '.join(ALLOWED_FILE_EXTENSIONS)}"
    
    # Check file size
    if uploaded_file.size > MAX_FILE_SIZE:
        return False, f"File size exceeds maximum allowed size of {MAX_FILE_SIZE / (1024*1024)}MB"
    
    return True, None

def check_object_permission(request, obj):
    """Check if user has permission to access object"""
    if hasattr(obj, 'created_by'):
        if obj.created_by != request.user and not request.user.is_staff:
            return False
    return True

@login_required
@csrf_protect
@require_http_methods(["GET", "POST"])
def upload_jd(request):
    """Upload and analyze job description - requires authentication"""
    if request.method == 'POST':
        form = JDUploadForm(request.POST, request.FILES)
        
        if form.is_valid():
            # Validate uploaded file
            uploaded_file = request.FILES.get('file')
            is_valid, error_msg = validate_file_upload(uploaded_file)
            
            if not is_valid:
                messages.error(request, error_msg)
                logger.warning(f"Invalid file upload attempt by user {request.user.id}: {error_msg}")
                return redirect('upload_jd')
            
            jd = form.save(commit=False)
            jd.created_by = request.user
            jd.file = request.FILES['file']# Associate with user
            jd.save()
            
            domain = request.POST.get('domain', '')
            
            # Extract text from uploaded file
            file_path = jd.file.path
            
            try:
                jd_text = extract_text_from_file(file_path)
                
                if not jd_text:
                    messages.error(request, "Could not extract text from the file.")
                    # Delete the uploaded file
                    if os.path.exists(file_path):
                        os.remove(file_path)
                    jd.delete()
                    logger.error(f"Text extraction failed for JD {jd.id} by user {request.user.id}")
                    return redirect('upload_jd')
                
                # Store extracted text in database
                jd.jd_text = jd_text
                
                # Extract comprehensive skills using OpenAI
                result = extract_skills_from_jd(jd_text, domain)
                
                # Get LinkedIn optimized skills
                linkedin_skills = result.get('linkedin_optimized_skills', result.get('all_skills', [])[:10])
                
                # Generate LinkedIn search strings
                search_strings = generate_linkedin_search_strings(
                    linkedin_skills,
                    jd.title,
                    result.get('experience_level', 'Mid Level')
                )
                
                # Update model with comprehensive data
                jd.all_skills = ", ".join(result.get('all_skills', []))
                jd.linkedin_skills_string = ", ".join(linkedin_skills)
                jd.linkedin_search_string = json.dumps(search_strings)
                jd.skill_categories = result.get('skill_categories', {})
                jd.role_category = result.get('role_category', 'Unknown')
                jd.experience_level = result.get('experience_level', 'Unknown')
                jd.key_responsibilities = " | ".join(result.get('key_responsibilities', []))
                jd.qualifications = " | ".join(result.get('qualifications', [])) if isinstance(result.get('qualifications'), list) else result.get('qualifications', '')
                jd.save()  # This will trigger file deletion via model's save() method
                
                # Save to Excel with comprehensive data
                excel_data = {
                    'Job Title': jd.title,
                    'All Skills Required': jd.all_skills,
                    'LinkedIn Search Skills': jd.linkedin_skills_string,
                    'LinkedIn Boolean Search': search_strings.get('basic_and', ''),
                    'Role Category': jd.role_category,
                    'Experience Level': jd.experience_level,
                    'Key Responsibilities': jd.key_responsibilities,
                    'Qualifications': jd.qualifications,
                    'Date Uploaded': datetime.now().strftime('%Y-%m-%d'),
                    'Uploaded By': request.user.username
                }
                save_jd_to_excel(excel_data)
                
                logger.info(f"JD {jd.id} successfully analyzed by user {request.user.id}")
                messages.success(request, "Job Description analyzed successfully! Original file deleted for security.")
                return redirect('results', pk=jd.pk)
                
            except Exception as e:
                logger.error(f"Error processing JD upload by user {request.user.id}: {str(e)}")
                messages.error(request, "An error occurred while processing the file. Please try again.")
                if os.path.exists(file_path):
                    os.remove(file_path)
                jd.delete()
                return redirect('upload_jd')
    else:
        form = JDUploadForm()
    
    # Show only user's JDs (staff can see all)
    if request.user.is_staff:
        recent_jds = JobDescription.objects.all()[:10]
    else:
        recent_jds = JobDescription.objects.filter(created_by=request.user)[:10]
    
    return render(request, 'base/upload.html', {'form': form, 'recent_jds': recent_jds})

@login_required
@require_http_methods(["GET"])
def results(request, pk):
    """View job description results - requires authentication and ownership"""
    jd = get_object_or_404(JobDescription, pk=pk)
    
    # Check permission
    if not check_object_permission(request, jd):
        logger.warning(f"Unauthorized access attempt to JD {pk} by user {request.user.id}")
        raise PermissionDenied("You don't have permission to view this job description.")
    
    # Parse LinkedIn search strings
    linkedin_searches = {}
    if jd.linkedin_search_string:
        try:
            linkedin_searches = json.loads(jd.linkedin_search_string)
        except json.JSONDecodeError:
            linkedin_searches = {}
            logger.error(f"Failed to parse LinkedIn search strings for JD {pk}")
    
    # Get available Google Sheet databases (user's own or shared)
    if request.user.is_staff:
        google_sheets = GoogleSheetDatabase.objects.filter(is_active=True)
    else:
        google_sheets = GoogleSheetDatabase.objects.filter(
            Q(created_by=request.user) | Q(is_shared=True),
            is_active=True
        )
    
    match_form = CandidateMatchForm()
    match_form.fields['google_sheet'].queryset = google_sheets
    
    context = {
        'jd': jd,
        'all_skills': jd.get_all_skills_list(),
        'linkedin_skills': jd.get_linkedin_skills_list(),
        'linkedin_searches': linkedin_searches,
        'skill_categories': jd.skill_categories,
        'responsibilities': jd.get_responsibilities_list(),
        'qualifications': jd.get_qualifications_list(),
        'google_sheets': google_sheets,
        'match_form': match_form,
    }
    
    return render(request, 'base/results.html', context)

@login_required
@csrf_protect
@require_http_methods(["GET", "POST"])
def add_google_sheet(request):
    """Add a new Google Sheet database - requires authentication"""
    if request.method == 'POST':
        form = GoogleSheetForm(request.POST)
        
        if form.is_valid():
            sheet_db = form.save(commit=False)
            sheet_db.created_by = request.user  # Associate with user
            
            # Extract sheet ID from URL
            sheet_id = sheet_db.extract_sheet_id()
            
            if not sheet_id:
                messages.error(request, "Invalid Google Sheets URL. Please check and try again.")
                logger.warning(f"Invalid Google Sheet URL provided by user {request.user.id}")
                return render(request, 'base/add_google_sheet.html', {'form': form})
            
            # Try to fetch data to validate access
            try:
                df = fetch_google_sheet_data(sheet_id)
                sheet_db.total_candidates = len(df)
                sheet_db.last_synced = timezone.now()
                sheet_db.save()
                
                logger.info(f"Google Sheet {sheet_db.id} added successfully by user {request.user.id}")
                messages.success(request, f"Google Sheet added successfully! {sheet_db.total_candidates} candidates found.")
                return redirect('manage_google_sheets')
            
            except Exception as e:
                logger.error(f"Failed to access Google Sheet by user {request.user.id}: {str(e)}")
                messages.error(request, f"Could not access Google Sheet. Error: {str(e)}")
                messages.info(request, "Make sure the sheet is shared with your service account email.")
                return render(request, 'base/add_google_sheet.html', {'form': form})
    else:
        form = GoogleSheetForm()
    
    return render(request, 'base/add_google_sheet.html', {'form': form})

@login_required
@require_http_methods(["GET"])
def manage_google_sheets(request):
    """View and manage Google Sheet databases - requires authentication"""
    # Show only user's sheets (staff can see all)
    if request.user.is_staff:
        sheets = GoogleSheetDatabase.objects.all()
    else:
        sheets = GoogleSheetDatabase.objects.filter(created_by=request.user)
    
    return render(request, 'base/manage_google_sheets.html', {'sheets': sheets})

@login_required
@require_POST
@csrf_protect
def sync_google_sheet(request, sheet_pk):
    """Sync/refresh candidate count from Google Sheet - requires authentication and ownership"""
    sheet_db = get_object_or_404(GoogleSheetDatabase, pk=sheet_pk)
    
    # Check permission
    if not check_object_permission(request, sheet_db):
        logger.warning(f"Unauthorized sync attempt for sheet {sheet_pk} by user {request.user.id}")
        raise PermissionDenied("You don't have permission to sync this sheet.")
    
    try:
        df = fetch_google_sheet_data(sheet_db.sheet_id)
        sheet_db.total_candidates = len(df)
        sheet_db.last_synced = timezone.now()
        sheet_db.save()
        
        logger.info(f"Sheet {sheet_pk} synced successfully by user {request.user.id}")
        messages.success(request, f"Synced successfully! {sheet_db.total_candidates} candidates found.")
    except Exception as e:
        logger.error(f"Sync failed for sheet {sheet_pk} by user {request.user.id}: {str(e)}")
        messages.error(request, f"Sync failed: {str(e)}")
    
    return redirect('manage_google_sheets')

@login_required
@require_POST
@csrf_protect
def match_candidates(request, jd_pk):
    """Match candidates from Google Sheet with JD requirements - requires authentication and ownership"""
    jd = get_object_or_404(JobDescription, pk=jd_pk)
    
    # Check permission
    if not check_object_permission(request, jd):
        logger.warning(f"Unauthorized match attempt for JD {jd_pk} by user {request.user.id}")
        raise PermissionDenied("You don't have permission to match candidates for this job description.")
    
    form = CandidateMatchForm(request.POST)
    
    if form.is_valid():
        google_sheet = form.cleaned_data['google_sheet']
        min_match = form.cleaned_data['min_match_percentage']
        
        # Check permission for Google Sheet
        if not check_object_permission(request, google_sheet) and not google_sheet.is_shared:
            logger.warning(f"Unauthorized access to sheet {google_sheet.id} by user {request.user.id}")
            raise PermissionDenied("You don't have permission to use this Google Sheet.")
        
        try:
            # Get required skills from JD
            required_skills = jd.get_all_skills_list()
            
            # Match candidates from Google Sheet
            matched_candidates = match_candidates_from_google_sheet(
                google_sheet.sheet_id,
                required_skills,
                min_match
            )
            
            if matched_candidates:
                # Export to Excel (will be deleted after download)
                output_filename = f"matched_candidates_{jd.title.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
                output_path = Path(settings.MEDIA_ROOT) / 'matched_candidates' / output_filename
                output_path.parent.mkdir(parents=True, exist_ok=True)
                
                export_matched_candidates(matched_candidates, output_path)
                
                # Store in session for display (limit to essential data)
                session_candidates = []
                for candidate in matched_candidates[:MAX_SESSION_CANDIDATES]:
                    session_candidates.append({
                        'name': candidate['name'],
                        'email': candidate['email'],
                        'contact': candidate['contact'],
                        'designation': candidate['designation'],
                        'current_company': candidate['current_company'],
                        'experience': candidate['experience'],
                        'location': candidate['location'],
                        'linkedin': candidate['linkedin'],
                        'match_percentage': candidate['match_percentage'],
                        'matched_skills_count': candidate['matched_skills_count'],
                        'total_required_skills': candidate['total_required_skills'],
                        'matched_skills': candidate['matched_skills'][:10],
                        'cv_link': candidate['cv_link'],
                    })
                
                request.session['matched_candidates'] = session_candidates
                request.session['output_file'] = str(output_path.relative_to(settings.MEDIA_ROOT))
                request.session['sheet_name'] = google_sheet.name
                request.session['total_matches'] = len(matched_candidates)
                request.session['jd_id'] = jd.pk  # Store JD ID for verification
                
                # Cleanup old matched files (older than 1 day)
                cleanup_old_matched_files(days=1)
                
                logger.info(f"Found {len(matched_candidates)} matches for JD {jd_pk} by user {request.user.id}")
                messages.success(request, f"Found {len(matched_candidates)} matching candidates from {google_sheet.name}!")
                return redirect('show_matches', jd_pk=jd.pk)
            else:
                messages.warning(request, "No candidates found matching the criteria. Try lowering the match percentage.")
                return redirect('results', pk=jd.pk)
                
        except Exception as e:
            logger.error(f"Error matching candidates for JD {jd_pk} by user {request.user.id}: {str(e)}")
            messages.error(request, f"An error occurred while matching candidates: {str(e)}")
            return redirect('results', pk=jd.pk)
    
    return redirect('results', pk=jd.pk)

@login_required
@require_http_methods(["GET"])
def show_matches(request, jd_pk):
    """Display matched candidates - requires authentication and ownership"""
    jd = get_object_or_404(JobDescription, pk=jd_pk)
    
    # Check permission
    if not check_object_permission(request, jd):
        logger.warning(f"Unauthorized access to matches for JD {jd_pk} by user {request.user.id}")
        raise PermissionDenied("You don't have permission to view these matches.")
    
    # Verify session data belongs to this JD
    session_jd_id = request.session.get('jd_id')
    if session_jd_id != jd_pk:
        logger.warning(f"Session JD mismatch for user {request.user.id}")
        messages.error(request, "Invalid session data. Please run the match again.")
        return redirect('results', pk=jd_pk)
    
    matched_candidates = request.session.get('matched_candidates', [])
    output_file = request.session.get('output_file', '')
    sheet_name = request.session.get('sheet_name', 'Google Sheet')
    total_matches = request.session.get('total_matches', len(matched_candidates))
    
    context = {
        'jd': jd,
        'matched_candidates': matched_candidates,
        'output_file': output_file,
        'sheet_name': sheet_name,
        'total_matches': total_matches,
    }
    
    return render(request, 'base/show_matches.html', context)

@login_required
@require_http_methods(["GET"])
def download_matched_file(request, jd_pk):
    """Download matched candidates file - requires authentication and ownership"""
    jd = get_object_or_404(JobDescription, pk=jd_pk)
    
    # Check permission
    if not check_object_permission(request, jd):
        logger.warning(f"Unauthorized download attempt for JD {jd_pk} by user {request.user.id}")
        raise PermissionDenied("You don't have permission to download this file.")
    
    # Verify session data belongs to this JD
    session_jd_id = request.session.get('jd_id')
    if session_jd_id != jd_pk:
        logger.warning(f"Session JD mismatch for download by user {request.user.id}")
        raise Http404("File not found or session expired")
    
    output_file = request.session.get('output_file', '')
    
    if not output_file:
        raise Http404("File not found")
    
    file_path = Path(settings.MEDIA_ROOT) / output_file
    
    # Validate file path to prevent directory traversal
    try:
        file_path = file_path.resolve()
        media_root = Path(settings.MEDIA_ROOT).resolve()
        if not str(file_path).startswith(str(media_root)):
            logger.error(f"Directory traversal attempt by user {request.user.id}: {file_path}")
            raise PermissionDenied("Invalid file path")
    except Exception as e:
        logger.error(f"File path validation error: {str(e)}")
        raise Http404("Invalid file path")
    
    if not file_path.exists():
        logger.warning(f"File not found for download: {file_path}")
        raise Http404("File not found")
    
    try:
        # Read file into memory
        with open(file_path, 'rb') as f:
            file_data = f.read()
        
        # Delete immediately
        os.remove(file_path)
        
        # Serve from memory
        from io import BytesIO
        response = FileResponse(
            BytesIO(file_data),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="{file_path.name}"'
        
        # Clear session
        request.session.pop('matched_candidates', None)
        request.session.pop('output_file', None)
        request.session.pop('jd_id', None)
        
        logger.info(f"File downloaded successfully by user {request.user.id} for JD {jd_pk}")
        return response
    
    except Exception as e:
        logger.error(f"Download error for user {request.user.id}: {str(e)}")
        messages.error(request, f"Error: {str(e)}")
        return redirect('show_matches', jd_pk=jd_pk)