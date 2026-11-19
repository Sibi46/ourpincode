from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from .models import Business, Branch, Employee, VoucherSlotPurchase, GiftVoucher, VoucherCategory, VoucherPurchase, VoucherRedemption
from django.db import models as dj_models, transaction
from .forms import BusinessRegistrationForm, BranchForm, EmployeeForm, SlotRequestForm, GiftVoucherForm, VoucherPurchaseForm, SLOT_PACKAGES, SLOT_PACKAGE_MAP
import string
import random
import io
from django.core.files.base import ContentFile

def business_register(request):
    """Any logged-in user can register a business."""
    if not request.user.is_authenticated:
        return redirect(f'/login/?next=/vouchers/business/register/')

    # If user already has a business, redirect to dashboard
    existing = Business.objects.filter(owner=request.user).first()
    if existing:
        return redirect('vouchers:business_dashboard')

    if request.method == 'POST':
        form = BusinessRegistrationForm(request.POST, request.FILES)
        if form.is_valid():
            business = form.save(commit=False)
            business.owner = request.user
            business.status = 'pending'
            business.save()
            return redirect('vouchers:register_success')
    else:
        form = BusinessRegistrationForm()

    return render(request, 'vouchers/business_register.html', {'form': form})


@login_required
def business_register_success(request):
    business = get_object_or_404(Business, owner=request.user)
    if business.status != 'pending':
        return redirect('vouchers:business_dashboard')
    return render(request, 'vouchers/pending_approval.html', {'business': business})


@login_required
def business_dashboard(request):
    from django.utils import timezone
    from django.db.models import Sum
    business = get_object_or_404(Business, owner=request.user)

    if business.status == 'pending':
        return render(request, 'vouchers/pending_approval.html', {'business': business})

    now = timezone.localtime()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    all_vouchers  = GiftVoucher.objects.filter(business=business)
    all_purchases = VoucherPurchase.objects.filter(gift_voucher__business=business)
    revenue_qs    = all_purchases.filter(status__in=['paid', 'sent', 'redeemed'])

    voucher_stats = {
        'total':     all_vouchers.count(),
        'published': all_vouchers.filter(status='published').count(),
        'draft':     all_vouchers.filter(status='draft').count(),
        'paused':    all_vouchers.filter(status='paused').count(),
    }

    purchase_stats = {
        'total':    all_purchases.count(),
        'paid':     all_purchases.filter(status='paid').count(),
        'sent':     all_purchases.filter(status='sent').count(),
        'redeemed': all_purchases.filter(status='redeemed').count(),
    }

    total_revenue = revenue_qs.aggregate(t=Sum('amount_paid'))['t'] or 0
    month_revenue = revenue_qs.filter(
        purchased_at__gte=month_start
    ).aggregate(t=Sum('amount_paid'))['t'] or 0

    slot_pending = VoucherSlotPurchase.objects.filter(
        business=business, status='pending'
    ).count()

    recent_vouchers    = all_vouchers.order_by('-created_at')[:5]
    recent_purchases   = all_purchases.select_related('gift_voucher').order_by('-purchased_at')[:8]
    recent_redemptions = VoucherRedemption.objects.filter(
        purchase__gift_voucher__business=business
    ).select_related('purchase', 'purchase__gift_voucher').order_by('-redeemed_at')[:5]

    from django.core.paginator import Paginator
    activity_type = request.GET.get('activity', '')
    activity_history = None
    if activity_type == 'purchases':
        activity_history = Paginator(all_purchases.select_related('gift_voucher').order_by('-purchased_at', '-pk'), 20).get_page(request.GET.get('page'))
    elif activity_type == 'redemptions':
        activity_history = Paginator(VoucherRedemption.objects.filter(purchase__gift_voucher__business=business).select_related('purchase__gift_voucher').order_by('-redeemed_at', '-pk'), 20).get_page(request.GET.get('page'))
    else:
        activity_type = ''

    context = {
        'activity_type': activity_type,
        'activity_history': activity_history,
        'business':           business,
        'voucher_stats':      voucher_stats,
        'purchase_stats':     purchase_stats,
        'total_revenue':      total_revenue,
        'month_revenue':      month_revenue,
        'slot_pending':       slot_pending,
        'recent_vouchers':    recent_vouchers,
        'recent_purchases':   recent_purchases,
        'recent_redemptions': recent_redemptions,
    }
    return render(request, 'vouchers/business_dashboard.html', context)


