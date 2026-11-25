"""Validation for Campus institute and company registration."""
from django import forms
from django.core.exceptions import ValidationError
from jobs.person_names import valid_person_name
from .models import Institution, CampusCompany


def validate_text_without_numbers(value):
    if value and (any(char.isnumeric() for char in value) or not any(char.isalpha() for char in value)):
        raise ValidationError('Use a name containing letters without numbers.')


def validate_contact_name(value):
    if value and not valid_person_name(value):
        raise ValidationError('Use letters and spaces only; numbers are not allowed.')


class InstitutionRegistrationForm(forms.ModelForm):
    po_name=forms.CharField(label='Placement Officer Name',max_length=150,validators=[validate_contact_name])

    class Meta:
        model=Institution
        fields=['name','affiliation','city','district','state','website']

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        for name in ['name','affiliation','city','district','state']:
            self.fields[name].validators.append(validate_text_without_numbers)


class CampusCompanyRegistrationForm(forms.ModelForm):
    class Meta:
        model=CampusCompany
        fields=['contact_person','website']

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['contact_person'].validators.append(validate_contact_name)
