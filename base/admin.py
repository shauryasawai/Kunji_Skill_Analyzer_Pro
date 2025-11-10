from django.contrib import admin
from django.contrib.auth.models import User, Group
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from django.urls import reverse
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta
from .models import JobDescription, GoogleSheetDatabase, AuditLog
import json


class JobDescriptionAdmin(admin.ModelAdmin):
    list_display = [
        'title', 
        'role_category', 
        'experience_level', 
        'created_by_link',
        'skills_count',
        'created_at',
        'is_active_badge'
    ]
    
    list_filter = [
        'role_category',
        'experience_level',
        'is_active',
        'created_at',
        'created_by'
    ]
    
    search_fields = [
        'title',
        'all_skills',
        'linkedin_skills_string',
        'key_responsibilities',
        'created_by__username',
        'created_by__email'
    ]
    
    readonly_fields = [
        'created_by',
        'created_at',
        'updated_at',
        'jd_text_preview',
        'linkedin_search_preview',
        'skill_categories_formatted'
    ]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'is_active', 'created_by', 'created_at', 'updated_at')
        }),
        ('Classification', {
            'fields': ('role_category', 'experience_level'),
            'classes': ('collapse',)
        }),
        ('Skills', {
            'fields': ('all_skills', 'linkedin_skills_string', 'skill_categories_formatted')
        }),
        ('Job Details', {
            'fields': ('key_responsibilities', 'qualifications', 'jd_text_preview'),
            'classes': ('collapse',)
        }),
        ('LinkedIn Search', {
            'fields': ('linkedin_search_preview',),
            'classes': ('collapse',)
        }),
    )
    
    date_hierarchy = 'created_at'
    actions = ['activate_jds', 'deactivate_jds', 'export_to_csv']
    list_per_page = 25
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(created_by=request.user)
    
    def save_model(self, request, obj, form, change):
        if not change:  # If creating new object
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
    
    def created_by_link(self, obj):
        url = reverse('admin:auth_user_change', args=[obj.created_by.id])
        return format_html('<a href="{}">{}</a>', url, obj.created_by.username)
    created_by_link.short_description = 'Created By'
    
    def skills_count(self, obj):
        skills = obj.get_all_skills_list()
        return f"{len(skills)} skills"
    skills_count.short_description = 'Skills Count'
    
    def is_active_badge(self, obj):
        if obj.is_active:
            return format_html('<span style="color: green;">●</span> Active')
        return format_html('<span style="color: red;">●</span> Inactive')
    is_active_badge.short_description = 'Status'
    
    def jd_text_preview(self, obj):
        if obj.jd_text:
            preview = obj.jd_text[:500] + '...' if len(obj.jd_text) > 500 else obj.jd_text
            return format_html('<div style="max-height: 200px; overflow-y: auto;">{}</div>', preview)
        return 'No text available'
    jd_text_preview.short_description = 'JD Text Preview'
    
    def linkedin_search_preview(self, obj):
        if obj.linkedin_search_string:
            try:
                searches = json.loads(obj.linkedin_search_string)
                html = '<div style="font-family: monospace; background: #f5f5f5; padding: 10px; border-radius: 5px;">'
                for key, value in searches.items():
                    html += f'<strong>{key}:</strong><br>{value}<br><br>'
                html += '</div>'
                return format_html(html)
            except:
                return obj.linkedin_search_string
        return 'No search strings available'
    linkedin_search_preview.short_description = 'LinkedIn Search Strings'
    
    def skill_categories_formatted(self, obj):
        if obj.skill_categories and isinstance(obj.skill_categories, dict):
            html = '<div style="font-family: monospace; background: #f5f5f5; padding: 10px; border-radius: 5px;">'
            for category, skills in obj.skill_categories.items():
                if isinstance(skills, list):
                    html += f'<strong>{category}:</strong><br>'
                    html += ', '.join(skills) + '<br><br>'
            html += '</div>'
            return format_html(html)
        return 'No categories available'
    skill_categories_formatted.short_description = 'Skill Categories'
    
    def activate_jds(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} job descriptions activated.')
    activate_jds.short_description = 'Activate selected JDs'
    
    def deactivate_jds(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} job descriptions deactivated.')
    deactivate_jds.short_description = 'Deactivate selected JDs'
    
    def export_to_csv(self, request, queryset):
        import csv
        from django.http import HttpResponse
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="job_descriptions.csv"'
        
        writer = csv.writer(response)
        writer.writerow(['Title', 'Role Category', 'Experience Level', 'Skills', 'Created By', 'Created At'])
        
        for jd in queryset:
            writer.writerow([
                jd.title,
                jd.role_category,
                jd.experience_level,
                jd.all_skills,
                jd.created_by.username,
                jd.created_at.strftime('%Y-%m-%d %H:%M:%S')
            ])
        
        return response
    export_to_csv.short_description = 'Export to CSV'


