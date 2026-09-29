"""Explicitly scoped admin workspace; never grants global staff permissions."""
from datetime import timedelta
from functools import wraps

from django import forms
from django.apps import apps
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import AdminProfile, PinCode, State, User, UserNotification

# Model, geographic lookup, title, permitted moderation actions.
SECTIONS = {
    'jobs': ('Jobs', 'jobs.Job', 'pincode', 'title', ('approve', 'suspend')),
    'news': ('News', 'newsdesk.NewsItem', 'pincode__code', 'title', ('publish', 'unpublish')),
    'offers': ('Offers', 'jobs.LocalOffer', 'owner__pincode', 'title', ('activate', 'suspend')),
    'ads': ('Ads', 'jobs.AdPost', 'pincode', 'company_name', ('approve', 'reject')),
    'community': ('Communities', 'portal.Community', 'pincode', 'name', ('approve', 'suspend')),
    'quiz': ('Quiz', 'quiz.Quiz', 'pincode', 'title', ('activate', 'suspend')),
    'coupons': ('Coupon shops', 'coupons.Shop', 'pincode', 'name', ('activate', 'suspend')),
    'vouchers': ('Voucher businesses', 'vouchers.Business', 'pincode', 'business_name', ('approve', 'suspend')),
    'flicks': ('Flicks', 'jobs.Flick', 'user__pincode', 'title', ('delete',)),
}
SECTION_CHOICES = [(key, value[0]) for key, value in SECTIONS.items()]


