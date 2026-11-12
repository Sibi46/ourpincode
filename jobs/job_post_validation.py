import re
from django import forms
from .form_fields import FourDigitYearDateField


class JobPostingValidationForm(forms.Form):
    title = forms.CharField(max_length=200)
    industry = forms.CharField(max_length=100, required=False)
    description = forms.CharField(required=False)
    skills = forms.CharField(max_length=500, required=False)
    pincode = forms.RegexField(r'^[1-9][0-9]{5}$', max_length=6, required=False,
        error_messages={'invalid': 'Enter a valid six-digit numeric pincode.'})
    location = forms.CharField(max_length=200, required=False)
    last_date = FourDigitYearDateField(required=False)

    def clean_title(self):
        value = self.cleaned_data['title']
        if not any(c.isalpha() for c in value):
            raise forms.ValidationError('Enter a job title containing letters, not only numbers.')
        return value

    def clean_industry(self):
        values = [item.strip() for item in self.cleaned_data['industry'].split(',') if item.strip()]
        if len(values) > 3 or any(not any(c.isalpha() for c in item) for item in values):
            raise forms.ValidationError('Choose up to three industry names containing letters.')
        return ', '.join(values)

    def clean_description(self):
        value = self.cleaned_data['description']
        if len(re.findall(r'\S+', value)) > 150:
            raise forms.ValidationError('Keep the job description within 150 words.')
        return value

    def clean_location(self):
        value = self.cleaned_data['location']
        if value and (any(c.isnumeric() for c in value) or not any(c.isalpha() for c in value)):
            raise forms.ValidationError('Enter a location or area name using text without numbers.')
        return value