def _get_approved_business(request):
    """Return approved business owned by request.user or None."""
    try:
        b = Business.objects.get(owner=request.user)
        return b if b.status == 'approved' else None
    except Business.DoesNotExist:
        return None


@login_required
def branch_list(request):
    business = get_object_or_404(Business, owner=request.user)
    branches = business.branches.all()
    return render(request, 'vouchers/branch_list.html', {
        'business': business,
        'branches': branches,
    })


@login_required
def branch_add(request):
    business = get_object_or_404(Business, owner=request.user)
    if business.status != 'approved':
        messages.error(request, 'Your business must be approved before adding branches.')
        return redirect('vouchers:business_dashboard')

    if request.method == 'POST':
        form = BranchForm(request.POST)
        if form.is_valid():
            branch = form.save(commit=False)
            branch.business = business
            branch.save()
            messages.success(request, f'Branch "{branch.branch_name}" added successfully.')
            return redirect('vouchers:branch_list')
    else:
        form = BranchForm()

    return render(request, 'vouchers/branch_form.html', {
        'business': business,
        'form': form,
        'action': 'Add',
    })


@login_required
def branch_edit(request, pk):
    business = get_object_or_404(Business, owner=request.user)
    branch = get_object_or_404(Branch, pk=pk, business=business)

    if request.method == 'POST':
        form = BranchForm(request.POST, instance=branch)
        if form.is_valid():
            form.save()
            messages.success(request, f'Branch "{branch.branch_name}" updated.')
            return redirect('vouchers:branch_list')
    else:
        form = BranchForm(instance=branch)

    return render(request, 'vouchers/branch_form.html', {
        'business': business,
        'form': form,
        'branch': branch,
        'action': 'Edit',
    })


@login_required
def branch_toggle(request, pk):
    business = get_object_or_404(Business, owner=request.user)
    branch = get_object_or_404(Branch, pk=pk, business=business)
    branch.is_active = not branch.is_active
    branch.save()
    status = 'activated' if branch.is_active else 'deactivated'
    messages.success(request, f'Branch "{branch.branch_name}" {status}.')
    return redirect('vouchers:branch_list')
@login_required
def employee_list(request):
    business = get_object_or_404(Business, owner=request.user)
    employees = business.employees.select_related('assigned_branch').all()
    return render(request, 'vouchers/employee_list.html', {
        'business': business,
        'employees': employees,
    })


@login_required
def employee_add(request):
    business = get_object_or_404(Business, owner=request.user)
    if business.status != 'approved':
        messages.error(request, 'Your business must be approved before adding employees.')
        return redirect('vouchers:business_dashboard')

    if request.method == 'POST':
        form = EmployeeForm(business, request.POST)
        if form.is_valid():
            emp = form.save(commit=False)
            emp.business = business
            emp.save()
            messages.success(request, f'Employee "{emp.name}" added successfully.')
            return redirect('vouchers:employee_list')
    else:
        form = EmployeeForm(business)

    return render(request, 'vouchers/employee_form.html', {
        'business': business,
        'form': form,
        'action': 'Add',
    })


@login_required
def employee_edit(request, pk):
    business = get_object_or_404(Business, owner=request.user)
    employee = get_object_or_404(Employee, pk=pk, business=business)

    if request.method == 'POST':
        form = EmployeeForm(business, request.POST, instance=employee)
        if form.is_valid():
            form.save()
            messages.success(request, f'Employee "{employee.name}" updated.')
            return redirect('vouchers:employee_list')
    else:
        form = EmployeeForm(business, instance=employee)

    return render(request, 'vouchers/employee_form.html', {
        'business': business,
        'form': form,
        'employee': employee,
        'action': 'Edit',
    })


