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


class SubjectInputs(forms.TextInput):
    template_name = 'tuition/widgets/subjects.html'

    def value_from_datadict(self, data, files, name):
        values = data.getlist(name) if hasattr(data, 'getlist') else data.get(name, '')
        return ','.join(values) if isinstance(values, list) else values

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context['subjects'] = (value or '').split(',')
        return context


class SubjectEntryForm(StyledForm):
    new_subjects = forms.CharField(required=False, max_length=1000, label='Type subject names',
        help_text='Use + to add another subject. Up to 10 subjects.', widget=SubjectInputs())

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
    opening_days = forms.MultipleChoiceField(choices=m.DAYS, required=False, widget=forms.CheckboxSelectMultiple, label='Opening days')
    opening_time = forms.TimeField(required=False, label='Opening time (India)')
    closing_time = forms.TimeField(required=False, label='Closing time (India)')
    profile_photo = forms.FileField(required=False, label='Logo / profile image', help_text='Shown beside your name at the top of your public profile.')
    banner_photo = forms.FileField(required=False, label='Banner image', help_text='Shown behind your name in the top section of your public profile. Use a wide image.')
    existing_profile_image = forms.ModelChoiceField(queryset=m.MediaAsset.objects.none(), required=False, label='Choose an uploaded logo / profile photo')
    existing_banner_image = forms.ModelChoiceField(queryset=m.MediaAsset.objects.none(), required=False, label='Choose an uploaded banner')
    publish_brand_images = forms.BooleanField(required=False, label='Publish my profile and banner images', help_text='I confirm these images contain no recognizable students. For student photos, use the gallery and consent process.')
    service_pins = forms.CharField(required=False, help_text='Comma-separated six-digit PIN codes served.')

    class Meta:
        model = m.TeacherProfile
        fields = ['kind', 'name', 'description', 'qualifications', 'experience', 'subjects', 'min_age', 'max_age', 'mode', 'address', 'pincode', 'phone', 'email', 'public_fees']
        widgets = {name: forms.Textarea(attrs={'rows': 3}) for name in ('description', 'qualifications', 'address')}
        labels = {'kind': 'Profile type', 'name': 'Teacher or academy name', 'experience': 'Experience (years)', 'min_age': 'Minimum student age', 'max_age': 'Maximum student age', 'pincode': 'PIN code', 'public_fees': 'Show lesson fees on my public profile'}

    def sections(self):
        for title, names in (
            ('Your teaching profile', ('kind', 'name', 'profile_photo', 'existing_profile_image', 'banner_photo', 'existing_banner_image', 'publish_brand_images', 'description', 'qualifications', 'experience')),
            ('What you teach', ('new_subjects', 'subjects', 'mode', 'min_age', 'max_age')),
            ('Academy timings', ('opening_days', 'opening_time', 'closing_time')),
            ('Location & contact', ('address', 'pincode', 'service_pins', 'phone', 'email', 'public_fees')),
        ):
            fields = [self[name] for name in names if name in self.fields]
            if fields:
                yield title, fields

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields.pop('subjects')
        self.fields.pop('public_fees')
        images = m.MediaAsset.objects.filter(teacher=self.instance, mime__startswith='image/', subjects__isnull=True).exclude(moderation='rejected') if self.instance.pk else m.MediaAsset.objects.none()
        for field, attribute in [('existing_profile_image', 'profile_image_id'), ('existing_banner_image', 'banner_image_id')]:
            self.fields[field].queryset = images
            self.fields[field].label_from_instance = lambda asset: asset.title or 'Image ' + str(asset.uid)[:8]
            self.initial[field] = getattr(self.instance, attribute)
        if self.instance.pk:
            self.initial['new_subjects'] = ','.join(self.instance.subjects.values_list('name', flat=True))
            for name in ('opening_days', 'opening_time', 'closing_time'):
                self.fields.pop(name)

    def clean(self):
        data = super().clean()
        if not self.instance.pk and data.get('kind') == 'academy':
            for name in ('opening_days', 'opening_time', 'closing_time'):
                if not data.get(name):
                    self.add_error(name, 'Enter academy opening days and hours.')
            if data.get('opening_time') and data.get('closing_time') and data['closing_time'] <= data['opening_time']:
                self.add_error('closing_time', 'Closing time must be after opening time.')
        if (data.get('profile_photo') or data.get('banner_photo') or (data.get('existing_profile_image') and data['existing_profile_image'].pk != self.instance.profile_image_id) or (data.get('existing_banner_image') and data['existing_banner_image'].pk != self.instance.banner_image_id)) and not data.get('publish_brand_images'):
            self.add_error('publish_brand_images', 'Confirm these images contain no recognizable students, or upload student media through the gallery.')
        if data.get('publish_brand_images'):
            for field, upload_field, selected_field in [('profile_image', 'profile_photo', 'existing_profile_image'), ('banner_image', 'banner_photo', 'existing_banner_image')]:
                if data.get(upload_field):
                    continue
                asset = data.get(selected_field) or getattr(self.instance, field, None)
                if asset and (asset.teacher_id != self.instance.pk or asset.subjects.exists() or asset.moderation == 'rejected'):
                    self.add_error('publish_brand_images', 'An existing image requires consent or administrator review. Use the gallery to manage it.')
        return data

    def _save_m2m(self):
        self.instance.subjects.set(resolve_subjects(self.cleaned_data.get('new_subjects', [])))

    def clean_profile_photo(self):
        return validated_photo(self.cleaned_data.get('profile_photo'))

    def clean_banner_photo(self):
        return validated_photo(self.cleaned_data.get('banner_photo'))

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


