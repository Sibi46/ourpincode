"""Employer account destinations with explicit availability and ownership checks."""
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET
from .models import CompanyProfile, PaymentPlan, Wallet


def require_business(user):
    if not user.is_active or not (user.is_employer() or CompanyProfile.objects.filter(user=user).exists()):
        raise PermissionDenied


@login_required
@require_GET
def wallet_action(request, action):
    require_business(request.user)
    wallet = Wallet.objects.filter(user=request.user).first()
    title = 'Add Money' if action == 'add-money' else 'Withdraw'
    return render(request, 'account_service_status.html', {
        'title': title, 'wallet': wallet,
        'notice': f'{title} is temporarily unavailable. Please contact support before making a payment or requesting a withdrawal.',
        'return_url': '/employer/dashboard/#wallet',
    })


@login_required
@require_GET
def subscription_plan(request, pk):
    require_business(request.user)
    plan = get_object_or_404(PaymentPlan, pk=pk, is_active=True, plan_type__startswith='employer')
    return render(request, 'account_service_status.html', {
        'title': plan.name, 'plan': plan,
        'notice': 'Online subscription activation is not available yet. Please contact support to activate this plan. No payment has been taken.',
        'return_url': '/employer/dashboard/#subscription',
    })


@login_required
@require_GET
def subscription_renew(request):
    require_business(request.user)
    return redirect('/employer/dashboard/#subscription')


@login_required
@require_GET
def business_coupon(request, pk):
    from coupons.models import Coupon
    coupon = get_object_or_404(Coupon.objects.select_related('batch__shop', 'batch__salesman__user'),
                              pk=pk, batch__shop__business=request.user, deleted_at__isnull=True)
    return render(request, 'business_coupon_detail.html', {'coupon': coupon})
