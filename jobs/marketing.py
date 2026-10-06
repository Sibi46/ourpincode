"""Explicit shop grants and session-scoped marketing access."""
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path
from django.utils import timezone
from .models import User, MarketingAccess


class AgentForm(UserCreationForm):
    pincode = forms.RegexField(r'^[0-9]{6}$', max_length=6)
    phone = forms.RegexField(r'^[0-9]{10}$', max_length=10)

    class Meta:
        model = User
        fields = ['username', 'pincode', 'phone']

    def clean_phone(self):
        phone = self.cleaned_data['phone']
        if User.objects.filter(phone=phone).exists() or User.objects.filter(business_phone=phone).exists():
            raise forms.ValidationError('This phone number is already registered.')
        return phone


def shop_name(user):
    if hasattr(user, 'shop'):
        return user.shop.shop_name
    if hasattr(user, 'company'):
        return user.company.company_name
    return user.username


@login_required
def admin_agents(request):
    if not (request.user.is_superuser or request.user.is_super_admin()):
        return HttpResponseForbidden('Super admin access required.')
    form = AgentForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        agent = form.save(commit=False)
        agent.user_type = 'marketing_agent'
        agent.save()
        messages.success(request, 'Smart Marketing Agent created.')
        return redirect('marketing_admin')
    return render(request, 'marketing/admin.html', {'form': form, 'agents': User.objects.filter(user_type='marketing_agent')})


@login_required
def shop_access(request):
    if not request.user.is_employer():
        return HttpResponseForbidden('Business owner access required.')
    if request.method == 'POST':
        if request.POST.get('action') == 'revoke':
            MarketingAccess.objects.filter(shop=request.user, pk=request.POST.get('grant')).delete()
        else:
            agent = User.objects.filter(username=request.POST.get('username', '').strip(), user_type='marketing_agent', is_active=True).first()
            if agent:
                MarketingAccess.objects.get_or_create(shop=request.user, agent=agent)
                messages.success(request, 'Agent access granted.')
            else:
                messages.error(request, 'Active agent username not found.')
        return redirect('marketing_access')
    return render(request, 'marketing/access.html', {'grants': request.user.marketing_agents.select_related('agent')})


@login_required
def agent_dashboard(request):
    if request.user.user_type != 'marketing_agent' or not request.user.is_active:
        return HttpResponseForbidden('Agent access required.')
    grants = list(request.user.marketing_shops.filter(shop__is_active=True).select_related('shop', 'shop__shop', 'shop__company'))
    for grant in grants:
        grant.name = shop_name(grant.shop)
    return render(request, 'marketing/dashboard.html', {'grants': grants})


@login_required
def open_shop(request, pk):
    if request.user.user_type != 'marketing_agent' or not request.user.is_active:
        return HttpResponseForbidden('Agent access required.')
    grant = get_object_or_404(MarketingAccess, agent=request.user, shop_id=pk, shop__is_active=True)
    request.session.pop('marketing_shop', None)
    if request.method == 'POST':
        from .views import _rate_limit, _get_client_ip
        if not _rate_limit(f'marketing_unlock_{request.user.pk}_{_get_client_ip(request)}', max_attempts=5, window_seconds=300):
            messages.error(request, 'Too many attempts. Please wait five minutes.')
        else:
            phone = request.POST.get('phone', '').strip()
            if phone and phone in (grant.shop.phone, grant.shop.business_phone) and grant.shop.check_password(request.POST.get('password', '')):
                request.session.cycle_key()
                request.session['marketing_shop'] = {'grant': grant.pk, 'hash': grant.shop.get_session_auth_hash(), 'expires': timezone.now().timestamp() + 3600}
                return redirect('marketing_workspace')
            messages.error(request, 'Invalid shop phone number or password.')
    return render(request, 'marketing/unlock.html', {'shop_name': shop_name(grant.shop)})


def active_shop(request):
    state = request.session.get('marketing_shop', {})
    if state.get('expires', 0) <= timezone.now().timestamp():
        return None
    grant = MarketingAccess.objects.select_related('shop').filter(pk=state.get('grant'), agent=request.user, shop__is_active=True).first()
    if grant and grant.shop.is_employer() and grant.shop.get_session_auth_hash() == state.get('hash'):
        return grant.shop
    return None


@login_required
def workspace(request):
    if request.user.user_type != 'marketing_agent':
        return HttpResponseForbidden('Agent access required.')
    shop = active_shop(request)
    if not shop:
        return redirect('marketing_dashboard')
    from coupons.models import Coupon
    from .models import Flick
    return render(request, 'marketing/workspace.html', {'shop_name': shop_name(shop), 'shop': shop,
        'coupons': Coupon.objects.filter(batch__shop__business=shop)[:100], 'videos': Flick.objects.filter(user=shop)})


class MarketingMiddleware:
    """Keep the authenticated agent in the session; delegate only named marketing views."""
    allowed = {'offer_post', 'offer_post_success', 'my_offers', 'post_flick', 'delete_flick', 'opc_verify_redemption'} | {
        'vouchers:' + name for name in ('business_dashboard', 'voucher_list', 'voucher_create', 'voucher_edit', 'voucher_publish', 'voucher_pause', 'voucher_resume', 'voucher_delete')}

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        if not request.user.is_authenticated or request.user.user_type != 'marketing_agent':
            return None
        if not request.user.is_active:
            return HttpResponseForbidden('Agent account disabled.')
        name = request.resolver_match.view_name
        if name in self.allowed:
            shop = active_shop(request)
            if not shop:
                return redirect('marketing_dashboard')
            request.marketing_agent = request.user
            request.user = shop
        elif name not in {'marketing_dashboard', 'marketing_open', 'marketing_workspace', 'logout', 'login'}:
            return redirect('marketing_dashboard')


urlpatterns = [
    path('admin/', admin_agents, name='marketing_admin'),
    path('access/', shop_access, name='marketing_access'),
    path('', agent_dashboard, name='marketing_dashboard'),
    path('shops/<int:pk>/', open_shop, name='marketing_open'),
    path('workspace/', workspace, name='marketing_workspace'),
]
