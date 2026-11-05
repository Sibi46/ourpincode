"""Account settings, saved discovery areas and business follows."""
import re

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .models import BusinessFollow, CompanyProfile, JobSeekerProfile, User

PIN = re.compile(r'[1-9][0-9]{5}')


class ProfileValidationMixin:
    name_fields = ()
    text_fields = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in self.name_fields:
            self.fields[name].widget.attrs.update({'data-person-name': '', 'pattern': r'[\p{L}\p{M} ]+', 'title': 'Use letters and spaces only.'})
        for name in self.text_fields:
            self.fields[name].widget.attrs.update({'data-no-digits': '', 'pattern': r'[^\p{N}]*', 'title': 'Numbers are not allowed in this field.'})

    def clean(self):
        from .person_names import valid_person_name
        import unicodedata
        data = super().clean()
        for name in self.name_fields:
            if data.get(name) and not valid_person_name(data[name]):
                self.add_error(name, 'Use letters and spaces only.')
        for name in self.text_fields:
            if data.get(name) and any(unicodedata.category(c).startswith('N') for c in data[name]):
                self.add_error(name, 'Numbers are not allowed in this field.')
        return data


class LocationPreferencesForm(forms.Form):
    pincode = forms.RegexField(PIN, required=False, max_length=6, label='Main pincode')
    preferred_pincode_1 = forms.RegexField(PIN, required=False, max_length=6, label='Preferred area 1')
    preferred_pincode_2 = forms.RegexField(PIN, required=False, max_length=6, label='Preferred area 2')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'inputmode': 'numeric', 'pattern': '[1-9][0-9]{5}', 'maxlength': '6', 'data-digits-only': ''})

    def clean(self):
        data = super().clean()
        pins = [value for value in data.values() if value]
        if len(pins) != len(set(pins)):
            raise forms.ValidationError('Choose different pincodes for your main and preferred areas.')
        if any(data.get(key) for key in ('preferred_pincode_1', 'preferred_pincode_2')) and not data.get('pincode'):
            self.add_error('pincode', 'Add your main pincode before saving preferred areas.')
        return data


class BusinessDetailsForm(forms.ModelForm):
    review_reward_percent = forms.IntegerField(required=False, min_value=0, max_value=50)

    class Meta:
        model = CompanyProfile
        fields = ['company_name', 'description', 'industry', 'company_size', 'website', 'logo', 'banner_image', 'review_reward_percent']

    def clean_review_reward_percent(self):
        return self.cleaned_data.get('review_reward_percent') or 0


class DashboardPersonalForm(ProfileValidationMixin, forms.ModelForm):
    name_fields = ('first_name', 'last_name')
    text_fields = ('city',)
    photo = forms.ImageField(required=False, label='Personal profile photo')
    whatsapp = forms.RegexField(r'[0-9]{10}', required=False, label='WhatsApp contact number',
        widget=forms.TextInput(attrs={'inputmode': 'numeric', 'pattern': '[0-9]{10}', 'maxlength': '10', 'data-digits-only': ''}),
        error_messages={'invalid': 'Enter a 10-digit WhatsApp number.'})

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'whatsapp', 'city', 'address', 'photo']


class DashboardSeekerForm(ProfileValidationMixin, forms.ModelForm):
    text_fields = ('languages', 'preferred_roles', 'preferred_location', 'education', 'education_details', 'primary_skill', 'skills')
    BLUE_TYPES = [('construction', 'Construction'), ('electrician', 'Electrician'), ('plumber', 'Plumber'),
        ('driver', 'Driver / Delivery'), ('factory', 'Factory / Production'), ('security', 'Security'),
        ('domestic', 'Domestic work'), ('agriculture', 'Agriculture'), ('welder', 'Welder'),
        ('painter', 'Painter'), ('helper', 'Helper'), ('sweeper', 'Housekeeping'), ('tailor', 'Tailor'),
        ('mechanic', 'Mechanic'), ('other_blue', 'Other blue collar')]
    WHITE_TYPES = [('software', 'Software / IT'), ('accounting', 'Accounting / Finance'),
        ('administration', 'Administration'), ('sales', 'Sales'), ('marketing', 'Marketing'),
        ('human_resources', 'Human resources'), ('teaching', 'Teaching'), ('healthcare', 'Healthcare'),
        ('customer_service', 'Customer service'), ('other_white', 'Other white collar')]
    blue_collar_type = forms.ChoiceField(required=False, label='Job type', choices=[('', 'Choose a job type')])
    dob = forms.DateField(
        required=False, label='Date of birth',
        input_formats=['%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'],
        widget=forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date', 'autocomplete': 'bday'}),
        error_messages={'invalid': 'Enter a valid date of birth using the date picker.'},
    )

    class Meta:
        model = JobSeekerProfile
        fields = ['dob', 'gender', 'experience', 'education', 'education_details', 'primary_skill',
                  'skills', 'languages', 'preferred_roles', 'preferred_location', 'open_to_relocate',
                  'job_category', 'blue_collar_type', 'salary_min', 'portfolio_url', 'resume']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        category = self.data.get('job_category', self.instance.job_category) if self.is_bound else self.instance.job_category
        options = self.WHITE_TYPES if category == 'white' else self.BLUE_TYPES if category == 'blue' else self.BLUE_TYPES + self.WHITE_TYPES
        self.fields['blue_collar_type'].choices = [('', 'Choose a job type')] + options
        self.fields['blue_collar_type'].widget.attrs['data-job-type'] = ''
        self.fields['job_category'].widget.attrs['data-job-category'] = ''