class AssignedAdminMiddleware:
    """Fail closed: legacy admin endpoints must not bypass assigned permissions."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        if not request.user.is_authenticated or request.user.admin_role != 'scoped_admin':
            return None
        name = request.resolver_match.url_name
        allowed = {'assigned_dashboard', 'assigned_section', 'assigned_action', 'dashboard', 'logout'}
        if name not in allowed:
            if request.method in ('GET', 'HEAD'):
                return redirect('assigned_dashboard')
            raise PermissionDenied('Use your assigned admin workspace.')


def main_admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(request, *args, **kwargs):
        if not request.user.is_active or request.user.admin_role != 'super_admin':
            raise PermissionDenied
        return view(request, *args, **kwargs)
    return wrapped


def profile_for(user):
    if not user.is_authenticated or not user.is_active:
        raise PermissionDenied
    if user.admin_role == 'super_admin':
        return None
    if user.admin_role != 'scoped_admin':
        raise PermissionDenied
    profile = get_object_or_404(AdminProfile.objects.select_related('state'), user=user, role='scoped_admin', is_active=True)
    if not profile.all_states and (not profile.state_id or not profile.state.is_active):
        raise PermissionDenied('Your state assignment is unavailable. Contact the Main Super Admin.')
    return profile


def scoped_records(user, section):
    profile = profile_for(user)
    if section not in SECTIONS or (profile and section not in profile.sections):
        raise PermissionDenied('This section has not been assigned to you.')
    _, model, location, _, _ = SECTIONS[section]
    records = apps.get_model(model).objects.all()
    if profile and not profile.all_states:
        pins = PinCode.objects.filter(district__state_id=profile.state_id).values('code')
        records = records.filter(**{location + '__in': pins})
    return records


class ScopeForm(forms.ModelForm):
    sections = forms.MultipleChoiceField(choices=SECTION_CHOICES, widget=forms.CheckboxSelectMultiple)
    class Meta:
        model = AdminProfile
        fields = ('all_states', 'state', 'sections')
        labels = {'all_states': 'All states / national section admin', 'state': 'Assigned state'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['state'].queryset = State.objects.filter(is_active=True).exclude(code='UNASN')
        self.fields['state'].required = False

    def clean(self):
        data = super().clean()
        if not data.get('all_states') and not data.get('state'):
            self.add_error('state', 'Select a state, or choose all states.')
        if data.get('all_states'):
            data['state'] = None
        return data


class AdminAccountForm(UserCreationForm):
    phone = forms.RegexField(r'^[0-9]{10}$', label='Mobile number', max_length=10)
    first_name = forms.CharField(label='Name', max_length=150)
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('first_name', 'phone')

    def clean_phone(self):
        phone = self.cleaned_data['phone']
        if User.objects.filter(Q(username=phone) | Q(phone=phone) | Q(business_phone=phone)).exists():
            raise forms.ValidationError('This mobile number already belongs to an account.')
        self.instance.username = phone
        return phone


@main_admin_required
def manage_admins(request):
    account_form = AdminAccountForm(request.POST if request.method == 'POST' else None)
    scope_form = ScopeForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST':
        valid_account = account_form.is_valid()
        valid_scope = scope_form.is_valid()
        if valid_account and valid_scope:
            with transaction.atomic():
                user = account_form.save(commit=False)
                user.admin_role = 'scoped_admin'
                user.is_staff = user.is_superuser = False
                user.save()
                profile = scope_form.save(commit=False)
                profile.user = user
                profile.role = 'scoped_admin'
                profile.appointed_by = request.user
                profile.save()
                UserNotification.objects.create(user=user, title='Your admin access is ready', message='Sign in with your mobile number and password to manage your assigned sections.')
            messages.success(request, f'Admin created. Login mobile: {user.phone}.')
            return redirect('manage_assigned_admins')
    admins = AdminProfile.objects.filter(role='scoped_admin').select_related('user', 'state')
    for admin in admins:
        admin.section_labels = ', '.join(SECTIONS[s][0] for s in admin.sections if s in SECTIONS)
    return render(request, 'assigned_admin/manage.html', {'account_form': account_form, 'scope_form': scope_form, 'admins': admins})


@main_admin_required
def edit_admin(request, pk):
    profile = get_object_or_404(AdminProfile, pk=pk, role='scoped_admin', user__admin_role='scoped_admin')
    form = ScopeForm(request.POST if request.method == 'POST' else None, instance=profile)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Admin permissions updated. They apply immediately.')
        return redirect('manage_assigned_admins')
    return render(request, 'assigned_admin/edit.html', {'scope_form': form, 'profile': profile})


@main_admin_required
@require_POST
def toggle_assigned_admin(request, pk):
    with transaction.atomic():
        profile = get_object_or_404(AdminProfile.objects.select_for_update(), pk=pk, role='scoped_admin', user__admin_role='scoped_admin')
        profile.is_active = not profile.is_active
        profile.save(update_fields=['is_active'])
        User.objects.filter(pk=profile.user_id).update(is_active=profile.is_active)
    messages.success(request, 'Admin access updated.')
    return redirect('manage_assigned_admins')


@login_required
def assigned_dashboard(request):
    profile = profile_for(request.user)
    sections = [{'key': key, 'name': value[0], 'count': scoped_records(request.user, key).count()}
                for key, value in SECTIONS.items() if profile is None or key in profile.sections]
    return render(request, 'assigned_admin/dashboard.html', {
        'profile': profile, 'sections': sections,
        'notifications': UserNotification.objects.filter(user=request.user)[:5],
    })


@login_required
def assigned_section(request, section):
    records = scoped_records(request.user, section)
    label, _, _, title, actions = SECTIONS[section]
    search = request.GET.get('q', '').strip()[:150]
    if search:
        records = records.filter(**{title + '__icontains': search})
    page = Paginator(records.order_by('-pk'), 25).get_page(request.GET.get('page'))
    for obj in page:
        obj.admin_title = getattr(obj, title) or f'{label} #{obj.pk}'
        obj.admin_status = getattr(obj, 'status', None)
        if obj.admin_status is None:
            obj.admin_status = 'Active' if getattr(obj, 'is_active', True) else 'Suspended'
        obj.admin_detail = getattr(obj, 'body', '') or getattr(obj, 'description', '') or getattr(obj, 'caption', '')
    return render(request, 'assigned_admin/section.html', {'page': page, 'section': section, 'label': label, 'actions': actions, 'search': search})


@login_required
@require_POST
@transaction.atomic
def assigned_action(request, section, pk):
    records = scoped_records(request.user, section)
    obj = get_object_or_404(records.select_for_update(), pk=pk)
    action = request.POST.get('action')
    if action not in SECTIONS[section][4]:
        raise PermissionDenied('Unsupported action.')
    if section == 'jobs':
        obj.is_approved = action == 'approve'
        obj.status = 'active' if action == 'approve' else 'closed'
        # QuerySet update avoids the unrelated geocoding performed by Job.save.
        records.filter(pk=pk).update(is_approved=obj.is_approved, status=obj.status)
        UserNotification.objects.create(user=obj.posted_by, title=f'Job {action}d: {obj.title}', message='Your job was reviewed by an administrator. Open your dashboard to see its status and select a plan.', link=f'/jobs/{pk}/select-plan/')
    elif section == 'news':
        obj.status = 'published' if action == 'publish' else 'draft'
        try:
            obj.clean()
        except ValidationError as error:
            messages.error(request, ' '.join(error.messages))
            return redirect('assigned_section', section=section)
        obj.save(update_fields=['status', 'updated_at'])
    elif section == 'ads':
        obj.status = 'approved' if action == 'approve' else 'rejected'
        if action == 'approve':
            from .models import AdSettings
            obj.approved_at = timezone.now()
            obj.expires_at = timezone.localdate() + timedelta(days=AdSettings.get().renewal_days)
            obj.reject_note = ''
        obj.save()
        UserNotification.objects.create(user=obj.user, title=f'Ad {obj.status}', message=f'Your ad "{obj.company_name}" was reviewed by an administrator.')
    elif section == 'vouchers':
        obj.status = 'approved' if action == 'approve' else 'suspended'
        if action == 'approve':
            obj.approved_by = request.user
            obj.approved_at = timezone.now()
        obj.save()
    elif section == 'flicks':
        if request.POST.get('confirm') != 'yes':
            raise PermissionDenied('Confirm deletion first.')
        obj.delete()
    else:
        obj.is_active = action in ('activate', 'approve')
        if section == 'community' and action == 'approve':
            obj.is_verified = True
        obj.save()
    messages.success(request, 'Saved successfully.')
    return redirect('assigned_section', section=section)


urlpatterns = [
    path('super-admin/team/', manage_admins, name='manage_assigned_admins'),
    path('super-admin/team/<int:pk>/edit/', edit_admin, name='edit_assigned_admin'),
    path('super-admin/team/<int:pk>/toggle/', toggle_assigned_admin, name='toggle_assigned_admin'),
    path('admin-workspace/', assigned_dashboard, name='assigned_dashboard'),
    path('admin-workspace/<slug:section>/', assigned_section, name='assigned_section'),
    path('admin-workspace/<slug:section>/<int:pk>/action/', assigned_action, name='assigned_action'),
]
