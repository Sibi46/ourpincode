from django import forms
from django.utils import timezone
from .forms import StyledForm
from . import models as m


class EventForm(StyledForm):
    class Meta:
        model = m.LearningEvent
        fields = ['kind', 'title', 'description', 'start', 'end', 'venue', 'mode', 'registration_start', 'registration_end', 'capacity', 'public', 'status']


class ProgrammeForm(StyledForm):
    class Meta:
        model = m.ProgrammeItem
        fields = ['title', 'description', 'start', 'end', 'venue', 'participants']


class ResultForm(StyledForm):
    class Meta:
        model = m.EventResult
        fields = ['award', 'title', 'placement', 'notes']


class AchievementForm(StyledForm):
    class Meta:
        model = m.Achievement
        fields = ['enrolment', 'kind', 'title', 'description', 'date', 'result', 'level', 'public_requested']


class AssignmentForm(StyledForm):
    class Meta:
        model = m.Assignment
        fields = ['batch', 'title', 'instructions', 'due_at', 'active']


class AnnouncementForm(StyledForm):
    class Meta:
        model = m.Announcement
        fields = ['lesson', 'batch', 'event', 'title', 'body', 'publish_at']


class PointForm(StyledForm):
    class Meta:
        model = m.PointRule
        fields = ['source', 'value', 'active']


class LevelForm(StyledForm):
    class Meta:
        model = m.LevelDefinition
        fields = ['name', 'threshold']


class ConsentForm(forms.Form):
    revision = forms.IntegerField(widget=forms.HiddenInput)
    learner = forms.ModelChoiceField(queryset=m.Learner.objects.none())
    display_name = forms.CharField(max_length=80, required=False, help_text='Optional public display name; leave blank to show no name.')
    allow_media = forms.BooleanField(required=False, label='Allow this specific photo/video to appear publicly')
    expires_at = forms.DateTimeField(widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}))
    confirm = forms.BooleanField(label='I have reviewed this exact content and authorize its publication until expiry. I can revoke consent.')


class MediaForm(forms.Form):
    file = forms.FileField(help_text='JPEG/PNG/WebP up to 10 MB; MP4/WebM up to 100 MB. Videos require server validation.')
    title = forms.CharField(max_length=150)
    public_requested = forms.BooleanField(required=False, label='Show on public profile')
    subjects = forms.ModelMultipleChoiceField(queryset=m.Learner.objects.none(), required=False, label='Students visible in this photo / video (optional)', widget=forms.CheckboxSelectMultiple, help_text='Select every recognizable student. Public publication requires each student’s verified adult consent.')


class ComplaintForm(forms.Form):
    subject = forms.CharField(max_length=200)
    description = forms.CharField(widget=forms.Textarea, max_length=10000)


class TeacherPublicationForm(forms.Form):
    subjects = forms.ModelMultipleChoiceField(queryset=m.Learner.objects.none(), required=False, label='Students visible in this photo / video', widget=forms.CheckboxSelectMultiple)
    students_confirmed = forms.BooleanField(label='I selected every recognizable student, or no students appear in this upload', help_text='Media showing students remains private until their required consent is verified.')
