import random
import decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.http import require_POST, require_http_methods
from django.db import transaction
from django.db.models import Sum, Count, Q
from django.utils import timezone
from django.contrib.auth import get_user_model

from .models import (
    Salesman, Shop, CouponBatch, Coupon, CouponCounter,
    SpinWheelSlot, Reward, PointsWallet, PointsTransaction,
    RedemptionCounter, Redemption,
)

from jobs.models import ShopProfile

User = get_user_model()


# ── helpers ──────────────────────────────────────────────────────────────────

def _is_opc_admin(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser)


def _is_salesman(user):
    return user.is_authenticated and hasattr(user, 'salesman_profile')


def opc_admin_required(view_fn):
    from functools import wraps
    @wraps(view_fn)
    def _wrap(request, *args, **kwargs):
        if not _is_opc_admin(request.user):
            return redirect('/coupons/admin/login/')
        return view_fn(request, *args, **kwargs)
    return _wrap


def salesman_required(view_fn):
    from functools import wraps
    @wraps(view_fn)
    def _wrap(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('/coupons/salesman/login/')
        if not _is_salesman(request.user):
            messages.error(request, 'Salesman access required.')
            return redirect('/coupons/salesman/login/')
        return view_fn(request, *args, **kwargs)
    return _wrap


def _notify_user(user, notif_type, message, url=''):
    """Send a notification via portal's _notify helper if available."""
    try:
        from portal.views import _notify
        _notify(user, notif_type, message, url)
    except Exception:
        pass


def _spin_result():
    """Pick a spin result based on configured probabilities."""
    slots = list(SpinWheelSlot.objects.filter(is_active=True))
    if not slots:
        return {'points': 10, 'label': '10 Points', 'is_surprise': False}
    total = sum(float(s.probability) for s in slots)
    r = random.uniform(0, total)
    cumulative = 0
    for slot in slots:
        cumulative += float(slot.probability)
        if r <= cumulative:
            return {
                'points': slot.points,
                'label': slot.label,
                'is_surprise': slot.is_surprise,
                'surprise_gift_name': slot.surprise_gift_name,
                'color': slot.color,
            }
    last = slots[-1]
    return {'points': last.points, 'label': last.label, 'is_surprise': last.is_surprise,
            'surprise_gift_name': last.surprise_gift_name, 'color': last.color}


# ═══════════════════════════════════════════════════════════════════════════════
# ADMIN VIEWS
# ═══════════════════════════════════════════════════════════════════════════════

@opc_admin_required
def admin_dashboard(request):
    ctx = {
        'total_salesmen': Salesman.objects.count(),
        'total_shops': Shop.objects.count(),
        'total_coupons_given': CouponBatch.objects.aggregate(t=Sum('quantity'))['t'] or 0,
        'total_activated': Coupon.objects.filter(status='activated').count(),
        'total_points_issued': PointsTransaction.objects.filter(type='credit').aggregate(t=Sum('amount'))['t'] or 0,
        'total_redemptions': Redemption.objects.count(),
        'recent_activations': Coupon.objects.filter(status='activated').select_related(
            'activated_by', 'batch__shop', 'batch__salesman__user').order_by('-activated_at')[:10],
    }
    return render(request, 'coupons/admin/dashboard.html', ctx)


@opc_admin_required
def admin_salesmen(request):
    salesmen = Salesman.objects.select_related('user').annotate(
        shop_count=Count('shops', distinct=True),
        coupon_count=Sum('batches__quantity'),
    )
    return render(request, 'coupons/admin/salesmen.html', {'salesmen': salesmen})


@opc_admin_required
def admin_salesman_create(request):
    if request.method == 'POST':
        full_name = request.POST.get('full_name', '').strip()
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()
        notes = request.POST.get('notes', '').strip()
        if not full_name or not username or not password:
            messages.error(request, 'All fields required.')
            return redirect('opc_admin_salesman_create')
        if User.objects.filter(username=username).exists():
            messages.error(request, 'Username already taken.')
            return redirect('opc_admin_salesman_create')
        parts = full_name.split(' ', 1)
        user = User.objects.create_user(
            username=username, password=password,
            first_name=parts[0], last_name=parts[1] if len(parts) > 1 else '',
        )
        Salesman.objects.create(user=user, created_by=request.user, notes=notes)
        messages.success(request, f'Salesman {full_name} created.')
        return redirect('opc_admin_salesmen')
    return render(request, 'coupons/admin/salesman_create.html')


@opc_admin_required
def admin_salesman_detail(request, pk):
    salesman = get_object_or_404(Salesman, pk=pk)
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'toggle':
            salesman.is_active = not salesman.is_active
            salesman.save()
            messages.success(request, 'Status updated.')
        elif action == 'reset_password':
            new_pw = request.POST.get('new_password', '').strip()
            if new_pw:
                salesman.user.set_password(new_pw)
                salesman.user.save()
                messages.success(request, 'Password reset.')
        elif action == 'edit':
            full_name = request.POST.get('full_name', '').strip()
            notes = request.POST.get('notes', '').strip()
            if full_name:
                parts = full_name.split(' ', 1)
                salesman.user.first_name = parts[0]
                salesman.user.last_name = parts[1] if len(parts) > 1 else ''
                salesman.user.save()
            salesman.notes = notes
            salesman.save()
            messages.success(request, 'Salesman updated.')
        return redirect('opc_admin_salesman_detail', pk=pk)
    shops = salesman.shops.prefetch_related('batches').all()
    return render(request, 'coupons/admin/salesman_detail.html', {
        'salesman': salesman, 'shops': shops
    })


@opc_admin_required
def admin_shops(request):
    q = request.GET.get('q', '')
    shops = Shop.objects.select_related('salesman__user').annotate(
        coupon_count=Sum('batches__quantity')
    )
    if q:
        shops = shops.filter(Q(name__icontains=q) | Q(pincode__icontains=q))
    return render(request, 'coupons/admin/shops.html', {'shops': shops, 'q': q})


@opc_admin_required
def admin_coupons(request):
    q = request.GET.get('q', '')
    status_f = request.GET.get('status', '')
    coupons = Coupon.objects.select_related(
        'batch__shop__salesman__user', 'activated_by'
    ).order_by('number')
    if q:
        coupons = coupons.filter(code__icontains=q)
    if status_f:
        coupons = coupons.filter(status=status_f)
    return render(request, 'coupons/admin/coupons.html', {
        'coupons': coupons[:200], 'q': q, 'status_f': status_f
    })


@opc_admin_required
def admin_coupon_audit(request):
    coupon = None
    q = request.GET.get('q', '').strip().upper()
    if q:
        coupon = Coupon.objects.filter(code=q).select_related(
            'batch__shop__salesman__user', 'activated_by'
        ).first()
        if coupon:
            coupon.audit_redemption = Redemption.objects.filter(
                transactions__coupon=coupon
            ).select_related('reward', 'user').first()
    return render(request, 'coupons/admin/coupon_audit.html', {'coupon': coupon, 'q': q})


@opc_admin_required
def admin_rewards(request):
    rewards = Reward.objects.all().order_by('points_required')
    return render(request, 'coupons/admin/rewards.html', {'rewards': rewards})


@opc_admin_required
def admin_reward_create(request):
    shops = ShopProfile.objects.filter(user__is_active=True, user__user_type='shop').select_related('user')
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        business = request.POST.get('business_name', '').strip()
        points = int(request.POST.get('points_required', 0))
        description = request.POST.get('description', '').strip()
        qty = request.POST.get('quantity_limit', '').strip()
        expiry = request.POST.get('expiry', '').strip() or None
        shop_id = request.POST.get('redemption_shop', '').strip()
        shop = get_object_or_404(shops, pk=shop_id) if shop_id else None
        Reward.objects.create(
            redemption_shop=shop,
            name=name, business_name=business, points_required=points,
            description=description,
            quantity_limit=int(qty) if qty else None,
            expiry=expiry,
        )
        messages.success(request, f'Reward "{name}" created.')
        return redirect('opc_admin_rewards')
    return render(request, 'coupons/admin/reward_form.html', {'action': 'Create', 'shops': shops})


@opc_admin_required
def admin_reward_edit(request, pk):
    shops = ShopProfile.objects.filter(user__is_active=True, user__user_type='shop').select_related('user')
    reward = get_object_or_404(Reward, pk=pk)
    if request.method == 'POST':
        if request.POST.get('action') == 'delete':
            reward.delete()
            messages.success(request, 'Reward deleted.')
            return redirect('opc_admin_rewards')
        shop_id = request.POST.get('redemption_shop', '').strip()
        reward.redemption_shop = get_object_or_404(shops, pk=shop_id) if shop_id else None
        reward.name = request.POST.get('name', reward.name).strip()
        reward.business_name = request.POST.get('business_name', reward.business_name).strip()
        reward.points_required = int(request.POST.get('points_required', reward.points_required))
        reward.description = request.POST.get('description', '').strip()
        qty = request.POST.get('quantity_limit', '').strip()
        reward.quantity_limit = int(qty) if qty else None
        expiry = request.POST.get('expiry', '').strip()
        reward.expiry = expiry or None
        reward.is_active = 'is_active' in request.POST
        reward.save()
        messages.success(request, 'Reward updated.')
        return redirect('opc_admin_rewards')
    return render(request, 'coupons/admin/reward_form.html', {'action': 'Edit', 'reward': reward, 'shops': shops})


@opc_admin_required
def admin_spinwheel(request):
    slots = SpinWheelSlot.objects.all()
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add':
            label = request.POST.get('label', '').strip()
            points = int(request.POST.get('points', 0))
            prob = request.POST.get('probability', '0').strip()
            is_surprise = 'is_surprise' in request.POST
            surprise_name = request.POST.get('surprise_gift_name', '').strip()
            color = request.POST.get('color', '#6366f1').strip()
            SpinWheelSlot.objects.create(
                label=label, points=points, probability=prob,
                is_surprise=is_surprise, surprise_gift_name=surprise_name,
                color=color,
            )
            messages.success(request, 'Slot added.')
        elif action == 'delete':
            slot_id = request.POST.get('slot_id')
            SpinWheelSlot.objects.filter(pk=slot_id).delete()
            messages.success(request, 'Slot removed.')
        return redirect('opc_admin_spinwheel')
    total_prob = sum(float(s.probability) for s in slots)
    return render(request, 'coupons/admin/spinwheel.html', {
        'slots': slots, 'total_prob': round(total_prob, 2)
    })


@opc_admin_required
def admin_customers(request):
    wallets = PointsWallet.objects.select_related('user').order_by('-balance')[:100]
    return render(request, 'coupons/admin/customers.html', {'wallets': wallets})


@opc_admin_required
def admin_redemptions(request):
    redemptions = Redemption.objects.select_related('user', 'reward').order_by('-created_at')[:200]
    return render(request, 'coupons/admin/redemptions.html', {'redemptions': redemptions})


# ═══════════════════════════════════════════════════════════════════════════════
# SALESMAN VIEWS
# ═══════════════════════════════════════════════════════════════════════════════

def salesman_login(request):
    if request.user.is_authenticated and _is_salesman(request.user):
        return redirect('opc_salesman_dashboard')
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()
        user = authenticate(request, username=username, password=password)
        if user and hasattr(user, 'salesman_profile'):
            if not user.salesman_profile.is_active:
                messages.error(request, 'Your account is deactivated.')
            else:
                login(request, user)
                return redirect('opc_salesman_dashboard')
        else:
            messages.error(request, 'Invalid credentials or not a salesman account.')
    return render(request, 'coupons/salesman/login.html')


def salesman_logout(request):
    logout(request)
    return redirect('opc_salesman_login')


@salesman_required
def salesman_dashboard(request):
    sm = request.user.salesman_profile
    shops = sm.shops.annotate(coupon_count=Sum('batches__quantity'))
    total_given = sm.batches.aggregate(t=Sum('quantity'))['t'] or 0
    activated = Coupon.objects.filter(batch__salesman=sm, status='activated').count()

    # Business ID lookup
    biz_result = None
    biz_error = None
    biz_query = request.GET.get('biz', '').strip().upper()
    if biz_query:
        biz_user = User.objects.filter(salesman_biz_id=biz_query).first()
        if biz_user:
            # Collect business name from company profile or shop profile
            biz_name = ''
            try:
                biz_name = biz_user.company.company_name
            except Exception:
                pass
            if not biz_name:
                try:
                    biz_name = biz_user.shop.shop_name
                except Exception:
                    pass
            if not biz_name:
                biz_name = biz_user.get_full_name() or biz_user.username
            biz_result = {
                'biz_id': biz_query,
                'name': biz_name,
                'owner': biz_user.get_full_name() or biz_user.username,
                'phone': biz_user.phone or biz_user.business_phone,
                'address': biz_user.address,
                'city': biz_user.city,
                'pincode': biz_user.pincode,
                'user_type': biz_user.get_user_type_display() if hasattr(biz_user, 'get_user_type_display') else biz_user.user_type,
                'joined': biz_user.date_joined,
            }
        else:
            biz_error = f'No business found with ID "{biz_query}".'

    ctx = {
        'salesman': sm,
        'shops': shops,
        'total_shops': shops.count(),
        'total_given': total_given,
        'activated': activated,
        'recent_batches': sm.batches.select_related('shop').order_by('-created_at')[:5],
        'biz_result': biz_result,
        'biz_error': biz_error,
        'biz_query': biz_query,
    }
    return render(request, 'coupons/salesman/dashboard.html', ctx)


@salesman_required
def salesman_shops(request):
    sm = request.user.salesman_profile
    shops = sm.shops.annotate(coupon_count=Sum('batches__quantity')).order_by('-created_at')
    return render(request, 'coupons/salesman/shops.html', {'shops': shops, 'salesman': sm})


@salesman_required
def salesman_shop_create(request):
    sm = request.user.salesman_profile
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        pincode = request.POST.get('pincode', '').strip()
        address = request.POST.get('address', '').strip()
        phone = request.POST.get('phone', '').strip()
        if not name or not pincode:
            messages.error(request, 'Shop name and pincode required.')
            return redirect('opc_salesman_shop_create')
        shop = Shop.objects.create(salesman=sm, name=name, pincode=pincode,
                                   address=address, phone=phone)
        messages.success(request, f'✓ {shop.name} added successfully.')
        return redirect('opc_salesman_shop_detail', pk=shop.pk)
    return render(request, 'coupons/salesman/shop_create.html')


@salesman_required
def salesman_shop_detail(request, pk):
    sm = request.user.salesman_profile
    shop = get_object_or_404(Shop, pk=pk, salesman=sm)
    batches = shop.batches.order_by('-created_at')
    return render(request, 'coupons/salesman/shop_detail.html', {
        'shop': shop, 'batches': batches, 'salesman': sm
    })


@salesman_required
def salesman_give_coupons(request):
    sm = request.user.salesman_profile
    # All active shops — salesman's own first, then others
    my_shops = list(Shop.objects.filter(salesman=sm, is_active=True).order_by('name'))
    other_shops = list(Shop.objects.exclude(salesman=sm).filter(is_active=True).order_by('name'))
    all_shops = my_shops + other_shops

    if request.method == 'POST':
        shop_id = request.POST.get('shop_id')
        dist_date = request.POST.get('distributed_date') or None
        start_raw = request.POST.get('start_number', '').strip()
        end_raw = request.POST.get('end_number', '').strip()

        shop = get_object_or_404(Shop, pk=shop_id, is_active=True)

        # Parse and validate start/end numbers
        try:
            start = int(start_raw)
            end = int(end_raw)
        except (ValueError, TypeError):
            messages.error(request, '❌ Please enter valid start and end coupon numbers.')
            return redirect('opc_salesman_give_coupons')

        if start < 1 or end < start:
            messages.error(request, '❌ End number must be greater than or equal to start number.')
            return redirect('opc_salesman_give_coupons')

        quantity = end - start + 1
        if quantity > 10000:
            messages.error(request, '❌ Maximum 10,000 coupons per batch.')
            return redirect('opc_salesman_give_coupons')

        # Check for overlapping coupon numbers
        conflict = Coupon.objects.filter(number__gte=start, number__lte=end).exists()
        if conflict:
            messages.error(request, f'❌ Some coupon numbers in OPC-{start:06d} → OPC-{end:06d} are already used. Please check the range.')
            return redirect('opc_salesman_give_coupons')

        with transaction.atomic():
            # Update global counter if needed
            with transaction.atomic():
                counter, _ = CouponCounter.objects.select_for_update().get_or_create(pk=1)
                if end > counter.last_number:
                    counter.last_number = end
                    counter.save(update_fields=['last_number'])

            batch = CouponBatch.objects.create(
                shop=shop, salesman=sm, quantity=quantity,
                start_number=start, end_number=end,
                distributed_date=dist_date or None,
            )
            coupons = [
                Coupon(code=f'OPC-{n:06d}', number=n, batch=batch)
                for n in range(start, end + 1)
            ]
            Coupon.objects.bulk_create(coupons)
        messages.success(request, f'✓ {quantity} coupons given to {shop.name} '
                                   f'(OPC-{start:06d} → OPC-{end:06d})')
        return redirect('opc_salesman_coupon_history')
    pre_shop = request.GET.get('shop')
    return render(request, 'coupons/salesman/give_coupons.html', {
        'shops': all_shops,
        'my_shop_ids': [s.pk for s in my_shops],
        'pre_shop': pre_shop,
    })


@salesman_required
def salesman_add_shop_from_biz(request):
    """Add a business as a shop under this salesman (via BIZ ID lookup)."""
    sm = request.user.salesman_profile
    if request.method != 'POST':
        return redirect('opc_salesman_dashboard')

    biz_id = request.POST.get('biz_id', '').strip().upper()
    biz_user = User.objects.filter(salesman_biz_id=biz_id).first()
    if not biz_user:
        messages.error(request, f'Business "{biz_id}" not found.')
        return redirect('opc_salesman_dashboard')

    # Get business details
    biz_name = ''
    try:
        biz_name = biz_user.company.company_name
    except Exception:
        pass
    if not biz_name:
        try:
            biz_name = biz_user.shop.shop_name
        except Exception:
            pass
    if not biz_name:
        biz_name = biz_user.get_full_name() or biz_user.username

    phone = ''
    try:
        phone = biz_user.phone or biz_user.business_phone or ''
    except Exception:
        pass

    address = ''
    try:
        parts = [p for p in [biz_user.address, biz_user.city] if p]
        address = ', '.join(parts)
    except Exception:
        pass

    pincode = getattr(biz_user, 'pincode', '') or ''

    # Check if this salesman already has a shop with this name + pincode
    existing = Shop.objects.filter(salesman=sm, name=biz_name, pincode=pincode).first()
    if existing:
        messages.success(request, f'✓ {biz_name} is already in your shops list.')
        return redirect('opc_salesman_give_coupons') if request.POST.get('goto_coupons') else redirect('opc_salesman_dashboard')

    shop = Shop.objects.create(
        salesman=sm,
        name=biz_name,
        pincode=pincode,
        address=address,
        phone=phone,
    )
    messages.success(request, f'✓ {biz_name} added to your shops. Now give coupons!')
    return redirect(f'/coupons/salesman/give-coupons/?shop={shop.pk}')


@salesman_required
def salesman_coupon_history(request):
    sm = request.user.salesman_profile
    batches = sm.batches.select_related('shop').order_by('-created_at')
    return render(request, 'coupons/salesman/coupon_history.html', {
        'batches': batches, 'salesman': sm
    })


# ═══════════════════════════════════════════════════════════════════════════════
# CUSTOMER VIEWS
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def customer_activate_coupon(request):
    if request.method == 'POST':
        code = request.POST.get('code', '').strip().upper()
        coupon = Coupon.objects.filter(code=code).select_related('batch__shop').first()
        if not coupon:
            messages.error(request, '❌ Coupon not found. Check the number and try again.')
            return redirect('opc_activate_coupon')
        if coupon.status == 'activated':
            messages.error(request, '❌ This coupon has already been activated.')
            return redirect('opc_activate_coupon')
        if coupon.status in ('expired', 'cancelled'):
            messages.error(request, f'❌ This coupon is {coupon.status}.')
            return redirect('opc_activate_coupon')
        # Valid — store in session and redirect to spin
        request.session['pending_coupon'] = coupon.pk
        return redirect('opc_spin_wheel')
    return render(request, 'coupons/customer/activate_coupon.html')


@login_required
def customer_spin_wheel(request):
    coupon_pk = request.session.get('pending_coupon')
    if not coupon_pk:
        return redirect('opc_activate_coupon')
    coupon = get_object_or_404(Coupon, pk=coupon_pk)
    if coupon.status != 'available':
        del request.session['pending_coupon']
        messages.error(request, 'Coupon already used.')
        return redirect('opc_activate_coupon')
    slots = SpinWheelSlot.objects.filter(is_active=True).order_by('order')
    return render(request, 'coupons/customer/spin_wheel.html', {
        'coupon': coupon, 'slots': slots
    })


@login_required
@require_POST
def customer_spin_api(request):
    coupon_pk = request.session.get('pending_coupon')
    if not coupon_pk:
        return JsonResponse({'error': 'No pending coupon'}, status=400)
    with transaction.atomic():
        coupon = Coupon.objects.select_for_update().filter(
            pk=coupon_pk, status='available'
        ).first()
        if not coupon:
            return JsonResponse({'error': 'Coupon no longer available'}, status=400)
        result = _spin_result()
        pts = result['points']
        coupon.status = 'activated'
        coupon.activated_by = request.user
        coupon.activated_at = timezone.now()
        coupon.points_awarded = pts
        coupon.is_surprise_gift = result.get('is_surprise', False)
        coupon.surprise_gift_name = result.get('surprise_gift_name', '')
        coupon.save()
        wallet = PointsWallet.get_or_create_for(request.user)
        wallet.credit(pts, f'Gift Coupon {coupon.code}', coupon=coupon)
    del request.session['pending_coupon']
    # Notifications
    _notify_user(request.user, 'points',
                 f'🎁 You activated {coupon.code} and won {pts} OURPINCODE Points!',
                 '/coupons/my-points/')
    return JsonResponse({
        'points': pts,
        'label': result['label'],
        'is_surprise': result.get('is_surprise', False),
        'surprise_gift_name': result.get('surprise_gift_name', ''),
        'shop_name': coupon.batch.shop.name,
        'coupon_code': coupon.code,
        'balance': wallet.balance,
    })


@login_required
def customer_my_points(request):
    wallet = PointsWallet.get_or_create_for(request.user)
    transactions = wallet.transactions.all()[:50]
    return render(request, 'coupons/customer/my_points.html', {
        'wallet': wallet, 'transactions': transactions
    })


@login_required
def customer_rewards(request):
    wallet = PointsWallet.get_or_create_for(request.user)
    rewards = Reward.objects.filter(is_active=True).filter(
        Q(expiry__isnull=True) | Q(expiry__gte=timezone.localdate())
    ).order_by('points_required')
    return render(request, 'coupons/customer/rewards.html', {
        'rewards': rewards, 'wallet': wallet
    })


@login_required
def customer_redeem(request, pk):
    reward = get_object_or_404(Reward, pk=pk, is_active=True)
    if not reward.is_available():
        messages.error(request, 'Reward no longer available.')
        return redirect('opc_rewards')
    wallet = PointsWallet.get_or_create_for(request.user)
    if request.method == 'POST':
        if wallet.balance < reward.points_required:
            messages.error(request, 'Insufficient points.')
            return redirect('opc_rewards')
        with transaction.atomic():
            num = RedemptionCounter.next_number()
            code = f'OPC-RED-{num:06d}'
            redemption = Redemption.objects.create(
                code=code, user=request.user, reward=reward,
                points_used=reward.points_required,
            )
            wallet.debit(reward.points_required,
                         f'Redeemed: {reward.name}', redemption=redemption)
            reward.quantity_redeemed += 1
            reward.save(update_fields=['quantity_redeemed'])
        _notify_user(request.user, 'announcement',
                     f'🎉 Your {reward.name} reward is ready! Code: {code}',
                     '/coupons/my-redemptions/')
        return redirect('opc_redemption_success', pk=redemption.pk)
    after = wallet.balance - reward.points_required
    return render(request, 'coupons/customer/redeem_confirm.html', {
        'reward': reward, 'wallet': wallet, 'balance_after': after
    })


@login_required
def customer_redemption_success(request, pk):
    redemption = get_object_or_404(Redemption, pk=pk, user=request.user)
    return render(request, 'coupons/customer/redemption_success.html', {
        'redemption': redemption
    })


@login_required
def customer_my_redemptions(request):
    redemptions = Redemption.objects.filter(user=request.user).select_related('reward').order_by('-created_at')
    wallet = PointsWallet.get_or_create_for(request.user)
    return render(request, 'coupons/customer/my_redemptions.html', {
        'redemptions': redemptions, 'wallet': wallet
    })


# ═══════════════════════════════════════════════════════════════════════════════
# SHOP VERIFY VIEW (authenticated, assigned shop only)
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
@require_http_methods(['GET', 'POST'])
def shop_verify_redemption(request):
    if not request.user.is_active or request.user.user_type != 'shop':
        return HttpResponseForbidden('Shop access required.')
    if not ShopProfile.objects.filter(user=request.user).exists():
        return HttpResponseForbidden('Shop access required.')

    redemptions = Redemption.objects.filter(reward__redemption_shop__user=request.user).filter(
        Q(reward__expiry__isnull=True) | Q(reward__expiry__gte=timezone.localdate())
    )
    redemption = None
    q = request.GET.get('q', '').strip().upper()
    error = None
    if request.method == 'POST':
        code = request.POST.get('code', '').strip().upper()
        action = request.POST.get('action', '')
        redemption = redemptions.filter(code=code).select_related('user', 'reward').first()
        if not redemption:
            error = 'Redemption code not found.'
        elif action == 'mark_redeemed':
            updated = Redemption.objects.filter(pk=redemption.pk, status='pending').update(
                status='redeemed', verified_by_shop=True, redeemed_at=timezone.now(),
            )
            redemption.refresh_from_db()
            if updated:
                messages.success(request, 'Redemption completed successfully.')
            else:
                error = 'This code is no longer pending.'
    elif q:
        redemption = redemptions.filter(code=q).select_related('user', 'reward').first()
        if not redemption:
            error = 'Redemption code not found.'
    return render(request, 'coupons/shop/verify_redemption.html', {
        'redemption': redemption, 'q': q, 'error': error
    })