@login_required
def employee_toggle(request, pk):
    business = get_object_or_404(Business, owner=request.user)
    employee = get_object_or_404(Employee, pk=pk, business=business)
    employee.is_active = not employee.is_active
    employee.save()
    status = 'activated' if employee.is_active else 'deactivated'
    messages.success(request, f'Employee "{employee.name}" {status}.')
    return redirect('vouchers:employee_list')


@login_required
def slot_buy(request):
    business = get_object_or_404(Business, owner=request.user)
    if business.status != 'approved':
        messages.error(request, 'Your business must be approved before buying slots.')
        return redirect('vouchers:business_dashboard')

    if request.method == 'POST':
        form = SlotRequestForm(request.POST)
        if form.is_valid():
            pkg = SLOT_PACKAGE_MAP[form.cleaned_data['package']]
            VoucherSlotPurchase.objects.create(
                business=business,
                purchased_by=request.user,
                slots_count=pkg['slots'],
                amount_paid=pkg['price'],
                payment_reference=form.cleaned_data['payment_reference'],
                notes=form.cleaned_data.get('notes', ''),
                status='pending',
            )
            messages.success(request, f"Slot request for {pkg['slots']} slots submitted. Admin will approve after payment verification.")
            return redirect('vouchers:slot_history')
    else:
        form = SlotRequestForm()

    return render(request, 'vouchers/slot_buy.html', {
        'business': business,
        'form': form,
        'packages': SLOT_PACKAGES,
    })


@login_required
def slot_history(request):
    business = get_object_or_404(Business, owner=request.user)
    if business.status == 'pending':
        return render(request, 'vouchers/pending_approval.html', {'business': business})
    slot_requests = business.slot_purchases.all()
    return render(request, 'vouchers/slot_history.html', {
        'business': business,
        'slot_requests': slot_requests,
        'slot_pending': business.status == 'approved' and slot_requests.filter(status='pending').exists(),
    })


@login_required
def voucher_list(request):
    business = get_object_or_404(Business, owner=request.user)
    vouchers = business.gift_vouchers.exclude(status='deleted').order_by('-created_at')
    return render(request, 'vouchers/voucher_list.html', {
        'business': business,
        'vouchers': vouchers,
    })


@login_required
def voucher_create(request):
    business = get_object_or_404(Business, owner=request.user)

    # Block if not approved
    if business.status != 'approved':
        messages.error(request, 'Your business must be approved before creating vouchers.')
        return redirect('vouchers:business_dashboard')

    if request.method == 'POST':
        form = GiftVoucherForm(business, request.POST, request.FILES)
        if form.is_valid():
            voucher = form.save(commit=False)
            # Set fields that user doesn't fill in manually
            voucher.business = business
            voucher.created_by = request.user
            voucher.status = 'draft'       # Always starts as draft
            voucher.sold_quantity = 0      # No sales yet
            voucher.save()
            form.save_m2m()               # Save applicable_branches (ManyToMany needs this)
            messages.success(request, f'Voucher "{voucher.voucher_name}" created as Draft.')
            return redirect('vouchers:voucher_list')
    else:
        form = GiftVoucherForm(business)

    return render(request, 'vouchers/voucher_form.html', {
        'business': business,
        'form': form,
        'action': 'Create',
    })


@login_required
def voucher_edit(request, pk):
    business = get_object_or_404(Business, owner=request.user)
    voucher = get_object_or_404(GiftVoucher, pk=pk, business=business)

    # Can only edit draft or paused vouchers
    if voucher.status not in ['draft', 'paused']:
        messages.error(request, 'Only Draft or Paused vouchers can be edited.')
        return redirect('vouchers:voucher_list')

    if request.method == 'POST':
        form = GiftVoucherForm(business, request.POST, request.FILES, instance=voucher)
        if form.is_valid():
            form.save()
            messages.success(request, f'Voucher "{voucher.voucher_name}" updated.')
            return redirect('vouchers:voucher_list')
    else:
        form = GiftVoucherForm(business, instance=voucher)

    return render(request, 'vouchers/voucher_form.html', {
        'business': business,
        'form': form,
        'voucher': voucher,
        'action': 'Edit',
    })