class GoogleSheetDatabaseAdmin(admin.ModelAdmin):
    list_display = [
        'name',
        'total_candidates',
        'created_by_link',
        'last_synced_display',
        'is_shared_badge',
        'is_active_badge',
        'created_at'
    ]
    
    list_filter = [
        'is_active',
        'is_shared',
        'created_at',
        'last_synced',
        'created_by'
    ]
    
    search_fields = [
        'name',
        'sheet_url',
        'sheet_id',
        'description',
        'created_by__username'
    ]
    
    readonly_fields = [
        'sheet_id',
        'created_by',
        'created_at',
        'updated_at',
        'last_synced',
        'total_candidates'
    ]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'description', 'is_active', 'is_shared')
        }),
        ('Google Sheet Details', {
            'fields': ('sheet_url', 'sheet_id', 'total_candidates', 'last_synced')
        }),
        ('Metadata', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    date_hierarchy = 'created_at'
    actions = ['sync_sheets', 'share_sheets', 'unshare_sheets']
    list_per_page = 25
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(Q(created_by=request.user) | Q(is_shared=True))
    
    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
    
    def created_by_link(self, obj):
        url = reverse('admin:auth_user_change', args=[obj.created_by.id])
        return format_html('<a href="{}">{}</a>', url, obj.created_by.username)
    created_by_link.short_description = 'Created By'
    
    def last_synced_display(self, obj):
        if obj.last_synced:
            now = timezone.now()
            diff = now - obj.last_synced
            
            if diff < timedelta(hours=1):
                minutes = int(diff.total_seconds() / 60)
                time_str = f'{minutes} min ago'
            elif diff < timedelta(days=1):
                hours = int(diff.total_seconds() / 3600)
                time_str = f'{hours} hrs ago'
            else:
                days = diff.days
                time_str = f'{days} days ago'
            
            color = 'green' if diff < timedelta(hours=24) else 'orange'
            return format_html('<span style="color: {};">{}</span>', color, time_str)
        return format_html('<span style="color: red;">Never</span>')
    last_synced_display.short_description = 'Last Synced'
    
    def is_shared_badge(self, obj):
        if obj.is_shared:
            return format_html('<span style="color: blue;">🌐 Shared</span>')
        return format_html('<span style="color: gray;">🔒 Private</span>')
    is_shared_badge.short_description = 'Sharing'
    
    def is_active_badge(self, obj):
        if obj.is_active:
            return format_html('<span style="color: green;">●</span> Active')
        return format_html('<span style="color: red;">●</span> Inactive')
    is_active_badge.short_description = 'Status'
    
    def sync_sheets(self, request, queryset):
        from .utils import fetch_google_sheet_data
        
        success_count = 0
        error_count = 0
        
        for sheet in queryset:
            try:
                df = fetch_google_sheet_data(sheet.sheet_id)
                sheet.total_candidates = len(df)
                sheet.last_synced = timezone.now()
                sheet.save()
                success_count += 1
            except Exception as e:
                error_count += 1
        
        if success_count:
            self.message_user(request, f'{success_count} sheets synced successfully.')
        if error_count:
            self.message_user(request, f'{error_count} sheets failed to sync.', level='error')
    sync_sheets.short_description = 'Sync selected sheets'
    
    def share_sheets(self, request, queryset):
        updated = queryset.update(is_shared=True)
        self.message_user(request, f'{updated} sheets are now shared.')
    share_sheets.short_description = 'Share selected sheets'
    
    def unshare_sheets(self, request, queryset):
        updated = queryset.update(is_shared=False)
        self.message_user(request, f'{updated} sheets are now private.')
    unshare_sheets.short_description = 'Unshare selected sheets'


class AuditLogAdmin(admin.ModelAdmin):
    list_display = [
        'timestamp',
        'user_link',
        'action_badge',
        'target_info',
        'ip_address',
        'view_details'
    ]
    
    list_filter = [
        'action',
        'timestamp',
        'user'
    ]
    
    search_fields = [
        'user__username',
        'action',
        'target_model',
        'ip_address',
        'user_agent'
    ]
    
    readonly_fields = [
        'user',
        'action',
        'target_model',
        'target_id',
        'ip_address',
        'user_agent',
        'details',
        'timestamp',
        'details_formatted'
    ]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('timestamp', 'user', 'action')
        }),
        ('Target', {
            'fields': ('target_model', 'target_id')
        }),
        ('Request Information', {
            'fields': ('ip_address', 'user_agent')
        }),
        ('Details', {
            'fields': ('details_formatted',),
            'classes': ('collapse',)
        }),
    )
    
    date_hierarchy = 'timestamp'
    list_per_page = 50
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
    
    def user_link(self, obj):
        if obj.user:
            url = reverse('admin:auth_user_change', args=[obj.user.id])
            return format_html('<a href="{}">{}</a>', url, obj.user.username)
        return 'Anonymous'
    user_link.short_description = 'User'
    
    def action_badge(self, obj):
        colors = {
            'JD_UPLOAD': 'blue',
            'JD_VIEW': 'gray',
            'JD_DELETE': 'red',
            'SHEET_ADD': 'green',
            'SHEET_SYNC': 'blue',
            'SHEET_DELETE': 'red',
            'MATCH_RUN': 'purple',
            'FILE_DOWNLOAD': 'orange',
            'LOGIN': 'green',
            'LOGOUT': 'gray',
            'PERMISSION_DENIED': 'red'
        }
        color = colors.get(obj.action, 'black')
        return format_html(
            '<span style="background: {}; color: white; padding: 3px 8px; border-radius: 3px; font-size: 11px;">{}</span>',
            color,
            obj.get_action_display()
        )
    action_badge.short_description = 'Action'
    
    def target_info(self, obj):
        if obj.target_model and obj.target_id:
            return f'{obj.target_model} #{obj.target_id}'
        return '-'
    target_info.short_description = 'Target'
    
    def view_details(self, obj):
        if obj.details:
            return format_html(
                '<a href="#" onclick="alert(\'{}\')" style="color: blue;">View</a>',
                json.dumps(obj.details, indent=2).replace("'", "\\'")
            )
        return '-'
    view_details.short_description = 'Details'
    
    def details_formatted(self, obj):
        if obj.details:
            return format_html(
                '<pre style="background: #f5f5f5; padding: 10px; border-radius: 5px;">{}</pre>',
                json.dumps(obj.details, indent=2)
            )
        return 'No details available'
    details_formatted.short_description = 'Details (JSON)'


