from django import forms
from django.contrib.auth import get_user_model

from jobs.models import PinCode
from .models import BirthdayCard, Comment, NewsAgent, NewsItem, Rating
from .permissions import active_pincodes, is_admin


class FeedForm(forms.Form):
    pincode = forms.ModelChoiceField(queryset=PinCode.objects.none(), to_field_name='code', required=False, empty_label='Select your pincode')
    category = forms.ChoiceField(choices=[('', 'All categories')] + list(NewsItem.Category.choices), required=False)
    kind = forms.ChoiceField(choices=[('', 'News & events'), ('news', 'News'), ('event', 'Events')], required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['pincode'].queryset = active_pincodes()


class NewsItemForm(forms.ModelForm):
    class Meta:
        model = NewsItem
        fields = ['pincode', 'title', 'category', 'kind', 'body', 'photo', 'video', 'event_start', 'event_end', 'venue', 'status']
        widgets = {
            'body': forms.Textarea(attrs={'rows': 10}),
            'event_start': forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={'type': 'datetime-local'}),
            'event_end': forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={'type': 'datetime-local'}),
        }
        help_texts = {'photo': 'JPEG, PNG or WebP; up to 5 MB.', 'video': 'MP4 or WebM; up to 25 MB.', 'event_start': 'Local time (Asia/Kolkata). Required for events.', 'status': 'Drafts are visible only to your assigned desk and admins.'}

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['pincode'].queryset = active_pincodes()
        if not is_admin(user):
            self.fields.pop('pincode')
        # Never expose a direct storage URL, including for draft attachments.
        self.fields['photo'].widget = forms.FileInput(attrs={'accept': 'image/jpeg,image/png,image/webp'})
        self.fields['video'].widget = forms.FileInput(attrs={'accept': 'video/mp4,video/webm'})


class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ['text']
        widgets = {'text': forms.Textarea(attrs={'rows': 3, 'maxlength': 160, 'placeholder': 'Add something helpful to the conversation…'})}


class RatingForm(forms.ModelForm):
    class Meta:
        model = Rating
        fields = ['stars']
        widgets = {'stars': forms.Select(choices=[(n, '★' * n) for n in range(1, 6)])}


class ReportForm(forms.Form):
    reason = forms.CharField(max_length=200, widget=forms.Textarea(attrs={'rows': 3}))


class AgentForm(forms.ModelForm):
    class Meta:
        model = NewsAgent
        fields = ['user', 'pincode', 'is_active']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['user'].queryset = get_user_model().objects.filter(is_active=True).order_by('pk')
        self.fields['pincode'].queryset = PinCode.objects.select_related('district').order_by('code')


class BirthdayForm(forms.ModelForm):
    class Meta:
        model = BirthdayCard
        fields = ['recipient', 'message', 'theme', 'is_public']
        widgets = {'message': forms.Textarea(attrs={'rows': 3})}
