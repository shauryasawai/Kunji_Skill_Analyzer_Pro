from django import forms
from .models import JobDescription, GoogleSheetDatabase

class JDUploadForm(forms.ModelForm):
    domain = forms.ChoiceField(
        choices=[
            ('', 'Auto-detect'),
            ('Technical', 'Technical'),
            ('Marketing', 'Marketing'),
            ('Finance', 'Finance'),
            ('HR', 'Human Resources'),
            ('Sales', 'Sales'),
            ('Operations', 'Operations'),
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    class Meta:
        model = JobDescription
        fields = ['title', 'file']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Senior Marketing Manager'}),
            'file': forms.FileInput(attrs={'class': 'form-control', 'accept': '.txt,.pdf,.docx'}),
        }


class GoogleSheetForm(forms.ModelForm):
    class Meta:
        model = GoogleSheetDatabase
        fields = ['name', 'sheet_url']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'e.g., Tech Candidates 2025'
            }),
            'sheet_url': forms.URLInput(attrs={
                'class': 'form-control', 
                'placeholder': 'https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID/edit'
            }),
        }
        help_texts = {
            'sheet_url': 'Make sure the Google Sheet is shared with the service account email'
        }


class CandidateMatchForm(forms.Form):
    google_sheet = forms.ModelChoiceField(
        queryset=GoogleSheetDatabase.objects.filter(is_active=True),
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Select Google Sheet Database',
        empty_label='Choose a Google Sheet...'
    )
    
    min_match_percentage = forms.IntegerField(
        initial=50,
        min_value=0,
        max_value=100,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '50'}),
        label='Minimum Match Percentage',
        help_text='Candidates must match at least this percentage of required skills'
    )