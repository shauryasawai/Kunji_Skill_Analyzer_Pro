from django import forms
from .models import JobDescription

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