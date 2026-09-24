from django import forms

from .models import CATEGORY_CHOICES


class CouponActivationForm(forms.Form):
    category = forms.ChoiceField(
        choices=[(code, f'{label} ({code})') for code, label in CATEGORY_CHOICES],
        initial='S',
        widget=forms.Select(attrs={'class': 'opc-input', 'id': 'couponCategory'}),
    )
    number = forms.RegexField(
        regex=r'\A[0-9]{1,10}\Z', max_length=10, label='Coupon number',
        error_messages={'invalid': 'Enter only the digits printed on your coupon.'},
        widget=forms.TextInput(attrs={
            'class': 'opc-input', 'id': 'couponNumber', 'inputmode': 'numeric',
            'pattern': '[0-9]{1,10}', 'placeholder': '000001',
            'autocomplete': 'off', 'aria-describedby': 'couponNumberHelp',
        }),
    )

    def clean_number(self):
        number = int(self.cleaned_data['number'])
        if not 1 <= number <= 2147483647:
            raise forms.ValidationError('Enter a valid coupon number greater than zero.')
        return number