@login_required
def voucher_publish(request, pk):
    business = get_object_or_404(Business, owner=request.user)
    voucher = get_object_or_404(GiftVoucher, pk=pk, business=business)

    if business.available_slots <= 0:
        messages.error(request, f'No slots available. Buy more slots to publish vouchers.')
        return redirect('vouchers:voucher_list')

    if voucher.status != 'draft':
        messages.error(request, 'Only Draft vouchers can be published.')
        return redirect('vouchers:voucher_list')

    from django.utils import timezone
    voucher.status = 'published'
    voucher.published_at = timezone.now()
    voucher.save()
    messages.success(request, f'"{voucher.voucher_name}" is now live!')
    return redirect('vouchers:voucher_list')


@login_required
def voucher_pause(request, pk):
    business = get_object_or_404(Business, owner=request.user)
    voucher = get_object_or_404(GiftVoucher, pk=pk, business=business)

    if voucher.status != 'published':
        messages.error(request, 'Only Published vouchers can be paused.')
        return redirect('vouchers:voucher_list')

    voucher.status = 'paused'
    voucher.save()
    messages.success(request, f'"{voucher.voucher_name}" paused. Slot freed — you can publish another voucher.')
    return redirect('vouchers:voucher_list')


@login_required
def voucher_resume(request, pk):
    business = get_object_or_404(Business, owner=request.user)
    voucher = get_object_or_404(GiftVoucher, pk=pk, business=business)

    if voucher.status != 'paused':
        messages.error(request, 'Only Paused vouchers can be resumed.')
        return redirect('vouchers:voucher_list')

    if business.available_slots <= 0:
        messages.error(request, 'No slots available. Buy more slots to resume this voucher.')
        return redirect('vouchers:voucher_list')

    voucher.status = 'published'
    voucher.save()
    messages.success(request, f'"{voucher.voucher_name}" is live again!')
    return redirect('vouchers:voucher_list')


@login_required
def voucher_delete(request, pk):
    business = get_object_or_404(Business, owner=request.user)
    voucher = get_object_or_404(GiftVoucher, pk=pk, business=business)

    if voucher.status == 'deleted':
        messages.error(request, 'Voucher already deleted.')
        return redirect('vouchers:voucher_list')

    name = voucher.voucher_name
    voucher.status = 'deleted'
    voucher.save()
    messages.success(request, f'"{name}" deleted. Slot freed.')
    return redirect('vouchers:voucher_list')


def marketplace(request):
    pincode  = request.GET.get('pincode', '').strip()
    category = request.GET.get('category', '').strip()

    from django.utils import timezone
    today = timezone.now().date()

    vouchers = GiftVoucher.objects.filter(
        status='published',
        expiry_date__gte=today,
    ).select_related('business', 'category')

    if pincode:
        from django.db.models import Q
        vouchers = vouchers.filter(
            Q(applicable_branches__pincode=pincode) |
            Q(business__pincode=pincode)
        ).distinct()

    if category:
        vouchers = vouchers.filter(category__id=category)

    categories = VoucherCategory.objects.filter(is_active=True)

    return render(request, 'vouchers/marketplace.html', {
        'vouchers':    vouchers,
        'categories':  categories,
        'pincode':     pincode,
        'category':    category,
    })


def voucher_detail(request, pk):
    from django.utils import timezone
    today = timezone.now().date()
    voucher = get_object_or_404(GiftVoucher, pk=pk, status='published')
    return render(request, 'vouchers/voucher_detail.html', {
        'voucher': voucher,
        'is_expired': voucher.expiry_date < today,
    })
    import uuid
import string
import random
import io
from django.core.files.base import ContentFile


def _generate_voucher_code():
    chars = string.ascii_uppercase + string.digits
    suffix = ''.join(random.choices(chars, k=8))
    return f"GIFT-{suffix}"


