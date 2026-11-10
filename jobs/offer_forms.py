from datetime import timedelta
from calendar import monthrange
from django import forms
from django.utils import timezone
from .offer_categories import OFFER_CATEGORIES


class OfferValidityForm(forms.Form):
    category = forms.ChoiceField(choices=OFFER_CATEGORIES)
    valid_type = forms.ChoiceField(choices=[(v, v) for v in ('week', 'month', 'weekdays', 'specific', 'repeat')])
    valid_until = forms.DateField(required=False)
    valid_days = forms.CharField(required=False)

    def clean(self):
        data = super().clean()
        kind = data.get('valid_type')
        today = timezone.localdate()
        if kind in ('week', 'month', 'weekdays'):
            if kind == 'month':
                data['valid_until'] = today.replace(day=monthrange(today.year, today.month)[1])
            else:
                days = ((6 - today.weekday()) % 7 or 7) if kind == 'week' else (4 - today.weekday()) % 7
                data['valid_until'] = today + timedelta(days=days)
            data['valid_days'] = 'Mon,Tue,Wed,Thu,Fri' if kind == 'weekdays' else ''
        elif kind == 'specific':
            if not data.get('valid_until') or data['valid_until'] < today:
                self.add_error('valid_until', 'Choose a valid expiry date that is today or later.')
            data['valid_days'] = ''
        elif kind == 'repeat':
            days = data.get('valid_days', '').split(',')
            allowed = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
            if not days or any(day not in allowed for day in days):
                self.add_error('valid_days', 'Choose at least one valid day for Repeat Weekly.')
            else:
                data['valid_days'] = ','.join(day for day in allowed if day in days)
            data['valid_until'] = None
        return data
