"""Isolated business workspaces accessed only through an authenticated owner."""
import uuid
from django import forms
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.crypto import constant_time_compare
from django.views.decorators.http import require_POST
from .models import User, CompanyProfile, ShopProfile, ManagedBusiness
from .business_categories import business_category_names

GRANT_KEY = 'managed_business_owner'
SALT = 'managed-business-owner-v1'


def business_owner(request):
    user = request.user
    if not user.is_authenticated or not user.is_active:
        raise PermissionDenied
    link = ManagedBusiness.objects.select_related('owner').filter(account=user).first()
    if not link:
        return user
    try:
        grant = signing.loads(request.session.get(GRANT_KEY, ''), salt=SALT, max_age=1209600)
        owner = link.owner
        if not owner.is_active or grant['owner'] != owner.pk or not constant_time_compare(grant['auth'], owner.get_session_auth_hash()):
            raise PermissionDenied
        return owner
    except (signing.BadSignature, KeyError, TypeError):
        raise PermissionDenied


def activate_business(request, owner, account):
    # A successful password-authenticated owner session grants only its own workspaces.
    login(request, account, backend='django.contrib.auth.backends.ModelBackend')
    request.session[GRANT_KEY] = signing.dumps({'owner': owner.pk, 'auth': owner.get_session_auth_hash()}, salt=SALT)


class ManagedBusinessSessionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
    def __call__(self, request):
        if request.user.is_authenticated and ManagedBusiness.objects.filter(account=request.user).exists():
            try:
                business_owner(request)
            except PermissionDenied:
                logout(request)
                return redirect('/login/')
        return self.get_response(request)


class AdditionalBusinessForm(forms.Form):
    name = forms.CharField(max_length=200, label='Business name')
    business_type = forms.ChoiceField(choices=User.USER_TYPES[:11], initial='shop')
    category = forms.ChoiceField(label='Business category')
    pincode = forms.RegexField(r'^[1-9][0-9]{5}$', max_length=6, label='PIN code', widget=forms.TextInput(attrs={'inputmode':'numeric','maxlength':6}))
    area = forms.CharField(max_length=100, label='Area / locality')
    address = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows':3}))
    logo = forms.ImageField(required=False)
    token = forms.CharField(widget=forms.HiddenInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].choices = [('', 'Select a business category')] + [(name,name) for name in business_category_names()]


@login_required
def add_business(request):
    owner = business_owner(request)
    if not (owner.is_employer() or CompanyProfile.objects.filter(user=owner).exists()):
        return redirect('/register/?type=company')
    if request.method == 'POST':
        form = AdditionalBusinessForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                token = signing.loads(form.cleaned_data['token'], salt='add-business', max_age=3600)
                if token['owner'] != owner.pk:
                    raise PermissionDenied
                nonce = uuid.UUID(token['nonce'])
            except (signing.BadSignature, ValueError, KeyError, TypeError):
                form.add_error(None, 'This form expired. Reload the page and try again.')
            else:
                with transaction.atomic():
                    owner = User.objects.select_for_update().get(pk=owner.pk, is_active=True)
                    link = ManagedBusiness.objects.filter(owner=owner, registration_token=nonce).select_related('account').first()
                    if link:
                        account = link.account
                    else:
                        data = form.cleaned_data
                        account = User(username='business-'+uuid.uuid4().hex, user_type=data['business_type'],
                            first_name=owner.first_name, last_name=owner.last_name, pincode=data['pincode'],
                            city=data['area'], address=data['address'])
                        from .utils import generate_biz_id
                        account.salesman_biz_id = generate_biz_id()
                        account.set_unusable_password()
                        account.save()
                        profile = CompanyProfile.objects.create(user=account, company_name=data['name'],
                            industry=data['category'], logo=data.get('logo'))
                        if account.user_type == 'shop':
                            ShopProfile.objects.create(user=account, shop_name=data['name'], shop_type=data['category'],
                                owner_name=owner.get_full_name(), logo=profile.logo)
                        ManagedBusiness.objects.create(owner=owner, account=account, registration_token=nonce)
                activate_business(request, owner, account)
                messages.success(request, 'Business added. You are now managing '+account.company.company_name+'.')
                return redirect('/employer/dashboard/')
    else:
        token = signing.dumps({'owner':owner.pk,'nonce':str(uuid.uuid4())}, salt='add-business')
        form = AdditionalBusinessForm(initial={'token':token})
    return render(request, 'add_business.html', {'form':form})


@login_required
@require_POST
def switch_business(request, account_id):
    owner = business_owner(request)
    if account_id == owner.pk:
        account = owner
    else:
        link = get_object_or_404(ManagedBusiness.objects.select_related('account'), owner=owner, account_id=account_id, account__is_active=True)
        account = link.account
    activate_business(request, owner, account)
    return redirect('/employer/dashboard/')


def workspace_context(request):
    if not request.user.is_authenticated or not request.user.is_active:
        return {}
    owner = business_owner(request)
    if not (owner.is_employer() or CompanyProfile.objects.filter(user=owner).exists()):
        return {}
    accounts = [owner] + [link.account for link in ManagedBusiness.objects.filter(owner=owner, account__is_active=True).select_related('account__company')]
    return {'business_workspaces': accounts, 'business_login_owner': owner}
