from django.http import FileResponse, Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .forms import JDUploadForm, GoogleSheetForm, CandidateMatchForm
from .models import JobDescription, GoogleSheetDatabase
from .utils import (cleanup_old_matched_files, delete_file_after_delay, extract_text_from_file, extract_skills_from_jd, save_jd_to_excel, 
                    generate_linkedin_search_strings, match_candidates_from_google_sheet,
                    export_matched_candidates, fetch_google_sheet_data)
from datetime import datetime
from django.conf import settings
from django.utils import timezone
import json
import os
from pathlib import Path

def upload_jd(request):
    if request.method == 'POST':
        form = JDUploadForm(request.POST, request.FILES)
        
        if form.is_valid():
            jd = form.save()
            domain = request.POST.get('domain', '')
            
            # Extract text from uploaded file
            file_path = jd.file.path
            jd_text = extract_text_from_file(file_path)
            
            if not jd_text:
                messages.error(request, "Could not extract text from the file.")
                # Delete the uploaded file
                if os.path.exists(file_path):
                    os.remove(file_path)
                jd.delete()
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
                'Date Uploaded': datetime.now().strftime('%Y-%m-%d')
            }
            save_jd_to_excel(excel_data)
            
            messages.success(request, "Job Description analyzed successfully! Original file deleted for security.")
            return redirect('results', pk=jd.pk)
    else:
        form = JDUploadForm()
    
    recent_jds = JobDescription.objects.all()[:10]
    return render(request, 'base/upload.html', {'form': form, 'recent_jds': recent_jds})

def results(request, pk):
    jd = JobDescription.objects.get(pk=pk)
    
    # Parse LinkedIn search strings
    linkedin_searches = {}
    if jd.linkedin_search_string:
        try:
            linkedin_searches = json.loads(jd.linkedin_search_string)
        except:
            linkedin_searches = {}
    
    # Get available Google Sheet databases
    google_sheets = GoogleSheetDatabase.objects.filter(is_active=True)
    match_form = CandidateMatchForm()
    
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


def add_google_sheet(request):
    '''Add a new Google Sheet database'''
    if request.method == 'POST':
        form = GoogleSheetForm(request.POST)
        
        if form.is_valid():
            sheet_db = form.save(commit=False)
            
            # Extract sheet ID from URL
            sheet_id = sheet_db.extract_sheet_id()
            
            if not sheet_id:
                messages.error(request, "Invalid Google Sheets URL. Please check and try again.")
                return render(request, 'base/add_google_sheet.html', {'form': form})
            
            # Try to fetch data to validate access
            try:
                df = fetch_google_sheet_data(sheet_id)
                sheet_db.total_candidates = len(df)
                sheet_db.last_synced = timezone.now()
                sheet_db.save()
                
                messages.success(request, f"Google Sheet added successfully! {sheet_db.total_candidates} candidates found.")
                return redirect('manage_google_sheets')
            
            except Exception as e:
                messages.error(request, f"Could not access Google Sheet. Error: {str(e)}")
                messages.info(request, "Make sure the sheet is shared with your service account email.")
                return render(request, 'base/add_google_sheet.html', {'form': form})
    else:
        form = GoogleSheetForm()
    
    return render(request, 'base/add_google_sheet.html', {'form': form})


def manage_google_sheets(request):
    '''View and manage Google Sheet databases'''
    sheets = GoogleSheetDatabase.objects.all()
    return render(request, 'base/manage_google_sheets.html', {'sheets': sheets})


def sync_google_sheet(request, sheet_pk):
    '''Sync/refresh candidate count from Google Sheet'''
    sheet_db = get_object_or_404(GoogleSheetDatabase, pk=sheet_pk)
    
    try:
        df = fetch_google_sheet_data(sheet_db.sheet_id)
        sheet_db.total_candidates = len(df)
        sheet_db.last_synced = timezone.now()
        sheet_db.save()
        
        messages.success(request, f"Synced successfully! {sheet_db.total_candidates} candidates found.")
    except Exception as e:
        messages.error(request, f"Sync failed: {str(e)}")
    
    return redirect('manage_google_sheets')


def match_candidates(request, jd_pk):
    '''Match candidates from Google Sheet with JD requirements'''
    jd = get_object_or_404(JobDescription, pk=jd_pk)
    
    if request.method == 'POST':
        form = CandidateMatchForm(request.POST)
        
        if form.is_valid():
            google_sheet = form.cleaned_data['google_sheet']
            min_match = form.cleaned_data['min_match_percentage']
            
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
                for candidate in matched_candidates[:50]:
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
                
                # Cleanup old matched files (older than 1 day)
                cleanup_old_matched_files(days=1)
                
                messages.success(request, f"Found {len(matched_candidates)} matching candidates from {google_sheet.name}!")
                return redirect('show_matches', jd_pk=jd.pk)
            else:
                messages.warning(request, "No candidates found matching the criteria. Try lowering the match percentage.")
                return redirect('results', pk=jd.pk)
    
    return redirect('results', pk=jd.pk)


def show_matches(request, jd_pk):
    '''Display matched candidates'''
    jd = get_object_or_404(JobDescription, pk=jd_pk)
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

def download_matched_file(request, jd_pk):
    output_file = request.session.get('output_file', '')
    
    if not output_file:
        raise Http404("File not found")
    
    file_path = settings.MEDIA_ROOT / output_file
    
    if not file_path.exists():
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
        
        return response
    
    except Exception as e:
        messages.error(request, f"Error: {str(e)}")
        return redirect('show_matches', jd_pk=jd_pk)