def _generate_qr(voucher_code):
    import qrcode
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(voucher_code)
    qr.make(fit=True)
    img = qr.make_image(fill_color='black', back_color='white')
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return ContentFile(buf.getvalue(), name=f'{voucher_code}.png')


def voucher_purchase(request, pk):
    from django.utils import timezone
    today = timezone.now().date()
    voucher = get_object_or_404(GiftVoucher, pk=pk, status='published')

    # Block if expired or sold out
    if voucher.expiry_date < today:
        messages.error(request, 'This voucher has expired.')
        return redirect('vouchers:voucher_detail', pk=pk)
    if voucher.available_quantity <= 0:
        messages.error(request, 'This voucher is sold out.')
        return redirect('vouchers:voucher_detail', pk=pk)

    if request.method == 'POST':
        form = VoucherPurchaseForm(request.POST)
        if form.is_valid():
            d = form.cleaned_data

            # Generate unique voucher code — retry if collision
            for _ in range(10):
                code = _generate_voucher_code()
                if not VoucherPurchase.objects.filter(voucher_code=code).exists():
                    break

            purchase = VoucherPurchase(
                gift_voucher     = voucher,
                voucher_code     = code,
                buyer_name       = d['buyer_name'],
                buyer_mobile     = d['buyer_mobile'],
                buyer_email      = d['buyer_email'],
                buyer_user       = request.user if request.user.is_authenticated else None,
                receiver_name    = d['receiver_name'],
                receiver_mobile  = d['receiver_mobile'],
                receiver_email   = d['receiver_email'],
                personal_message = d.get('personal_message', ''),
                amount_paid      = voucher.voucher_value,
                status           = 'paid',
            )
            purchase.qr_code.save(f'{code}.png', _generate_qr(code), save=False)
            purchase.save()

            # Increment sold quantity
            GiftVoucher.objects.filter(pk=voucher.pk).update(
                sold_quantity=dj_models.F('sold_quantity') + 1
            )

            return redirect('vouchers:purchase_confirm', pk=purchase.pk)
    else:
        form = VoucherPurchaseForm()

    return render(request, 'vouchers/voucher_purchase.html', {
        'voucher': voucher,
        'form': form,
    })


def purchase_confirm(request, pk):
    purchase = get_object_or_404(VoucherPurchase, pk=pk)
    return render(request, 'vouchers/purchase_confirm.html', {
        'purchase': purchase,
    })


@login_required
def my_vouchers(request):
    from django.utils import timezone
    today = timezone.now().date()
    purchases = VoucherPurchase.objects.filter(
        buyer_user=request.user
    ).select_related('gift_voucher', 'gift_voucher__business').order_by('-purchased_at')
    return render(request, 'vouchers/my_vouchers.html', {
        'purchases': purchases,
        'today': today,
    })


def voucher_card(request, code):
    """Public voucher card — anyone with the link can view it (no login needed)."""
    from django.utils import timezone
    purchase = get_object_or_404(VoucherPurchase, voucher_code=code.upper())
    return render(request, 'vouchers/voucher_card.html', {
        'purchase': purchase,
        'today': timezone.now().date(),
    })


@login_required
def voucher_share_email(request, pk):
    """Send the voucher card link to the receiver's email."""
    from django.core.mail import send_mail
    purchase = get_object_or_404(VoucherPurchase, pk=pk)

    scheme = 'https' if request.is_secure() else 'http'
    domain = request.get_host()
    card_url = f"{scheme}://{domain}/vouchers/v/{purchase.voucher_code}/"

    send_mail(
        subject=f'Gift Voucher for you – {purchase.gift_voucher.voucher_name}',
        message=(
            f"Hello {purchase.receiver_name},\n\n"
            f"{purchase.buyer_name} has sent you a gift voucher!\n\n"
            f"Voucher: {purchase.gift_voucher.voucher_name}\n"
            f"Value: Rs.{purchase.amount_paid}\n"
            f"Code: {purchase.voucher_code}\n"
            f"Valid Till: {purchase.gift_voucher.expiry_date.strftime('%d %b %Y')}\n"
            + (f"\nMessage: {purchase.personal_message}\n" if purchase.personal_message else "")
            + f"\nView your voucher here:\n{card_url}\n\n"
            f"Show this voucher or QR code at the store to redeem.\n\n"
            f"– MYPINCOD Team"
        ),
        from_email=None,
        recipient_list=[purchase.receiver_email],
        fail_silently=True,
    )
    messages.success(request, f'Voucher sent to {purchase.receiver_email}')
    return redirect('vouchers:purchase_confirm', pk=pk)


