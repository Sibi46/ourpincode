import uuid
from django import forms
from django.utils import timezone
from . import models as m


class StyledForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field, forms.DateTimeField):
                field.widget = forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M')
            elif isinstance(field, forms.DateField):
                field.widget = forms.DateInput(attrs={'type': 'date'})
            elif isinstance(field, forms.TimeField):
                field.widget = forms.TimeInput(attrs={'type': 'time'})


class TeacherForm(StyledForm):
    service_pins = forms.CharField(required=False, help_text='Comma-separated six-digit PIN codes served.')

    class Meta:
        model = m.TeacherProfile
        fields = ['kind', 'name', 'description', 'qualifications', 'experience', 'subjects', 'min_age', 'max_age', 'mode', 'address', 'pincode', 'phone', 'email', 'latitude', 'longitude', 'location_source', 'radius_km', 'public_fees']

    def clean_service_pins(self):
        pins = set(x.strip() for x in self.cleaned_data['service_pins'].split(',') if x.strip())
        for pin in pins:
            m.PIN(pin)
        return pins


class LessonForm(StyledForm):
    class Meta:
        model = m.Lesson
        fields = ['name', 'description', 'subjects', 'min_age', 'max_age', 'skill_level', 'mode', 'location', 'fee', 'billing_period', 'duration_minutes', 'capacity', 'start_date', 'end_date', 'active']


class BatchForm(StyledForm):
    class Meta:
        model = m.Batch
        fields = ['name', 'capacity', 'location', 'mode', 'status']


class AvailabilityForm(StyledForm):
    class Meta:
        model = m.Availability
        fields = ['weekday', 'start', 'end']


class LearnerForm(StyledForm):
    relationship = forms.CharField(required=False, help_text='For a child/dependant, state your relationship.')
    attestation = forms.CharField(required=False, widget=forms.Textarea, help_text='Explain your authority to act for this learner. An administrator reviews guardian access.')
    self_registration = forms.BooleanField(required=False, label='I am registering myself and am at least 18')

    class Meta:
        model = m.Learner
        fields = ['name', 'dob', 'age', 'guardian_name', 'phone', 'email', 'address', 'pincode', 'interests']

    def clean(self):
        data = super().clean()
        if self.instance.pk:
            return data
        if data.get('self_registration'):
            dob = data.get('dob')
            today = timezone.localdate()
            if not dob or today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day)) < 18:
                self.add_error('dob', 'Adult self-registration requires your date of birth.')
        elif not data.get('relationship') or not data.get('attestation'):
            raise forms.ValidationError('Guardian requests require relationship and attestation.')
        return data


class ApplicationForm(StyledForm):
    learner = forms.ModelChoiceField(queryset=m.Learner.objects.none(), required=False,
        help_text='Choose an authorized learner to allow enrolment; otherwise this is an enquiry.')
    website = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = m.Application
        fields = ['learner', 'name', 'age', 'mobile', 'email', 'pincode', 'preferred_days', 'preferred_timings', 'mode', 'message']

    def clean_website(self):
        if self.cleaned_data.get('website'):
            raise forms.ValidationError('Unable to submit.')
        return ''


class RuleForm(StyledForm):
    class Meta:
        model = m.ScheduleRule
        fields = ['weekday', 'start_time', 'duration_minutes', 'timezone_name', 'start_date', 'end_date', 'meeting_url', 'active']


class SessionForm(StyledForm):
    class Meta:
        model = m.ClassSession
        fields = ['start', 'end', 'mode', 'location', 'meeting_url', 'status', 'reason']


class FeeForm(StyledForm):
    class Meta:
        model = m.FeeAgreement
        fields = ['start_date', 'end_date', 'amount', 'cadence']


class InvoiceForm(StyledForm):
    class Meta:
        model = m.Invoice
        fields = ['period_start', 'period_end', 'due_date', 'amount']


class ProgressForm(StyledForm):
    class Meta:
        model = m.ProgressEntry
        fields = ['date', 'assessment', 'comments']


class PaymentForm(forms.Form):
    amount = forms.DecimalField(max_digits=10, decimal_places=2, min_value=0.01)
    method = forms.ChoiceField(choices=m.Payment._meta.get_field('method').choices)
    paid_at = forms.DateTimeField(initial=timezone.now, widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'))
    key = forms.UUIDField(initial=uuid.uuid4, widget=forms.HiddenInput)


class SearchForm(forms.Form):
    q = forms.CharField(required=False, label='Teacher, academy or lesson')
    pincode = forms.RegexField(r'^[0-9]{6}$', required=False)
    subject = forms.ModelChoiceField(queryset=m.Subject.objects.filter(active=True), required=False)
    kind = forms.ChoiceField(choices=[('', 'Any'), ('teacher', 'Teacher'), ('academy', 'Academy')], required=False)
    mode = forms.ChoiceField(choices=[('', 'Any')] + m.MODES, required=False)
    age = forms.IntegerField(min_value=0, max_value=120, required=False)
    weekday = forms.TypedChoiceField(choices=[('', 'Any day')] + m.DAYS, coerce=int, empty_value=None, required=False)
    start = forms.TimeField(required=False, widget=forms.TimeInput(attrs={'type': 'time'}))
    end = forms.TimeField(required=False, widget=forms.TimeInput(attrs={'type': 'time'}))
    latitude = forms.FloatField(min_value=-90, max_value=90, required=False)
    longitude = forms.FloatField(min_value=-180, max_value=180, required=False)
    radius = forms.FloatField(min_value=0.1, max_value=500, required=False, label='Straight-line distance (km)')

    def clean(self):
        data = super().clean()
        if any(data.get(k) is not None for k in ('latitude', 'longitude', 'radius')) and not all(data.get(k) is not None for k in ('latitude', 'longitude', 'radius')):
            raise forms.ValidationError('Distance searches require latitude, longitude and radius. PIN alone is an area match.')
        if data.get('start') and data.get('end') and data['start'] >= data['end']:
            raise forms.ValidationError('End time must be after start time.')
        return data
