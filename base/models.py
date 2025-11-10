from django.db import models
from django.contrib.auth.models import User
from django.core.validators import URLValidator, MinValueValidator, MaxValueValidator
import re
import os

class JobDescription(models.Model):
    title = models.CharField(max_length=200)
    file = models.FileField(upload_to='jds/', blank=True, null=True)
    jd_text = models.TextField(blank=True)
    all_skills = models.TextField(blank=True)
    linkedin_skills_string = models.TextField(blank=True)
    linkedin_search_string = models.TextField(blank=True)
    skill_categories = models.JSONField(default=dict, blank=True)
    role_category = models.CharField(max_length=100, blank=True)
    experience_level = models.CharField(max_length=100, blank=True)
    key_responsibilities = models.TextField(blank=True)
    qualifications = models.TextField(blank=True)
    
    # Security fields
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='job_descriptions')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['created_by', '-created_at']),
            models.Index(fields=['is_active']),
        ]
        permissions = [
            ("can_view_all_jds", "Can view all job descriptions"),
            ("can_delete_any_jd", "Can delete any job description"),
        ]
    
    def __str__(self):
        return f"{self.title} - {self.created_by.username}"
    
    def save(self, *args, **kwargs):
        # Delete old file if it exists and a new file is being uploaded
        if self.pk:
            try:
                old_instance = JobDescription.objects.get(pk=self.pk)
                if old_instance.file and old_instance.file != self.file:
                    if os.path.exists(old_instance.file.path):
                        os.remove(old_instance.file.path)
            except JobDescription.DoesNotExist:
                pass
        
        super().save(*args, **kwargs)
        
        # Delete file after saving (for security)
        # if self.file and os.path.exists(self.file.path):
        #     os.remove(self.file.path)
        #     self.file = None
        #     super().save(update_fields=['file'])
    
    def get_all_skills_list(self):
        return [s.strip() for s in self.all_skills.split(',') if s.strip()]
    
    def get_linkedin_skills_list(self):
        return [s.strip() for s in self.linkedin_skills_string.split(',') if s.strip()]
    
    def get_responsibilities_list(self):
        return [r.strip() for r in self.key_responsibilities.split('|') if r.strip()]
    
    def get_qualifications_list(self):
        return [q.strip() for q in self.qualifications.split('|') if q.strip()]


class GoogleSheetDatabase(models.Model):
    name = models.CharField(max_length=200, help_text="Name for this candidate database")
    sheet_url = models.URLField(
        max_length=500,
        validators=[URLValidator()],
        help_text="Full Google Sheets URL"
    )
    sheet_id = models.CharField(max_length=200, blank=True)
    total_candidates = models.IntegerField(default=0)
    last_synced = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    description = models.TextField(blank=True, help_text="Optional description of this database")
    
    # Security fields
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='google_sheets')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_shared = models.BooleanField(
        default=False,
        help_text="Allow other users to use this sheet for matching"
    )
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['created_by', '-created_at']),
            models.Index(fields=['is_active', 'is_shared']),
        ]
        permissions = [
            ("can_view_all_sheets", "Can view all Google Sheets"),
            ("can_share_sheets", "Can share sheets with other users"),
        ]
    
    def __str__(self):
        return f"{self.name} - {self.created_by.username}"
    
    def extract_sheet_id(self):
        """Extract Google Sheet ID from URL"""
        patterns = [
            r'/spreadsheets/d/([a-zA-Z0-9-_]+)',
            r'key=([a-zA-Z0-9-_]+)',
            r'^([a-zA-Z0-9-_]+)$'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, self.sheet_url)
            if match:
                self.sheet_id = match.group(1)
                return self.sheet_id
        
        return None


class AuditLog(models.Model):
    """Track important actions for security and compliance"""
    ACTION_CHOICES = [
        ('JD_UPLOAD', 'Job Description Upload'),
        ('JD_VIEW', 'Job Description View'),
        ('JD_DELETE', 'Job Description Delete'),
        ('SHEET_ADD', 'Google Sheet Add'),
        ('SHEET_SYNC', 'Google Sheet Sync'),
        ('SHEET_DELETE', 'Google Sheet Delete'),
        ('MATCH_RUN', 'Candidate Match Run'),
        ('FILE_DOWNLOAD', 'File Download'),
        ('LOGIN', 'User Login'),
        ('LOGOUT', 'User Logout'),
        ('PERMISSION_DENIED', 'Permission Denied'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='audit_logs')
    action = models.CharField(max_length=50, choices=ACTION_CHOICES)
    target_model = models.CharField(max_length=100, blank=True)
    target_id = models.IntegerField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    details = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', '-timestamp']),
            models.Index(fields=['action', '-timestamp']),
        ]
    
    def __str__(self):
        return f"{self.user} - {self.action} - {self.timestamp}"