class WeeklyTimesWidget(forms.TextInput):
    template_name = 'tuition/widgets/weekly_times.html'

    def value_from_datadict(self, data, files, name):
        values = data.getlist(name) if hasattr(data, 'getlist') else data.get(name, [])
        return ','.join(values) if isinstance(values, list) else values

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context['times'] = (value or '').split(',')[:24]
        context['times'] += [''] * max(0, 5-len(context['times']))
        return context


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
        self.fields['fee'].required = False
        self.fields['fee'].help_text = 'Optional. Leave blank to save INR 0. Student fee agreements are managed separately.'
        for day, label in m.DAYS:
            self.fields[f'day_start_{day}'] = forms.CharField(required=False, max_length=300, label=f'{label} start times', widget=WeeklyTimesWidget())
        self.order_fields(['name', 'new_subjects', 'description', 'mode', 'location', 'meeting_url', 'capacity', 'fee', 'billing_period', 'weekdays'])

    def day_rows(self):
        return [(checkbox, self[f'day_start_{checkbox.data["value"]}']) for checkbox in self['weekdays']]

    def main_fields(self):
        return [field for field in self if field.name != 'weekdays' and not field.name.startswith('day_')]

    def clean(self):
        data = super().clean()
        slots = []
        for day in data.get('weekdays', []):
            name = f'day_start_{day}'
            values = [v for v in (data.get(name) or '').split(',') if v.strip()]
            if not values:
                self.add_error(name, 'Enter at least one start time for this day.')
            if len(values) > 24:
                self.add_error(name, 'Use up to 24 slots per day.')
            seen = set()
            for value in values:
                try:
                    start = forms.TimeField(input_formats=['%H:%M']).clean(value)
                    if start in seen:
                        raise forms.ValidationError('Use different start times for each slot.')
                    seen.add(start)
                    slots.append((int(day), start, 60))
                except forms.ValidationError as error:
                    self.add_error(name, error)
        data['fee'] = data.get('fee') or 0
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
        else:
            if not data.get('relationship'):
                self.add_error('relationship', 'Enter your relationship to this student, or select adult self-registration above.')
            if not data.get('attestation'):
                self.add_error('attestation', 'Confirm that you are authorized to register this child or dependant.')
        return data


class ApplicationForm(StyledForm):
    learner = forms.ModelChoiceField(queryset=m.Learner.objects.none(), required=False, label='Student', empty_label='Send an enquiry without selecting a student',
        help_text='Select your student profile. Children appear after guardian approval. You may send an enquiry while waiting.')
    website = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = m.Application
        fields = ['learner', 'name', 'age', 'parent_name', 'parent_phone', 'mobile', 'email', 'pincode', 'preferred_days', 'preferred_timings', 'mode', 'message']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['mobile'].required = False
        self.fields['mobile'].label = 'Contact phone'
        self.fields['parent_name'].label = 'Parent / guardian name'
        self.fields['parent_phone'].label = 'Parent / guardian phone'

    def clean(self):
        data = super().clean()
        age = data.get('age')
        if age is not None and age < 18:
            for field in ('parent_name', 'parent_phone'):
                if not data.get(field):
                    self.add_error(field, 'Required for students under 18.')
            if data.get('parent_phone'):
                data['mobile'] = data['parent_phone']
        elif age is not None:
            if not data.get('mobile'):
                self.add_error('mobile', 'Enter a contact phone number.')
            data['parent_name'] = ''
            data['parent_phone'] = ''
        return data

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


def validated_photo(file):
    if file:
        from .storage import validate_image
        validate_image(file)
        file.seek(0)
    return file


class AcademyStaffForm(SubjectEntryForm):
    profile_photo = forms.FileField(required=False, label='Profile image')

    class Meta:
        model = m.AcademyStaff
        fields = ['name', 'phone', 'subjects', 'public']
        labels = {'public': 'Publish staff profile with permission'}

    def clean_profile_photo(self):
        return validated_photo(self.cleaned_data.get('profile_photo'))
