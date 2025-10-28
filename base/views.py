from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .forms import JDUploadForm, CandidateDatabaseUploadForm, CandidateMatchForm
from .models import JobDescription, CandidateDatabase
from .utils import (extract_text_from_file, extract_skills_from_jd, save_jd_to_excel, 
                    generate_linkedin_search_strings, match_candidates_with_jd, 
                    export_matched_candidates)
from datetime import datetime
from django.conf import settings
import json
import pandas as pd

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
                return redirect('upload_jd')
            
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
            jd.save()
            
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
            
            messages.success(request, "Job Description analyzed successfully! LinkedIn search strings generated.")
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
    
    # Get available candidate databases
    candidate_databases = CandidateDatabase.objects.all()
    match_form = CandidateMatchForm()
    
    context = {
        'jd': jd,
        'all_skills': jd.get_all_skills_list(),
        'linkedin_skills': jd.get_linkedin_skills_list(),
        'linkedin_searches': linkedin_searches,
        'skill_categories': jd.skill_categories,
        'responsibilities': jd.get_responsibilities_list(),
        'qualifications': jd.get_qualifications_list(),
        'candidate_databases': candidate_databases,
        'match_form': match_form,
    }
    
    return render(request, 'base/results.html', context)


def upload_candidate_database(request):
    '''Upload candidate database Excel file'''
    if request.method == 'POST':
        form = CandidateDatabaseUploadForm(request.POST, request.FILES)
        
        if form.is_valid():
            candidate_db = form.save(commit=False)
            uploaded_file = request.FILES['file']
            candidate_db.file_name = uploaded_file.name

            # Read Excel directly from uploaded file
            try:
                df = pd.read_excel(uploaded_file)
                candidate_db.total_candidates = len(df)
            except Exception as e:
                print(f"⚠️ Error reading Excel: {e}")
                candidate_db.total_candidates = 0
            
            # Now save the record (this will write file to disk)
            candidate_db.save()
            
            messages.success(
                request,
                f"✅ Candidate database uploaded successfully! {candidate_db.total_candidates} candidates found."
            )
            return redirect('manage_databases')
    else:
        form = CandidateDatabaseUploadForm()
    
    return render(request, 'base/upload_database.html', {'form': form})


def manage_databases(request):
    '''View and manage candidate databases'''
    databases = CandidateDatabase.objects.all()
    return render(request, 'base/manage_databases.html', {'databases': databases})


def match_candidates(request, jd_pk):
    '''Match candidates from database with JD requirements'''
    jd = get_object_or_404(JobDescription, pk=jd_pk)
    
    if request.method == 'POST':
        form = CandidateMatchForm(request.POST)
        
        if form.is_valid():
            candidate_db = form.cleaned_data['candidate_database']
            min_match = form.cleaned_data['min_match_percentage']
            
            # Get required skills from JD
            required_skills = jd.get_all_skills_list()
            
            # Match candidates
            matched_candidates = match_candidates_with_jd(
                candidate_db.file.path,
                required_skills,
                min_match
            )
            
            if matched_candidates:
                # Export to Excel
                output_filename = f"matched_candidates_{jd.title.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
                output_path = settings.MEDIA_ROOT / 'matched_candidates' / output_filename
                output_path.parent.mkdir(parents=True, exist_ok=True)
                
                export_matched_candidates(matched_candidates, output_path)
                
                # Store in session for display
                request.session['matched_candidates'] = matched_candidates[:50]  # Limit to 50 for display
                request.session['output_file'] = str(output_path.relative_to(settings.MEDIA_ROOT))
                
                messages.success(request, f"Found {len(matched_candidates)} matching candidates!")
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
    
    context = {
        'jd': jd,
        'matched_candidates': matched_candidates,
        'output_file': output_file,
        'total_matches': len(matched_candidates),
    }
    
    return render(request, 'base/show_matches.html', context)