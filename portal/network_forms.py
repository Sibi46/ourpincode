from django import forms


class NetworkPostForm(forms.Form):
    text = forms.CharField(
        max_length=500, label='What would you like to do?',
        widget=forms.Textarea(attrs={
            'rows': 4, 'id': 'networkText', 'placeholder': "I'm free now. Anyone up for cricket?",
            'aria-describedby': 'activityPreview networkCount',
        }),
    )
