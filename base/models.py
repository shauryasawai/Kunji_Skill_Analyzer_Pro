from django.db import models

class JobDescription(models.Model):
    title = models.CharField(max_length=255)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    file = models.FileField(upload_to='jd_files/')
    all_skills = models.TextField(blank=True)  # All skills in one place
    skill_categories = models.JSONField(default=dict, blank=True)  # Categorized skills
    role_category = models.CharField(max_length=255, blank=True, null=True)
    experience_level = models.CharField(max_length=100, blank=True, null=True)
    key_responsibilities = models.TextField(blank=True)  # Key responsibilities
    qualifications = models.TextField(blank=True)  # Education/certifications
    
    class Meta:
        ordering = ['-uploaded_at']
    
    def __str__(self):
        return f"{self.title} - {self.role_category}"
    
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