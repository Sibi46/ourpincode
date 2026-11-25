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
    salary_min = forms.IntegerField(required=False,min_value=0,max_value=2147483647)
    salary_max = forms.IntegerField(required=False,min_value=0,max_value=2147483647)
    vacancies = forms.IntegerField(required=False,min_value=1,max_value=9999)

    def clean_vacancies(self):
        value=self.cleaned_data.get('vacancies')
        return 1 if value is None else value

    def clean(self):
        data=super().clean()
        minimum,maximum=data.get('salary_min'),data.get('salary_max')
        if minimum is not None and maximum is not None and maximum<minimum:
            self.add_error('salary_max','Maximum salary must be at least the minimum salary.')
        return data

    def clean_title(self):
        value = self.cleaned_data['title']
        if not any(c.isalpha() for c in value):
            raise forms.ValidationError('Enter a job title containing letters, not only numbers.')
        return value

    def clean_industry(self):
        from .job_industries import clean_job_industries
        return clean_job_industries(self.cleaned_data['industry'])

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
