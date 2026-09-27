from django import forms


class NetworkPostForm(forms.Form):
    category = forms.ChoiceField(
        required=False, label='Post category',
        choices=[('', 'Auto-detect from text'), ('sports', 'Sports'), ('food', 'Food'),
                 ('health', 'Health'), ('transport', 'Transport'), ('rent', 'Rent'),
                 ('training', 'Training'), ('music', 'Music')],
        widget=forms.Select(attrs={'id': 'networkCategory'}),
    )
    text = forms.CharField(
        max_length=500, label='What would you like to do?',
        widget=forms.Textarea(attrs={
            'rows': 4, 'id': 'networkText', 'placeholder': "I'm free now. Anyone up for cricket?",
            'aria-describedby': 'activityPreview networkCount',
        }),
    )
