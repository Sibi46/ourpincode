"""Validate job industry names against the options shown by the posting UI."""
from django.core.exceptions import ValidationError
from .models import Industry

# Matches the built-in chips used when the admin has not configured industries.
DEFAULT_JOB_INDUSTRIES = ('IT & Technology', 'Healthcare & Medical', 'Education & Training', 'Finance & Banking', 'Marketing & Sales', 'Administration', 'Engineering', 'Legal & Compliance', 'Media & Design', 'Retail & Commerce', 'Construction', 'Electrical & Electronics', 'Plumbing & Sanitation', 'Transport & Driving', 'Food & Hospitality', 'Factory & Manufacturing', 'Agriculture', 'Security & Safety', 'Domestic & Household', 'Repair & Maintenance')


def clean_job_industries(value):
    values=[part.strip() for part in value.split(',') if part.strip()]
    configured=list(Industry.objects.filter(is_active=True).values_list('name',flat=True))
    choices=configured or DEFAULT_JOB_INDUSTRIES
    allowed={name.casefold():name for name in choices if any(c.isalpha() for c in name)}
    if len(values)>3 or any(part.casefold() not in allowed for part in values):
        raise ValidationError('Select up to three valid industries from the available options.')
    return ', '.join(dict.fromkeys(allowed[part.casefold()] for part in values))
