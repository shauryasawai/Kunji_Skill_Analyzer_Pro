from django.contrib import admin
from .models import JobDescription

@admin.register(JobDescription)
class JobDescriptionAdmin(admin.ModelAdmin):
    list_display = ['title', 'role_category', 'experience_level', 'uploaded_at']
    list_filter = ['role_category', 'experience_level']
    search_fields = ['title', 'primary_skills', 'secondary_skills']