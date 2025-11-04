from django.db import models
import os

class JobDescription(models.Model):
    title = models.CharField(max_length=255)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    file = models.FileField(upload_to='jd_files/', blank=True, null=True)  # Make optional
    jd_text = models.TextField(blank=True)  # Store extracted text instead of file
    all_skills = models.TextField(blank=True)  # All skills in one place
    skill_categories = models.JSONField(default=dict, blank=True)  # Categorized skills
    role_category = models.CharField(max_length=255, blank=True, null=True)
    experience_level = models.CharField(max_length=100, blank=True, null=True)
    key_responsibilities = models.TextField(blank=True)  # Key responsibilities
    qualifications = models.TextField(blank=True)  # Education/certifications
    linkedin_search_string = models.TextField(blank=True)  # LinkedIn boolean search
    linkedin_skills_string = models.TextField(blank=True)  # Optimized skills for LinkedIn
    
    class Meta:
        ordering = ['-uploaded_at']
    
    def __str__(self):
        return f"{self.title} - {self.role_category}"
    
    def delete_file(self):
        '''Delete the physical file from storage'''
        if self.file:
            if os.path.isfile(self.file.path):
                os.remove(self.file.path)
                print(f"✅ Deleted JD file: {self.file.path}")
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Delete file after saving if it exists
        if self.file and self.jd_text:
            self.delete_file()
            self.file = None
            super().save(update_fields=['file'])
    
    def get_all_skills_list(self):
        '''Return all skills as a list'''
        if self.all_skills:
            return [s.strip() for s in self.all_skills.split(',') if s.strip()]
        return []
    
    def get_responsibilities_list(self):
        '''Return responsibilities as a list'''
        if self.key_responsibilities:
            return [r.strip() for r in self.key_responsibilities.split('|') if r.strip()]
        return []
    
    def get_qualifications_list(self):
        '''Return qualifications as a list'''
        if self.qualifications:
            return [q.strip() for q in self.qualifications.split('|') if q.strip()]
        return []
    
    def get_linkedin_skills_list(self):
        '''Return LinkedIn optimized skills as a list'''
        if self.linkedin_skills_string:
            return [s.strip() for s in self.linkedin_skills_string.split(',') if s.strip()]
        return []


class GoogleSheetDatabase(models.Model):
    name = models.CharField(max_length=255)
    sheet_url = models.URLField(max_length=500)
    sheet_id = models.CharField(max_length=255, blank=True)
    added_at = models.DateTimeField(auto_now_add=True)
    last_synced = models.DateTimeField(null=True, blank=True)
    total_candidates = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['-added_at']
    
    def __str__(self):
        return f"{self.name} - {self.total_candidates} candidates"
    
    def extract_sheet_id(self):
        '''Extract Google Sheet ID from URL'''
        import re
        # Pattern: https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit...
        pattern = r'/spreadsheets/d/([a-zA-Z0-9-_]+)'
        match = re.search(pattern, self.sheet_url)
        if match:
            self.sheet_id = match.group(1)
            return self.sheet_id
        return None