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


def subject_names(value):
    names = list(dict.fromkeys(' '.join(name.split()) for name in value.split(',') if name.strip()))
    if len(names) > 10 or any(len(name) > 100 for name in names):
        raise forms.ValidationError('Enter up to 10 subjects, each no longer than 100 characters.')
    for name in names:
        if m.Subject.objects.filter(name__iexact=name, active=False).exists():
            raise forms.ValidationError('A subject with this name is disabled. Contact the administrator.')
    return names


def resolve_subjects(names):
    import hashlib
    records = []
    for name in names:
        subject = m.Subject.objects.filter(name__iexact=name).first()
        if subject is None:
            slug = 'teacher-' + hashlib.sha256(name.casefold().encode()).hexdigest()[:40]
            subject, _ = m.Subject.objects.get_or_create(slug=slug, defaults={'name': name})
        if not subject.active or subject.name.casefold() != name.casefold():
            raise forms.ValidationError('This subject is unavailable. Contact the administrator.')
        records.append(subject)
    return records


class SubjectEntryForm(StyledForm):
    new_subjects = forms.CharField(required=False, max_length=1000, label='Type subject names',
        help_text='Separate names with commas, for example: Maths, English, Piano. Up to 10 names.',
        widget=forms.TextInput(attrs={'placeholder': 'Maths, English, Piano'}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['subjects'].label = 'Or select existing subjects'
        names = [name for name in self.fields if name != 'new_subjects']
        names.insert(names.index('subjects'), 'new_subjects')
        self.order_fields(names)

    def clean_new_subjects(self):
        return subject_names(self.cleaned_data['new_subjects'])

    def _save_m2m(self):
        # Called only after the parent profile/lesson is saved, inside the view's transaction.
        super()._save_m2m()
        self.instance.subjects.add(*resolve_subjects(self.cleaned_data.get('new_subjects', [])))


class TeacherForm(SubjectEntryForm):
    service_pins = forms.CharField(required=False, help_text='Comma-separated six-digit PIN codes served.')

    class Meta:
        model = m.TeacherProfile
        fields = ['kind', 'name', 'description', 'qualifications', 'experience', 'subjects', 'min_age', 'max_age', 'mode', 'address', 'pincode', 'phone', 'email', 'public_fees']
        widgets = {name: forms.Textarea(attrs={'rows': 3}) for name in ('description', 'qualifications', 'address')}
        labels = {'kind': 'Profile type', 'name': 'Teacher or academy name', 'experience': 'Experience (years)', 'min_age': 'Minimum student age', 'max_age': 'Maximum student age', 'pincode': 'PIN code', 'public_fees': 'Show lesson fees on my public profile'}

    def sections(self):
        for title, names in (
            ('Your teaching profile', ('kind', 'name', 'description', 'qualifications', 'experience')),
            ('What you teach', ('new_subjects', 'subjects', 'mode', 'min_age', 'max_age')),
            ('Location & contact', ('address', 'pincode', 'service_pins', 'phone', 'email', 'public_fees')),
        ):
            yield title, [self[name] for name in names]

    def clean_service_pins(self):
        pins = set(x.strip() for x in self.cleaned_data['service_pins'].split(',') if x.strip())
        for pin in pins:
            m.PIN(pin)
        return pins


class GroupLeaveForm(forms.Form):
    enrolment = forms.ModelChoiceField(queryset=m.Enrolment.objects.none(), label='Student')
    start_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    end_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}), help_text='Both dates are included. Only classes already in this group timetable are affected.')
    status = forms.ChoiceField(choices=[('excused', 'Leave (excused)'), ('absent', 'Absent')], help_text='Leave can be recorded in advance. Absence can only be recorded after class starts.')
    note = forms.CharField(max_length=250, label='Reason / note', widget=forms.Textarea(attrs={'rows': 3}))

    def __init__(self, *args, batch, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['enrolment'].queryset = m.Enrolment.objects.filter(membership__batch=batch, status='active').select_related('learner', 'lesson')

    def clean(self):
        data = super().clean()
        if data.get('start_date') and data.get('end_date') and data['end_date'] < data['start_date']:
            raise forms.ValidationError('End date must be on or after start date.')
        return data


class LessonForm(SubjectEntryForm):
    class Meta:
        model = m.Lesson
        fields = ['name', 'description', 'subjects', 'min_age', 'max_age', 'skill_level', 'mode', 'location', 'fee', 'billing_period', 'duration_minutes', 'capacity', 'start_date', 'end_date', 'active']


class GroupCreateForm(LessonForm):
    weekdays = forms.MultipleChoiceField(choices=m.DAYS, label='Class days', widget=forms.CheckboxSelectMultiple)
    meeting_url = forms.URLField(required=False, validators=[m.meeting_url], label='Online meeting link')

    class Meta(LessonForm.Meta):
        fields = ['name', 'description', 'subjects', 'mode', 'location', 'fee', 'billing_period', 'capacity']
        labels = {'name': 'Group name', 'fee': 'Advertised fee', 'capacity': 'Maximum students', 'location': 'Class address'}
        widgets = {name: forms.Textarea(attrs={'rows': 2}) for name in ('description', 'location')}
        help_texts = {'fee': 'Student fee agreements and payments are managed separately.'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields.pop('subjects')
        for day, label in m.DAYS:
            for part in ('start', 'end'):
                self.fields[f'day_{part}_{day}'] = forms.TimeField(required=False, label=f'{label} {part} time', widget=forms.TimeInput(attrs={'type': 'time', 'step': '60', 'data-weekday': str(day)}))
        self.order_fields(['name', 'new_subjects', 'description', 'mode', 'location', 'meeting_url', 'capacity', 'fee', 'billing_period', 'weekdays'])

    def day_rows(self):
        return [(checkbox, self[f'day_start_{checkbox.data["value"]}'], self[f'day_end_{checkbox.data["value"]}']) for checkbox in self['weekdays']]

    def main_fields(self):
        return [field for field in self if field.name != 'weekdays' and not field.name.startswith('day_')]

    def clean(self):
        data = super().clean()
        slots = []
        for day in data.get('weekdays', []):
            start, end = data.get(f'day_start_{day}'), data.get(f'day_end_{day}')
            if not start: self.add_error(f'day_start_{day}', 'Enter start time.')
            if not end: self.add_error(f'day_end_{day}', 'Enter end time.')
            if start and end:
                if end <= start or start.second or end.second:
                    self.add_error(f'day_end_{day}', 'End time must be after start time on the same day, in whole minutes.')
                else:
                    slots.append((int(day), start, (end.hour*60+end.minute)-(start.hour*60+start.minute)))
        data['slots'] = slots
        if data.get('mode') in ('offline', 'hybrid') and not data.get('location'):
            self.add_error('location', 'Enter the class address.')
        if data.get('mode') == 'offline':
            data['meeting_url'] = ''
        if data.get('mode') == 'online':
            data['location'] = ''
        if data.get('mode') in ('online', 'hybrid') and not data.get('meeting_url'):
            self.add_error('meeting_url', 'Enter an approved online meeting link.')
        return data


class GroupMemberForm(forms.Form):
    enrolment = forms.ModelChoiceField(queryset=m.Enrolment.objects.none(), required=False, label='Add an enrolled student')
    application = forms.ModelChoiceField(queryset=m.Application.objects.none(), required=False, label='Or accept an application and add student')

    def __init__(self, *args, batch, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['enrolment'].queryset = batch.lesson.enrolments.filter(status='active').exclude(membership__batch=batch).select_related('learner', 'lesson')
        self.fields['application'].queryset = m.Application.objects.filter(lesson=batch.lesson, status__in=['pending', 'needs_info'], learner__isnull=False, applicant__isnull=False)
        self.fields['application'].label_from_instance = lambda obj: obj.name

    def clean(self):
        data = super().clean()
        if bool(data.get('enrolment')) == bool(data.get('application')):
            raise forms.ValidationError('Choose one enrolled student or one application.')
        return data


class BatchForm(StyledForm):
    class Meta:
        model = m.Batch
        fields = ['name', 'capacity', 'location', 'mode', 'status']


class AvailabilityForm(StyledForm):
    class Meta:
        model = m.Availability
        fields = ['weekday', 'start', 'end']


class LearnerForm(StyledForm):
    interests = forms.CharField(required=False, max_length=1000, help_text='Type interests separated by commas, e.g. Maths, Music.', widget=forms.TextInput(attrs={'placeholder': 'Maths, Music, Drawing'}))
    relationship = forms.CharField(required=False, help_text='For a child/dependant, state your relationship.')
    attestation = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 3}), help_text='For a child or dependant, explain your authority to act for this learner. An administrator reviews guardian access.')
    self_registration = forms.BooleanField(required=False, label='I am registering myself and am at least 18')

    class Meta:
        model = m.Learner
        fields = ['name', 'dob', 'age', 'guardian_name', 'phone', 'email', 'address', 'pincode', 'interests']
        labels = {'dob': 'Date of birth', 'name': 'Student name', 'pincode': 'PIN code'}
        widgets = {'address': forms.Textarea(attrs={'rows': 2}), 'pincode': forms.TextInput(attrs={'data-pin-lookup': 'off', 'inputmode': 'numeric', 'pattern': '[0-9]{6}', 'maxlength': '6'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial['interests'] = ', '.join(self.instance.interests.values_list('name', flat=True))
        self.fields['pincode'].help_text = 'Enter any complete six-digit PIN code. Registration in our directory is not required.'
        self.fields['age'].help_text = 'Calculated from date of birth, or enter age if birth date is unavailable.'
        self.fields['dob'].widget.attrs['max'] = timezone.localdate().isoformat()

    def clean_interests(self):
        return subject_names(self.cleaned_data['interests'])

    def _save_m2m(self):
        names = self.cleaned_data['interests']
        self.cleaned_data['interests'] = resolve_subjects(names)
        try:
            super()._save_m2m()
        finally:
            self.cleaned_data['interests'] = names

    def sections(self):
        for title, names in (
            ('Student details', ('self_registration', 'name', 'dob', 'age', 'interests')),
            ('Contact & location', ('guardian_name', 'phone', 'email', 'address', 'pincode', 'relationship', 'attestation')),
        ):
            fields = [self[name] for name in names if name in self.fields]
            if fields:
                yield title, fields

    def clean(self):
        data = super().clean()
        dob = data.get('dob')
        if dob and dob <= timezone.localdate():
            today = timezone.localdate()
            data['age'] = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
            self.instance.age_as_of = today
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
    q = forms.CharField(required=False, label='Teacher, academy or lesson', widget=forms.TextInput(attrs={'placeholder': 'Try Maths, piano or an academy'}))
    pincode = forms.CharField(required=False, max_length=64, label='PIN codes',
        help_text='Up to 3 six-digit PIN codes, separated by commas or spaces.',
        widget=forms.TextInput(attrs={'placeholder': '600001, 600002, 600003', 'aria-describedby': 'pin-help'}))
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

    def clean_pincode(self):
        import re
        value = self.cleaned_data['pincode'].strip()
        if not value:
            return []
        pins = [pin for pin in re.split(r'[\s,]+', value) if pin]
        if not pins or len(pins) > 3 or any(not re.fullmatch(r'[0-9]{6}', pin) for pin in pins):
            raise forms.ValidationError('Enter up to 3 complete six-digit PIN codes, separated by commas or spaces.')
        return list(dict.fromkeys(pins))

    def clean(self):
        data = super().clean()
        if any(data.get(k) is not None for k in ('latitude', 'longitude', 'radius')) and not all(data.get(k) is not None for k in ('latitude', 'longitude', 'radius')):
            raise forms.ValidationError('Distance searches require latitude, longitude and radius. PIN alone is an area match.')
        if data.get('start') and data.get('end') and data['start'] >= data['end']:
            raise forms.ValidationError('End time must be after start time.')
        return data