# Custom User Admin with Statistics
class CustomUserAdmin(BaseUserAdmin):
    list_display = BaseUserAdmin.list_display + ('jd_count', 'sheet_count', 'last_login_formatted')
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.annotate(
            _jd_count=Count('job_descriptions', distinct=True),
            _sheet_count=Count('google_sheets', distinct=True)
        )
        return qs
    
    def jd_count(self, obj):
        count = obj._jd_count
        if count > 0:
            url = f'/admin/base/jobdescription/?created_by__id__exact={obj.id}'
            return format_html('<a href="{}">{} JDs</a>', url, count)
        return '0 JDs'
    jd_count.short_description = 'Job Descriptions'
    jd_count.admin_order_field = '_jd_count'
    
    def sheet_count(self, obj):
        count = obj._sheet_count
        if count > 0:
            url = f'/admin/base/googlesheetdatabase/?created_by__id__exact={obj.id}'
            return format_html('<a href="{}">{} Sheets</a>', url, count)
        return '0 Sheets'
    sheet_count.short_description = 'Google Sheets'
    sheet_count.admin_order_field = '_sheet_count'
    
    def last_login_formatted(self, obj):
        if obj.last_login:
            now = timezone.now()
            diff = now - obj.last_login
            
            if diff < timedelta(hours=1):
                return format_html('<span style="color: green;">Online</span>')
            elif diff < timedelta(days=1):
                hours = int(diff.total_seconds() / 3600)
                return format_html('<span style="color: orange;">{} hrs ago</span>', hours)
            else:
                days = diff.days
                return format_html('<span style="color: gray;">{} days ago</span>', days)
        return format_html('<span style="color: red;">Never</span>')
    last_login_formatted.short_description = 'Last Login'


# Unregister default User admin and register custom
admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)

# Register models
admin.site.register(JobDescription, JobDescriptionAdmin)
admin.site.register(GoogleSheetDatabase, GoogleSheetDatabaseAdmin)
admin.site.register(AuditLog, AuditLogAdmin)

# Customize admin site
admin.site.site_header = 'JD Analyzer Administration'
admin.site.site_title = 'JD Analyzer Admin'
admin.site.index_title = 'Dashboard'