def dashboard_profile_context(user, company):
    seeker = getattr(user, 'seeker', None)
    return {'company': company, 'business_form': BusinessDetailsForm(instance=company) if company else None,
            'personal_form': DashboardPersonalForm(instance=user),
            'seeker_form': DashboardSeekerForm(instance=seeker) if seeker else None,
            'location_form': LocationPreferencesForm(initial={field: getattr(user, field) for field in LocationPreferencesForm.base_fields}),
            'account_features': profile_features(user), 'following_count': user.business_follows.count(),
            'business_follower_count': company.followers.count() if company else 0}


def selected_area(request):
    """An explicit filter wins; otherwise use the chosen area or resident pincode."""
    explicit = request.GET.get('pincode')
    if explicit is not None:
        explicit = explicit.strip()
        if not explicit or PIN.fullmatch(explicit):
            request.session['active_pincode'] = explicit
            request.session['offers_pincode'] = explicit
            request.session['news_pincode'] = explicit
            return explicit
    user = request.user
    return request.session.get('active_pincode', user.pincode if user.is_authenticated else '')


def safe_return(request, default='/profile/edit/'):
    target = request.POST.get('next') or request.GET.get('next', '')
    return target if target.startswith('/') and url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()) else default


@require_POST
def select_area(request):
    code = request.POST.get('pincode', '').strip()
    if not PIN.fullmatch(code):
        messages.error(request, 'Enter a valid six-digit pincode.')
        return redirect(safe_return(request, '/'))
    request.session['active_pincode'] = code
    request.session['offers_pincode'] = code
    request.session['news_pincode'] = code
    if request.user.is_authenticated and not request.user.pincode:
        request.user.pincode = code
        request.user.save(update_fields=['pincode'])
    return redirect(safe_return(request, '/'))


@login_required
@require_POST
def follow_business(request, company_id):
    company = get_object_or_404(CompanyProfile, company_id=company_id, user__is_active=True)
    if company.user_id == request.user.pk:
        return JsonResponse({'error': 'You cannot follow your own business.'}, status=400)
    action = request.POST.get('action')
    if action not in ('follow', 'unfollow'):
        return JsonResponse({'error': 'Choose follow or unfollow.'}, status=400)
    if action == 'follow':
        BusinessFollow.objects.get_or_create(company=company, user=request.user)
    else:
        BusinessFollow.objects.filter(company=company, user=request.user).delete()
    data = {'following': action == 'follow', 'followers': company.followers.count()}
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse(data)
    return redirect(safe_return(request, company.get_absolute_url()))


def profile_features(user):
    from .features import FEATURES
    links = [{'name': 'My dashboard', 'url': '/dashboard/'},
             {'name': 'Following businesses', 'url': '/businesses/?following=1&pincode='},
             {'name': 'My accounts', 'url': '/my-accounts/'},
             {'name': 'Refer & Earn', 'url': '/referral/'}]
    if user.is_employer() or CompanyProfile.objects.filter(user=user).exists():
        links += [{'name': name, 'url': '/employer/dashboard/#' + section} for name, section in [
            ('Business dashboard', 'active-jobs'), ('Job applications', 'applications'),
            ('Job approvals & drafts', 'approval-pending'), ('Business gallery', 'gallery'),
            ('Business coupons', 'coupons'), ('Notifications', 'notifications'),
            ('Wallet', 'wallet'), ('Billing', 'billing')]]
    else:
        links.append({'name': 'Jobseeker dashboard', 'url': '/jobseeker/dashboard/'})
    links += [{'name': item['name'], 'url': item['url']} for item in FEATURES if item['name'] != 'My Profile']
    return links