def _send_otp_email(purchase):
    from django.core.mail import send_mail
    otp = f"{random.randint(100000, 999999)}"
    from django.utils import timezone
    purchase.otp = otp
    purchase.otp_generated_at = timezone.now()
    purchase.save(update_fields=['otp', 'otp_generated_at'])
    send_mail(
        subject='Your Gift Voucher OTP – MYPINCOD',
        message=(
            f"Hello {purchase.receiver_name},\n\n"
            f"Your redemption OTP for voucher {purchase.voucher_code} is:\n\n"
            f"  {otp}\n\n"
            f"This OTP is valid for 10 minutes. Share it with the store staff.\n\n"
            f"– MYPINCOD Team"
        ),
        from_email=None,
        recipient_list=[purchase.receiver_email],
        fail_silently=True,
    )
    return otp


@login_required
def redeem_lookup(request):
    error = None
    if request.method == 'POST':
        code = request.POST.get('voucher_code', '').strip().upper()
        try:
            purchase = VoucherPurchase.objects.select_related(
                'gift_voucher', 'gift_voucher__business'
            ).get(voucher_code=code)
            if purchase.status == 'redeemed':
                error = 'This voucher has already been redeemed.'
            elif purchase.status in ['cancelled', 'expired']:
                error = f'This voucher is {purchase.status}.'
            elif purchase.status == 'pending':
                error = 'Payment not completed for this voucher.'
            else:
                return redirect('vouchers:redeem_verify', pk=purchase.pk)
        except VoucherPurchase.DoesNotExist:
            error = 'Voucher code not found. Please check and try again.'

    return render(request, 'vouchers/redeem_lookup.html', {'error': error})


@login_required
def redeem_send_otp(request, pk):
    purchase = get_object_or_404(VoucherPurchase, pk=pk)
    if purchase.status not in ['paid', 'sent']:
        messages.error(request, 'Cannot send OTP for this voucher.')
        return redirect('vouchers:redeem_lookup')
    _send_otp_email(purchase)
    messages.success(request, f'OTP sent to {purchase.receiver_email}')
    return redirect('vouchers:redeem_verify', pk=pk)


@login_required
def redeem_verify(request, pk):
    from django.utils import timezone
    purchase = get_object_or_404(
        VoucherPurchase.objects.select_related('gift_voucher', 'gift_voucher__business'),
        pk=pk
    )

    if purchase.status == 'redeemed':
        messages.error(request, 'This voucher is already redeemed.')
        return redirect('vouchers:redeem_lookup')

    error = None

    if request.method == 'POST':
        entered_otp = request.POST.get('otp', '').strip()

        # Check OTP exists
        if not purchase.otp:
            error = 'OTP not sent yet. Please send OTP first.'

        # Check OTP expiry (10 minutes)
        elif purchase.otp_generated_at:
            age = (timezone.now() - purchase.otp_generated_at).seconds
            if age > 600:
                error = 'OTP has expired. Please send a new OTP.'
            elif entered_otp != purchase.otp:
                error = 'Incorrect OTP. Please try again.'
            else:
                # OTP correct — redeem
                now = timezone.now()
                purchase.status = 'redeemed'
                purchase.save(update_fields=['status'])

                VoucherRedemption.objects.create(
                    purchase=purchase,
                    branch=None,
                    redeemed_by=request.user,
                    otp_sent_at=purchase.otp_generated_at,
                    otp_verified_at=now,
                )

                return render(request, 'vouchers/redeem_success.html', {
                    'purchase': purchase,
                })
        else:
            error = 'OTP not sent yet. Please send OTP first.'

    return render(request, 'vouchers/redeem_verify.html', {
        'purchase': purchase,
        'error': error,
    })


