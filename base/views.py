from django.shortcuts import render, redirect
from django.contrib import messages
from .forms import JDUploadForm
from .models import JobDescription
from .utils import extract_text_from_file, extract_skills_from_jd, save_to_excel, generate_linkedin_search_strings
from datetime import datetime
import json

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
            jd.skill_categories = result.get('skill_categories', {})
            jd.role_category = result.get('role_category', 'Unknown')
            jd.experience_level = result.get('experience_level', 'Unknown')
            jd.key_responsibilities = " | ".join(result.get('key_responsibilities', []))
            jd.qualifications = " | ".join(result.get('qualifications', [])) if isinstance(result.get('qualifications'), list) else result.get('qualifications', '')
            jd.linkedin_skills_string = ", ".join(linkedin_skills)
            jd.linkedin_search_string = json.dumps(search_strings)
            jd.save()
            
            # Save to Excel with comprehensive data
            excel_data = {
                'Job Title': jd.title,
                'All Skills Required': jd.all_skills,
                'LinkedIn Search Skills': jd.linkedin_skills_string,  # NEW
                'LinkedIn Boolean Search': search_strings.get('basic_and', ''),  # NEW
                'Role Category': jd.role_category,
                'Experience Level': jd.experience_level,
                'Key Responsibilities': jd.key_responsibilities,
                'Qualifications': jd.qualifications,
                'Date Uploaded': datetime.now().strftime('%Y-%m-%d')
            }
            save_to_excel(excel_data)
            
            messages.success(request, "Job Description analyzed successfully! All skills extracted.")
            return redirect('results', pk=jd.pk)
    else:
        form = JDUploadForm()
    
    recent_jds = JobDescription.objects.all()[:10]
    return render(request, 'base/upload.html', {'form': form, 'recent_jds': recent_jds})

def results(request, pk):
    jd = JobDescription.objects.get(pk=pk)
    
    context = {
        'jd': jd,
        'all_skills': jd.get_all_skills_list(),
        'linkedin_skills': jd.get_linkedin_skills_list(),  # NEW
        'linkedin_searches': json.loads(jd.linkedin_search_string),
        'skill_categories': jd.skill_categories,
        'responsibilities': jd.get_responsibilities_list(),
        'qualifications': jd.get_qualifications_list(),
    }
    
    return render(request, 'base/results.html', context)