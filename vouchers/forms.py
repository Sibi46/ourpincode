from django import forms
from jobs.profile_validation import ProfileValidationMixin
from jobs.form_fields import FourDigitYearDateField
from .models import Business, BusinessCategory, Branch, Employee, VoucherSlotPurchase, GiftVoucher, VoucherCategory


class BusinessRegistrationForm(ProfileValidationMixin, forms.ModelForm):
    person_fields = ('owner_name', 'city', 'state')
    class Meta:
        model = Business
        fields = [
            'business_name', 'owner_name', 'category',
            'mobile', 'email', 'website', 'description',
            'address', 'pincode', 'city', 'state',
            'gst_number', 'pan_number',
            'logo', 'cover_image',
            'facebook', 'instagram', 'twitter',
        ]
        widgets = {
            'business_name': forms.TextInput(attrs={'placeholder': 'Enter your business name'}),
            'owner_name':    forms.TextInput(attrs={'placeholder': 'Full name of business owner'}),
            'mobile':        forms.TextInput(attrs={'placeholder': '10-digit mobile number'}),
            'email':         forms.EmailInput(attrs={'placeholder': 'business@email.com'}),
            'website':       forms.URLInput(attrs={'placeholder': 'https://yourwebsite.com (optional)'}),
            'address':       forms.Textarea(attrs={'rows': 3, 'placeholder': 'Full business address'}),
            'pincode':       forms.TextInput(attrs={'placeholder': '6-digit pincode', 'maxlength': '10'}),
            'city':          forms.TextInput(attrs={'placeholder': 'City'}),
            'state':         forms.TextInput(attrs={'placeholder': 'State'}),
            'gst_number':    forms.TextInput(attrs={'placeholder': 'GST number (optional)'}),
            'pan_number':    forms.TextInput(attrs={'placeholder': 'PAN number (optional)'}),
            'description':   forms.Textarea(attrs={'rows': 4, 'placeholder': 'Brief description of your business'}),
            'facebook':      forms.URLInput(attrs={'placeholder': 'Facebook page URL (optional)'}),
            'instagram':     forms.URLInput(attrs={'placeholder': 'Instagram profile URL (optional)'}),
            'twitter':       forms.URLInput(attrs={'placeholder': 'Twitter/X profile URL (optional)'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].queryset = BusinessCategory.objects.filter(is_active=True)
        self.fields['category'].empty_label = '— Select Category —'
        for name, field in self.fields.items():
            if isinstance(field.widget, (forms.TextInput, forms.EmailInput,
                                         forms.URLInput, forms.Textarea, forms.Select)):
                existing = field.widget.attrs.get('class', '')
                field.widget.attrs['class'] = (existing + ' form-control').strip()


class BranchForm(ProfileValidationMixin, forms.ModelForm):
    person_fields = ('branch_name',)
    pincode = forms.RegexField(r'^[1-9][0-9]{5}$', max_length=6, label='Pincode',
        widget=forms.TextInput(attrs={'inputmode': 'numeric', 'maxlength': '6', 'pattern': '[1-9][0-9]{5}', 'data-digits-only': ''}))
    contact_number = forms.RegexField(r'^[0-9]{10}$', min_length=10, max_length=10, label='Contact number',
        widget=forms.TextInput(attrs={'inputmode': 'numeric', 'maxlength': '10', 'pattern': '[0-9]{10}', 'data-digits-only': ''}),
        error_messages={'invalid': 'Enter exactly 10 numeric digits.'})

    def clean_address(self):
        value = self.cleaned_data['address'].strip()
        if not any(c.isalpha() for c in value):
            raise forms.ValidationError('Enter an address with a street, area or locality name.')
        return value
    class Meta:
        model = Branch
        fields = ['branch_name', 'address', 'pincode', 'contact_number', 'working_hours', 'is_active']
        widgets = {
            'branch_name':    forms.TextInput(attrs={'placeholder': 'e.g. Main Branch, Anna Nagar Branch'}),
            'address':        forms.Textarea(attrs={'rows': 3, 'placeholder': 'Full branch address', 'data-address-text': ''}),
            'pincode':        forms.TextInput(attrs={'placeholder': '6-digit pincode', 'maxlength': '10'}),
            'contact_number': forms.TextInput(attrs={'placeholder': '10-digit contact number'}),
            'working_hours':  forms.TextInput(attrs={'placeholder': 'e.g. Mon–Sat 9am–6pm'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if isinstance(field.widget, (forms.TextInput, forms.Textarea, forms.CheckboxInput)):
                if not isinstance(field.widget, forms.CheckboxInput):
                    existing = field.widget.attrs.get('class', '')
                    field.widget.attrs['class'] = (existing + ' form-control').strip()
class EmployeeForm(forms.ModelForm):
    class Meta:
        model = Employee
        fields = ['name', 'mobile', 'email', 'role', 'assigned_branch', 'is_active']
        widgets = {
            'name':   forms.TextInput(attrs={'placeholder': 'Full name'}),
            'mobile': forms.TextInput(attrs={'placeholder': '10-digit mobile number'}),
            'email':  forms.EmailInput(attrs={'placeholder': 'employee@email.com'}),
        }

    def __init__(self, business, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['assigned_branch'].queryset = Branch.objects.filter(business=business, is_active=True)
        self.fields['assigned_branch'].empty_label = '— No specific branch —'
        self.fields['assigned_branch'].required = False
        for name, field in self.fields.items():
            if isinstance(field.widget, (forms.TextInput, forms.EmailInput, forms.Select)):
                existing = field.widget.attrs.get('class', '')
                field.widget.attrs['class'] = (existing + ' form-control').strip()


SLOT_PACKAGES = [
    {'id': '5',  'slots': 5,  'price': 999,  'label': '5 Slots',  'per_slot': 199, 'tag': ''},
    {'id': '10', 'slots': 10, 'price': 1799, 'label': '10 Slots', 'per_slot': 179, 'tag': 'Popular'},
    {'id': '20', 'slots': 20, 'price': 3299, 'label': '20 Slots', 'per_slot': 164, 'tag': 'Best Value'},
    {'id': '50', 'slots': 50, 'price': 7499, 'label': '50 Slots', 'per_slot': 149, 'tag': ''},
]

SLOT_PACKAGE_MAP = {p['id']: p for p in SLOT_PACKAGES}


class SlotRequestForm(forms.Form):
    PACKAGE_CHOICES = [(p['id'], p['label']) for p in SLOT_PACKAGES]
    package           = forms.ChoiceField(choices=PACKAGE_CHOICES, widget=forms.RadioSelect)
    payment_reference = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={
            'placeholder': 'UPI transaction ID / Bank transfer UTR number',
            'class': 'form-control',
        })
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 2,
            'placeholder': 'Any additional notes (optional)',
            'class': 'form-control',
        })
    )


class GiftVoucherForm(forms.ModelForm):
    valid_from = FourDigitYearDateField(widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}, format='%Y-%m-%d'))
    expiry_date = FourDigitYearDateField(widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}, format='%Y-%m-%d'))
    class Meta:
        model = GiftVoucher
        fields = [
            'voucher_name', 'product_service_name',
            'category', 'voucher_value', 'description',
            'terms_conditions', 'valid_from', 'expiry_date',
            'applicable_branches', 'total_quantity',
            'product_image', 'header_image',
        ]
        widgets = {
            'voucher_name':         forms.TextInput(attrs={'placeholder': 'e.g. Diwali Special Gift', 'class': 'form-control'}),
            'product_service_name': forms.TextInput(attrs={'placeholder': 'e.g. Dinner for Two', 'class': 'form-control'}),
            'voucher_value':        forms.NumberInput(attrs={'placeholder': '500', 'class': 'form-control'}),
            'description':          forms.Textarea(attrs={'rows': 3, 'placeholder': 'What does this voucher offer?', 'class': 'form-control'}),
            'terms_conditions':     forms.Textarea(attrs={'rows': 3, 'placeholder': 'Terms and conditions...', 'class': 'form-control'}),
            'valid_from':           forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'expiry_date':          forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'total_quantity':       forms.NumberInput(attrs={'placeholder': '100', 'class': 'form-control'}),
            'applicable_branches':  forms.CheckboxSelectMultiple(),
        }

    def __init__(self, business, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['applicable_branches'].queryset = Branch.objects.filter(business=business)
        self.fields['applicable_branches'].required = False
        self.fields['category'].queryset = VoucherCategory.objects.filter(is_active=True)
        self.fields['category'].empty_label = '— Select Category —'
        self.fields['category'].required = False
        self.fields['category'].widget.attrs['class'] = 'form-control'


class VoucherPurchaseForm(forms.Form):
    buyer_name   = forms.CharField(max_length=100, widget=forms.TextInput(attrs={'placeholder': 'Your full name', 'class': 'form-control'}))
    buyer_mobile = forms.CharField(max_length=15,  widget=forms.TextInput(attrs={'placeholder': 'Your mobile number', 'class': 'form-control'}))
    buyer_email  = forms.EmailField(widget=forms.EmailInput(attrs={'placeholder': 'Your email address', 'class': 'form-control'}))

    receiver_name    = forms.CharField(max_length=100, widget=forms.TextInput(attrs={'placeholder': "Receiver's full name", 'class': 'form-control'}))
    receiver_mobile  = forms.CharField(max_length=15,  widget=forms.TextInput(attrs={'placeholder': "Receiver's mobile number", 'class': 'form-control'}))
    receiver_email   = forms.EmailField(widget=forms.EmailInput(attrs={'placeholder': "Receiver's email address", 'class': 'form-control'}))
    personal_message = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 3, 'placeholder': 'Write a personal message (optional)', 'class': 'form-control'})
    )