@staff_member_required
def admin_dashboard(request):
    from django.db.models import Sum
    from django.utils import timezone

    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    businesses    = Business.objects.all()
    all_purchases = VoucherPurchase.objects.filter(status__in=['paid', 'sent', 'redeemed'])

    biz_stats = {
        'total':     businesses.count(),
        'pending':   businesses.filter(status='pending').count(),
        'approved':  businesses.filter(status='approved').count(),
        'suspended': businesses.filter(status='suspended').count(),
    }

    slot_stats = {
        'pending':  VoucherSlotPurchase.objects.filter(status='pending').count(),
        'approved': VoucherSlotPurchase.objects.filter(status='approved').count(),
    }

    voucher_stats = {
        'total':     GiftVoucher.objects.count(),
        'published': GiftVoucher.objects.filter(status='published').count(),
    }

    total_revenue = all_purchases.aggregate(t=Sum('amount_paid'))['t'] or 0
    month_revenue = all_purchases.filter(
        purchased_at__gte=month_start
    ).aggregate(t=Sum('amount_paid'))['t'] or 0
    total_redemptions = VoucherRedemption.objects.count()

    pending_businesses = businesses.filter(status='pending').select_related(
        'category', 'owner'
    ).order_by('created_at')

    pending_slots = VoucherSlotPurchase.objects.filter(status='pending').select_related(
        'business'
    ).order_by('purchased_at')

    context = {
        'biz_stats':          biz_stats,
        'slot_stats':         slot_stats,
        'voucher_stats':      voucher_stats,
        'total_revenue':      total_revenue,
        'month_revenue':      month_revenue,
        'total_redemptions':  total_redemptions,
        'pending_businesses': pending_businesses,
        'pending_slots':      pending_slots,
    }
    return render(request, 'vouchers/admin_dashboard.html', context)


@staff_member_required
def admin_approve_business(request, pk):
    if request.method == 'POST':
        from jobs.models import UserNotification
        with transaction.atomic():
            biz = get_object_or_404(Business.objects.select_for_update(), pk=pk)
            changed = biz.status != 'approved'
            biz.status = 'approved'
            biz.save()
            if changed:
                UserNotification.objects.create(user=biz.owner, title='Voucher business approved', message=f'{biz.business_name} is approved. You can now buy voucher slots.', notif_type='success', link='/vouchers/dashboard/')
        messages.success(request, f'"{biz.business_name}" approved.')
    return redirect('vouchers:admin_dashboard')


@staff_member_required
def admin_reject_business(request, pk):
    if request.method == 'POST':
        biz = get_object_or_404(Business, pk=pk)
        biz.status = 'rejected'
        biz.rejection_reason = request.POST.get('reason', '').strip()
        biz.save()
        messages.success(request, f'"{biz.business_name}" rejected.')
    return redirect('vouchers:admin_dashboard')


@staff_member_required
def admin_approve_slot(request, pk):
    if request.method == 'POST':
        from jobs.models import UserNotification
        with transaction.atomic():
            slot = get_object_or_404(VoucherSlotPurchase.objects.select_for_update().select_related('business'), pk=pk)
            changed = slot.status != 'approved'
            slot.status = 'approved'
            slot.save()
            if changed:
                UserNotification.objects.create(user=slot.business.owner, title='Voucher slots approved', message=f'Your request for {slot.slots_count} slots is approved. You can now create vouchers.', notif_type='success', link='/vouchers/dashboard/')
        messages.success(request, f'Slot request #{slot.pk} approved ({slot.slots_count} slots).')
    return redirect('vouchers:admin_dashboard')


@staff_member_required
def admin_reject_slot(request, pk):
    if request.method == 'POST':
        slot = get_object_or_404(VoucherSlotPurchase, pk=pk)
        slot.status = 'rejected'
        slot.save()
        messages.success(request, f'Slot request #{slot.pk} rejected.')
    return redirect('vouchers:admin_dashboard')