from django import forms
from .models import JobDescription, CandidateDatabase

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
        
class CandidateDatabaseUploadForm(forms.ModelForm):
    class Meta:
        model = CandidateDatabase
        fields = ['file']
        widgets = {
            'file': forms.FileInput(attrs={'class': 'form-control', 'accept': '.xlsx,.xls'}),
        }


class CandidateMatchForm(forms.Form):
    candidate_database = forms.ModelChoiceField(
        queryset=CandidateDatabase.objects.all(),
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Select Candidate Database',
        empty_label='Choose a database...'
    )
    
    min_match_percentage = forms.IntegerField(
        initial=50,
        min_value=0,
        max_value=100,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '50'}),
        label='Minimum Match Percentage',
        help_text='Candidates must match at least this percentage of required skills'
    )