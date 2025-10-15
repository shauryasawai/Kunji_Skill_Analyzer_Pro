from django.shortcuts import render, redirect
from django.contrib import messages
from .forms import JDUploadForm
from .models import JobDescription
from .utils import extract_text_from_file, extract_skills_from_jd, save_to_excel
from datetime import datetime

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
            
            # Update model with comprehensive data
            jd.all_skills = ", ".join(result.get('all_skills', []))
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
        'skill_categories': jd.skill_categories,
        'responsibilities': jd.get_responsibilities_list(),
        'qualifications': jd.get_qualifications_list(),
    }
    
    return render(request, 'base/results.html', context)