import logging

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.db.models import Q, F, Count
from django.utils import timezone

logger = logging.getLogger(__name__)

from .models import (Job, JobApplication, CompanyProfile, ShopProfile,
                     JobSeekerProfile, SeekerCertificate, SavedJob, Interview,
                     Conversation, Message, OfferLetter,
                     Advertiser, AdPackage, Advertisement, AdPayment,
                     State, District, AdminProfile, Industry, JobRole,
                     PaymentPlan, Discount, Complaint, SystemNotification, PinCode,
                     UserNotification, SavedCandidate, Wallet, WalletTransaction,
                     EmployerSubscription, BillingRecord,
                     PointsWallet, PointsTransaction, Referral,
                     SpinGift, UserSpin, LocalOffer, AdPost)

User = get_user_model()


# ── PINCODE LOOKUP API ────────────────────────────────────────────────────────
def api_pincode_lookup(request, pin):
    """Return area/district/state for a 6-digit PIN code."""
    try:
        pc = PinCode.objects.select_related('district', 'district__state').get(code=pin, is_active=True)
        return JsonResponse({
            'success': True,
            'area':     pc.area_name or pc.district.name,
            'district': pc.district.name,
            'state':    pc.district.state.name,
        })
    except PinCode.DoesNotExist:
        pass
    # Fallback: India Post public API
    try:
        import urllib.request as ur, json as _json
        with ur.urlopen(f'https://api.postalpincode.in/pincode/{pin}', timeout=4) as resp:
            data = _json.loads(resp.read())[0]
        if data.get('Status') == 'Success' and data.get('PostOffice'):
            po = data['PostOffice'][0]
            return JsonResponse({
                'success': True,
                'area':     po.get('Name', ''),
                'district': po.get('District', ''),
                'state':    po.get('State', ''),
            })
    except Exception:
        pass
    return JsonResponse({'success': False})


# ── HOME ──────────────────────────────────────────────────────────────────────
def home(request):
    import random as _random
    from django.utils import timezone as tz
    today = tz.now().date()

    # ── Ads ─────────────────────────────────────────────
    # Fetch active ads in one query (replaces 5 × ORDER BY RAND() queries).
    # Pool cap of 90 covers all realistic ad inventory; shuffle in Python.
    ads_active = Advertisement.objects.filter(status='active', start_date__lte=today, end_date__gte=today)
    _ad_pool   = list(ads_active.select_related('package')[:90])
    _random.shuffle(_ad_pool)

    def _pick_ads(ad_type, n):
        return [a for a in _ad_pool if a.package.ad_type == ad_type][:n]

    homepage_banners   = _pick_ads('homepage_banner', 3)
    featured_employers = _pick_ads('featured_employer', 6)
    featured_job_ads   = _pick_ads('featured_job', 6)
    _sidebar           = _pick_ads('sidebar', 1)
    sidebar_ad         = _sidebar[0] if _sidebar else None
    _popup             = _pick_ads('popup', 1)
    popup_ad           = _popup[0] if _popup else None

    # track views — same UPDATE logic, now using already-fetched PKs
    all_shown_pks = (
        [a.pk for a in homepage_banners]
        + [a.pk for a in featured_employers]
        + [a.pk for a in featured_job_ads]
        + ([sidebar_ad.pk] if sidebar_ad else [])
        + ([popup_ad.pk] if popup_ad else [])
    )
    if all_shown_pks:
        Advertisement.objects.filter(pk__in=all_shown_pks).update(views=F('views') + 1)

    # ── Approved advertiser banners ──────────────────────
    # Fetch up to 60 rows (all approved banners in practice), shuffle in Python.
    _adv_pool = list(
        Advertiser.objects.filter(status='approved', banner_image__isnull=False).exclude(banner_image='')[:60]
    )
    _random.shuffle(_adv_pool)
    advertiser_banners = _adv_pool[:6]

    # ── Live simple ads (AdPost) ─────────────────────────
    _adpost_pool = list(
        AdPost.objects.filter(status='approved').filter(
            Q(expires_at__isnull=True) | Q(expires_at__gte=today)
        )[:60]
    )
    _random.shuffle(_adpost_pool)
    live_ads = _adpost_pool[:12]

    # Track views for AdPost ads shown on home page
    live_ad_pks = [a.pk for a in live_ads]
    if live_ad_pks:
        AdPost.objects.filter(pk__in=live_ad_pks).update(views=F('views') + 1)


    # ── Jobs & employers ────────────────────────────────
    featured_jobs = Job.objects.filter(status='active').select_related('posted_by').order_by('-created_at')[:8]

    # ── Stats — cached 5 min to avoid COUNT on every request ─────────────────
    from django.core.cache import cache
    stats = cache.get('homepage_stats')
    if not stats:
        stats = {
            'total_jobs':      Job.objects.filter(status='active').count(),
            'total_employers': User.objects.filter(user_type__in=User.EMPLOYER_TYPES).count(),
            'total_seekers':   User.objects.filter(user_type__in=['employee', 'individual', 'freelancer']).count(),
            'total_districts': District.objects.filter(is_active=True).count(),
        }
        cache.set('homepage_stats', stats, 300)
    total_jobs      = stats['total_jobs']
    total_employers = stats['total_employers']
    total_seekers   = stats['total_seekers']
    total_districts = stats['total_districts']

    # ── Spin to Win ─────────────────────────────────────
    spin_gift = SpinGift.objects.filter(is_active=True).first()
    already_spun = (
        request.user.is_authenticated and
        UserSpin.objects.filter(user=request.user, date=today).exists()
    )

    # ── Industries ───────────────────────────────────────
    industries = Industry.objects.filter(is_active=True).order_by('order')[:12]

    # ── Jobs by District — single aggregated query instead of N+1 ───────────
    active_pin_job_counts = dict(
        Job.objects.filter(status='active')
        .values('pincode')
        .annotate(cnt=Count('id'))
        .values_list('pincode', 'cnt')
    )
    active_districts = District.objects.filter(is_active=True).prefetch_related('pincodes')[:12]
    districts_jobs = []
    for d in active_districts:
        pin_list = [p.code for p in d.pincodes.all()]
        d.job_count = sum(active_pin_job_counts.get(p, 0) for p in pin_list)
        districts_jobs.append(d)
    districts_jobs.sort(key=lambda d: d.job_count, reverse=True)

    # ── Jobs by PIN Code — reuse the counts dict, no extra queries ────────────
    pincode_jobs = [
        {'pin': pin, 'count': active_pin_job_counts.get(pin.code, 0)}
        for pin in PinCode.objects.filter(is_active=True).select_related('district', 'district__state')[:20]
        if active_pin_job_counts.get(pin.code, 0) > 0
    ]
    pincode_jobs.sort(key=lambda x: x['count'], reverse=True)

    # ── Business logo strip ─────────────────────────────────────────────────────
    from .models import CompanyProfile
    business_logos = list(
        CompanyProfile.objects.filter(logo__isnull=False).exclude(logo='')
        .select_related('user').order_by('-user__date_joined')[:30]
    )
    _random.shuffle(business_logos)
    business_logos = business_logos[:20]

    return render(request, 'index.html', {
        'featured_jobs':       featured_jobs,
        'business_logos':      business_logos,
        'homepage_banners':    homepage_banners,
        'featured_employers':  featured_employers,
        'featured_job_ads':    featured_job_ads,
        'sidebar_ad':          sidebar_ad,
        'popup_ad':            popup_ad,
        'industries':          industries,
        'districts_jobs':      districts_jobs,
        'pincode_jobs':        pincode_jobs,
        'total_jobs':          total_jobs,
        'total_employers':     total_employers,
        'total_seekers':       total_seekers,
        'total_districts':     total_districts,
        'advertiser_banners':  advertiser_banners,
        'live_ads':            live_ads,
        'spin_gift':           spin_gift,
        'already_spun':        already_spun,
    })


# ── REGISTER ─────────────────────────────────────────────────────────────────
def register(request):
    ref_code = request.GET.get('ref', '').strip().upper()
    existing_business = None
    if request.user.is_authenticated and request.user.is_employer():
        existing_business = (
            getattr(request.user, 'company', None) or
            getattr(request.user, 'shop', None) or
            getattr(request.user, 'factory', None) or
            getattr(request.user, 'startup', None) or
            getattr(request.user, 'institution', None) or
            getattr(request.user, 'ngo', None) or
            getattr(request.user, 'hospital', None) or
            getattr(request.user, 'hotel', None) or
            getattr(request.user, 'farm', None)
        )
    registered_companies = CompanyProfile.objects.filter(
        company_name__isnull=False
    ).exclude(company_name='').order_by('-id')[:50]
    return render(request, 'register.html', {
        'ref_code': ref_code,
        'existing_business': existing_business,
        'registered_companies': registered_companies,
    })


def register_process(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid method'})

    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    def err(msg):
        if is_ajax:
            return JsonResponse({'success': False, 'error': msg})
        messages.error(request, msg)
        return redirect('register')

    user_type  = request.POST.get('user_type', '').strip()
    if user_type not in User.EMPLOYER_TYPES and user_type not in ('employee', 'freelancer'):
        user_type = 'individual'
    password   = request.POST.get('password', '')
    phone      = request.POST.get('phone', '').strip()
    email      = request.POST.get('email', '').strip()
    first_name = (request.POST.get('first_name', '') or request.POST.get('owner_name', '')).strip()
    last_name  = request.POST.get('last_name', '').strip()
    address    = request.POST.get('address', '').strip()
    city       = request.POST.get('city', '').strip()
    pincode    = (request.POST.get('pincode', '') or request.POST.get('emp_pincode', '')).strip()
    whatsapp   = request.POST.get('whatsapp', '').strip()
    ref_code   = request.POST.get('ref_code', '').strip().upper()

    from django.db import IntegrityError as _IntegrityError

    # If already logged in and registering a business — link to existing account
    if request.user.is_authenticated and user_type in User.EMPLOYER_TYPES:
        user = request.user
        user.user_type = user_type
        if pincode: user.pincode = pincode
        # Save business phone if provided and not already taken
        if phone and phone != user.phone:
            if not User.objects.filter(business_phone=phone).exclude(pk=user.pk).exists():
                user.business_phone = phone
        if password:
            user.set_password(password)
        try:
            user.save()
        except Exception:
            logger.exception('register_process: user.save() failed (authenticated link) user=%s', user.pk)
            return err('Registration failed. Please try again.')
    else:
        username = phone if phone else email
        if not username:
            return err('Phone or email is required.')

        if not password:
            return err('Password is required.')

        existing_user = User.objects.filter(username=username).first() or \
                        User.objects.filter(phone=phone).first() if phone else None
        if existing_user:
            if user_type in User.EMPLOYER_TYPES:
                user = existing_user
                if password: user.set_password(password)
                user.user_type = user_type
                if first_name: user.first_name = first_name
                if pincode: user.pincode = pincode
                try:
                    user.save()
                except Exception:
                    logger.exception('register_process: user.save() failed (existing employer) user=%s', user.pk)
                    return err('Registration failed. Please try again.')
            else:
                return err('An account already exists with this phone. Please login instead.')
        else:
            try:
                from .utils import generate_referral_code
                user = User.objects.create_user(
                    username=username,
                    password=password,
                    first_name=first_name,
                    last_name=last_name,
                    email=email,
                    phone=phone,
                    whatsapp=whatsapp,
                    user_type=user_type,
                    address=address,
                    city=city,
                    pincode=pincode,
                    referral_code=generate_referral_code(),
                )
            except _IntegrityError:
                logger.exception('register_process: create_user IntegrityError phone=%s', phone)
                return err('An account already exists with this phone or email. Please login instead.')
            except Exception:
                logger.exception('register_process: create_user failed phone=%s', phone)
                return err('Registration failed. Please try again.')

    # Track referral and award signup bonus
    if ref_code:
        referrer = User.objects.filter(referral_code=ref_code).first()
        if referrer and referrer != user:
            Referral.objects.create(referrer=referrer, referred=user, bonus_signup=True)
            from .utils import award_referral_points
            award_referral_points(
                referrer, 50, 'referral_signup',
                f'{user.get_full_name() or user.username} joined using your referral link!'
            )

    org_name = (
        request.POST.get('org_name', '').strip()
        or request.POST.get('company_name', '').strip()
        or f"{first_name} {last_name}".strip()
    )

    try:
        if user_type in User.EMPLOYER_TYPES:
            logo_file = request.FILES.get('logo') or None
            banner_file = request.FILES.get('banner_image') or None
            cp_defaults = dict(
                company_name=org_name,
                industry=request.POST.get('industry', '').strip(),
                website=request.POST.get('website', '').strip(),
                company_size=request.POST.get('company_size', '').strip(),
            )
            if logo_file:
                cp_defaults['logo'] = logo_file
            if banner_file:
                cp_defaults['banner_image'] = banner_file
            CompanyProfile.objects.update_or_create(user=user, defaults=cp_defaults)
            # Generate salesman BIZ ID if not already set
            if not user.salesman_biz_id:
                from .utils import generate_biz_id
                user.salesman_biz_id = generate_biz_id()
                User.objects.filter(pk=user.pk).update(salesman_biz_id=user.salesman_biz_id)
            if user_type == 'shop':
                sp_defaults = dict(
                    shop_name=org_name,
                    shop_type=request.POST.get('shop_type', '').strip(),
                    owner_name=first_name,
                    website=request.POST.get('website', '').strip(),
                )
                if logo_file:
                    sp_defaults['logo'] = logo_file
                if banner_file:
                    sp_defaults['banner_image'] = banner_file
                ShopProfile.objects.update_or_create(user=user, defaults=sp_defaults)
        elif user_type in ('employee', 'individual', 'freelancer'):
            seeker_defaults = dict(
                job_category=request.POST.get('job_category', ''),
                primary_skill=request.POST.get('primary_skill', ''),
                rate=request.POST.get('rate', ''),
            )
            seeker, _ = JobSeekerProfile.objects.get_or_create(user=user, defaults=seeker_defaults)
            if not _:
                # existing — update collar and skill
                if request.POST.get('job_category'):
                    seeker.job_category = request.POST.get('job_category')
                if request.POST.get('primary_skill'):
                    seeker.primary_skill = request.POST.get('primary_skill')
            if request.FILES.get('photo'):
                seeker.photo = request.FILES['photo']
            if request.FILES.get('resume'):
                seeker.resume = request.FILES['resume']
            seeker.save()
    except Exception:
        logger.exception('register_process: profile create failed for user %s type=%s', user.pk, user_type)
        # User account was created — log them in; profile can be completed later.

    login(request, user, backend='jobs.backends.PhoneOrEmailBackend')
    request.session['show_referral_popup'] = True

    if user_type in User.EMPLOYER_TYPES:
        redirect_url = '/employer/dashboard/'
    elif user_type == 'employee':
        redirect_url = '/jobs/'
    else:
        redirect_url = '/'

    if is_ajax:
        return JsonResponse({'success': True, 'redirect': redirect_url})
    return redirect(redirect_url)


# ── AUTH ──────────────────────────────────────────────────────────────────────
def forgot_password(request):
    phone = request.GET.get('phone', '')
    return render(request, 'forgot_password.html', {'prefill_phone': phone})


def login_view(request):
    from django.utils.http import url_has_allowed_host_and_scheme
    raw_next = request.GET.get('next', '') or request.POST.get('next', '')
    next_url = raw_next if url_has_allowed_host_and_scheme(
        raw_next, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ) else ''

    if request.user.is_authenticated:
        return redirect(next_url or 'dashboard')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                from django.http import JsonResponse as _JR
                return _JR({'success': True, 'redirect': next_url or '/'})
            return redirect(next_url or 'dashboard')
        # Check if the user exists at all
        user_exists = User.objects.filter(phone=username).exists() or \
                      User.objects.filter(email=username).exists() or \
                      User.objects.filter(username=username).exists()
        if not user_exists:
            error_msg = 'No account found. Please register first.'
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                from django.http import JsonResponse as _JR
                return _JR({'success': False, 'error': error_msg, 'not_registered': True})
            messages.error(request, error_msg)
            return render(request, 'login.html', {'next': next_url, 'not_registered': True, 'tried_username': username})
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            from django.http import JsonResponse as _JR
            return _JR({'success': False, 'error': 'Invalid phone/email or password.'})
        messages.error(request, 'Invalid phone/email or password.')

    return render(request, 'login.html', {'next': next_url})


def logout_view(request):
    logout(request)
    return redirect('home')


@login_required
def dashboard(request):
    role = request.user.admin_role
    if role == 'super_admin':
        return redirect('super_admin_dashboard')
    if role == 'state_admin':
        return redirect('state_admin_dashboard')
    if role == 'district_admin':
        return redirect('district_admin_dashboard')
    if request.user.user_type in User.EMPLOYER_TYPES or CompanyProfile.objects.filter(user=request.user).exists():
        return redirect('employer_dashboard')
    if request.user.user_type == 'advertiser' or hasattr(request.user, 'advertiser'):
        return redirect('advertiser_dashboard')

    # Community leader — redirect to their community
    try:
        from portal.models import CommunityLeader
        leader = CommunityLeader.objects.filter(
            user=request.user, status='accepted'
        ).select_related('community').first()
        if leader:
            return redirect(f'/portal/c/{leader.community.page_id}/')
    except Exception:
        pass

    return redirect('home')


# ── JOBS ──────────────────────────────────────────────────────────────────────
def job_list(request):
    jobs = Job.objects.filter(status='active', is_approved=True, job_plan__in=['free', 'paid'], posted_by__user_type__in=User.EMPLOYER_TYPES)

    collar    = request.GET.get('collar', '')
    category  = request.GET.get('category', '')
    pincode   = request.GET.get('pincode', '')
    q         = request.GET.get('q', '')
    radius_km = request.GET.get('radius', '')

    if collar:
        jobs = jobs.filter(collar_type=collar)
    if category:
        jobs = jobs.filter(category__icontains=category)
    if q:
        jobs = jobs.filter(Q(title__icontains=q) | Q(category__icontains=q) | Q(location__icontains=q))

    nearby_pairs = None
    radius_error = None

    if pincode and radius_km:
        # Nearby radius search
        try:
            from .utils import geocode_pincode, jobs_within_radius
            radius_km = float(radius_km)
            lat, lng = geocode_pincode(pincode)
            if lat:
                nearby_pairs = jobs_within_radius(lat, lng, radius_km, queryset=jobs)
                # nearby_pairs is [(job, dist_km), ...]
                jobs = [pair[0] for pair in nearby_pairs]
            else:
                radius_error = f"Could not locate pincode {pincode}. Showing all results."
                jobs = jobs.filter(pincode=pincode) if pincode else jobs
        except (ValueError, TypeError):
            radius_error = "Invalid radius value."
            jobs = jobs.filter(pincode=pincode) if pincode else jobs
    elif pincode:
        jobs = jobs.filter(pincode=pincode)

    total = len(jobs) if isinstance(jobs, list) else jobs.count()

    return render(request, 'job_list.html', {
        'jobs':         jobs,
        'nearby_pairs': nearby_pairs,
        'collar':       collar,
        'q':            q,
        'pincode':      pincode,
        'radius':       radius_km,
        'radius_error': radius_error,
        'total':        total,
    })


def job_detail(request, pk):
    job = get_object_or_404(Job, pk=pk, status='active', is_approved=True, job_plan__in=['free', 'paid'])
    already_applied = False
    is_saved = False
    if request.user.is_authenticated:
        already_applied = JobApplication.objects.filter(job=job, applicant=request.user).exists()
        is_saved = SavedJob.objects.filter(user=request.user, job=job).exists()
    related = Job.objects.filter(collar_type=job.collar_type, status='active', is_approved=True, job_plan__in=['free', 'paid']).exclude(pk=pk)[:3]
    return render(request, 'job_detail.html', {
        'job': job,
        'already_applied': already_applied,
        'is_saved': is_saved,
        'related': related,
    })


def _application_missing_fields(seeker):
    if not seeker:
        return ['job_category', 'experience', 'qualification', 'primary_skill']
    missing = []
    if seeker.job_category not in ('blue', 'white'):
        missing.append('job_category')
    if not seeker.experience:
        missing.append('experience')
    if seeker.job_category != 'blue' and not seeker.education:
        missing.append('qualification')
    if seeker.job_category == 'blue':
        if not seeker.blue_collar_type:
            missing.append('blue_collar_type')
    elif not (seeker.primary_skill or seeker.skills):
        missing.append('primary_skill')
    if seeker.job_category == 'white' and not seeker.resume:
        missing.append('resume')
    return missing


@login_required
def apply_job(request, pk):
    job = get_object_or_404(Job, pk=pk, status='active', is_approved=True, job_plan__in=['free', 'paid'])

    # Already applied — redirect back
    existing = JobApplication.objects.filter(job=job, applicant=request.user).first()
    if existing:
        messages.warning(request, 'You have already applied for this job.')
        return redirect('job_detail', pk=pk)

    # Load seeker profile for pre-fill
    try:
        seeker = request.user.seeker
    except Exception:
        seeker = None

    if request.method == 'GET':
        return render(request, 'job_apply_confirm.html', {'job': job, 'seeker': seeker, 'user': request.user})

    if request.method == 'POST':
        p = request.POST
        category = p.get('job_category', '')
        if category not in ('blue', 'white'):
            messages.error(request, 'Choose Blue Collar or White Collar.')
            return redirect('apply_job', pk=pk)
        seeker, _ = JobSeekerProfile.objects.get_or_create(user=request.user)
        resume = request.FILES.get('application_resume')
        if resume:
            from pathlib import Path
            if Path(resume.name).suffix.lower() not in ('.pdf', '.doc', '.docx') or resume.size > 5 * 1024 * 1024:
                messages.error(request, 'Upload a PDF, DOC or DOCX resume smaller than 5 MB.')
                return redirect('apply_job', pk=pk)
            seeker.resume = resume
        seeker.job_category = category
        seeker.save()
        if _application_missing_fields(seeker):
            messages.error(request, 'Complete the fields highlighted in red before applying.')
            return redirect(f'/profile/edit/?next=/jobs/{pk}/apply/')
        if p.get('quick_apply') == '1' and seeker:
            # Quick apply: use saved profile data
            app = JobApplication(
                job=job,
                applicant=request.user,
                cover_note=p.get('cover_note', '').strip(),
                expected_salary=str(seeker.salary_min) if seeker.salary_min else '',
                declared=True,
            )
            if seeker.resume:
                app.application_resume = seeker.resume
            app.save()
        else:
            app = JobApplication(
                job=job,
                applicant=request.user,
                cover_note=p.get('cover_note', '').strip(),
                expected_salary=p.get('expected_salary', '').strip(),
                notice_period=p.get('notice_period', '').strip(),
                employment_type=p.get('employment_type', '').strip(),
                why_join=p.get('why_join', '').strip(),
                why_suitable=p.get('why_suitable', '').strip(),
                currently_employed=p.get('currently_employed') == 'yes',
                how_heard=p.get('how_heard', '').strip(),
                declared=bool(p.get('declared')),
            )
            if seeker.resume:
                app.application_resume = seeker.resume
            if 'cover_letter_file' in request.FILES:
                app.cover_letter_file = request.FILES['cover_letter_file']
            app.save()
        messages.success(request, 'Application submitted successfully!')
        # Referral bonus
        try:
            ref = Referral.objects.get(referred=request.user, bonus_action=False)
            if JobApplication.objects.filter(applicant=request.user).count() == 1:
                from .utils import award_referral_points
                award_referral_points(ref.referrer, 25, 'referral_apply',
                    f'{request.user.get_full_name() or request.user.username} applied for their first job!')
                ref.bonus_action = True
                ref.save(update_fields=['bonus_action'])
        except Referral.DoesNotExist:
            pass
        return redirect('job_detail', pk=pk)


# ── POST JOB ──────────────────────────────────────────────────────────────────
@login_required
def post_job(request):
    # Block if employer profile is incomplete
    user = request.user
    if user.is_employer():
        try:
            prof = user.company
        except Exception:
            prof = None
        score = 0
        if prof and prof.company_name: score += 10
        if user.pincode:               score += 20
        if user.city:                  score += 15
        if user.address:               score += 15
        if prof and prof.industry:     score += 20
        if prof and prof.company_size: score += 10
        if prof and prof.website:      score += 10
        if score < 70:
            return redirect('employer_dashboard')

    if request.method == 'POST':
        import datetime
        p = request.POST
        last_date_str = p.get('last_date', '')
        last_date = None
        if last_date_str:
            try:
                last_date = datetime.datetime.strptime(last_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass

        action = p.get('action', 'publish')
        status = 'draft' if action == 'draft' else 'active'

        Job.objects.create(
            posted_by       = request.user,
            title           = p.get('title', ''),
            collar_type     = p.get('collar_type', 'white'),
            industry        = p.get('industry', ''),
            category        = p.get('category', ''),
            description     = p.get('description', ''),
            job_type        = p.get('job_type', 'full_time'),
            experience      = p.get('experience', ''),
            education       = p.get('education', ''),
            gender_preference = p.get('gender_preference', 'any'),
            age_min         = p.get('age_min') or None,
            age_max         = p.get('age_max') or None,
            skills          = p.get('skills', ''),
            language        = p.get('language', 'Any'),
            salary_min      = p.get('salary_min') or None,
            salary_max      = p.get('salary_max') or None,
            salary_type     = p.get('salary_type', 'month'),
            benefits        = p.get('benefits', ''),
            vacancies       = p.get('vacancies', 1),
            shift           = p.get('shift', 'day'),
            working_days    = p.get('working_days', ''),
            accommodation   = 'accommodation' in p,
            food_provided   = 'food_provided' in p,
            transport       = 'transport' in p,
            location        = p.get('location', ''),
            pincode         = p.get('pincode', ''),
            latitude        = p.get('latitude') or None,
            longitude       = p.get('longitude') or None,
            contact_phone   = p.get('contact_phone', ''),
            is_urgent       = 'is_urgent' in p,
            interview_type  = p.get('interview_type', 'walkin'),
            last_date       = last_date,
            status          = status,
        )
        if status == 'draft':
            messages.success(request, 'Job saved as draft.')
        else:
            messages.success(request, 'Job submitted! Admin will review and approve it shortly.')
            request.session['show_job_posted_popup'] = p.get('title', 'Your job')
            # Referral bonus: first job posted by a referred employer
            try:
                ref = Referral.objects.get(referred=request.user, bonus_action=False)
                first_job = Job.objects.filter(posted_by=request.user).count() == 1
                if first_job:
                    from .utils import award_referral_points
                    award_referral_points(
                        ref.referrer, 100, 'referral_job',
                        f'{request.user.get_full_name() or request.user.username} posted their first job!'
                    )
                    ref.bonus_action = True
                    ref.save(update_fields=['bonus_action'])
            except Referral.DoesNotExist:
                pass
        return redirect('employer_dashboard')

    industries = Industry.objects.filter(is_active=True).prefetch_related('roles')
    return render(request, 'post_job.html', {'industries': industries})


@login_required
def job_select_plan(request, pk):
    import datetime
    job = get_object_or_404(Job, pk=pk, posted_by=request.user)

    if not job.is_approved:
        messages.warning(request, 'This job is still pending admin approval.')
        return redirect('employer_dashboard')

    if job.job_plan and job.job_plan not in ('', 'free_expired'):
        messages.info(request, 'A plan is already active for this job.')
        return redirect('employer_dashboard')

    is_upgrade = job.job_plan == 'free_expired'

    if request.method == 'POST':
        plan = request.POST.get('plan')

        if plan == 'free':
            job.job_plan = 'free'
            job.plan_expires_at = datetime.date.today() + datetime.timedelta(weeks=2)
            job.save()
            from .utils import notify_seekers_for_job
            notify_seekers_for_job(job)
            messages.success(request, 'Free plan activated! Your job is now live for 2 weeks.')
            return redirect('employer_dashboard')

        elif plan == 'paid_confirm':
            screenshot = request.FILES.get('screenshot')
            if not screenshot:
                messages.error(request, 'Please upload the payment screenshot.')
                return render(request, 'job_select_plan.html', {'job': job, 'show_qr': True, 'is_upgrade': is_upgrade})
            job.job_plan = 'paid_pending'
            job.payment_screenshot = screenshot
            job.save()
            messages.success(request, 'Payment screenshot submitted! Admin will verify and activate your plan shortly.')
            return redirect('employer_dashboard')

    return render(request, 'job_select_plan.html', {'job': job, 'show_qr': False, 'is_upgrade': is_upgrade})


@login_required
def edit_job(request, pk):
    job = get_object_or_404(Job, pk=pk, posted_by=request.user)
    if request.method == 'POST':
        import datetime
        p = request.POST
        last_date_str = p.get('last_date', '')
        last_date = None
        if last_date_str:
            try:
                last_date = datetime.datetime.strptime(last_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass

        action = p.get('action', 'publish')
        job.title             = p.get('title', job.title)
        job.collar_type       = p.get('collar_type', job.collar_type)
        job.industry          = p.get('industry', job.industry)
        job.category          = p.get('category', job.category)
        job.description       = p.get('description', job.description)
        job.job_type          = p.get('job_type', job.job_type)
        job.experience        = p.get('experience', job.experience)
        job.education         = p.get('education', job.education)
        job.gender_preference = p.get('gender_preference', job.gender_preference)
        job.age_min           = p.get('age_min') or None
        job.age_max           = p.get('age_max') or None
        job.skills            = p.get('skills', job.skills)
        job.language          = p.get('language', job.language)
        job.salary_min        = p.get('salary_min') or None
        job.salary_max        = p.get('salary_max') or None
        job.salary_type       = p.get('salary_type', job.salary_type)
        job.benefits          = p.get('benefits', job.benefits)
        job.vacancies         = p.get('vacancies', job.vacancies)
        job.shift             = p.get('shift', job.shift)
        job.working_days      = p.get('working_days', job.working_days)
        job.accommodation     = 'accommodation' in p
        job.food_provided     = 'food_provided' in p
        job.transport         = 'transport' in p
        job.location          = p.get('location', job.location)
        job.pincode           = p.get('pincode', job.pincode)
        job.latitude          = p.get('latitude') or None
        job.longitude         = p.get('longitude') or None
        job.contact_phone     = p.get('contact_phone', job.contact_phone)
        job.is_urgent         = 'is_urgent' in p
        job.interview_type    = p.get('interview_type', job.interview_type)
        job.last_date         = last_date
        job.status            = 'draft' if action == 'draft' else 'active'
        job.save()
        messages.success(request, 'Job updated successfully!')
        return redirect('employer_dashboard')

    industries = Industry.objects.filter(is_active=True).prefetch_related('roles')
    return render(request, 'edit_job.html', {'job': job, 'industries': industries})


def business_profile(request, company_id):
    from .models import CompanyProfile, Flick, LocalOffer, AdPost
    profile = get_object_or_404(CompanyProfile, company_id=company_id)
    owner = profile.user
    user_type = owner.user_type

    # Offers by this business
    offers = LocalOffer.objects.filter(
        business_name__iexact=profile.company_name, is_active=True
    ).order_by('-created_at')[:20]

    # Flicks posted by owner
    flicks = Flick.objects.filter(user=owner).order_by('-created_at')[:12]

    # Gallery: ad post images + offer images
    gallery_images = []
    for ap in AdPost.objects.filter(user=owner, status='approved').order_by('-created_at')[:20]:
        if ap.image:
            gallery_images.append(ap.image.url)
    for o in LocalOffer.objects.filter(business_name__iexact=profile.company_name, is_active=True):
        if o.image:
            gallery_images.append(o.image.url)
    gallery_images = list(dict.fromkeys(gallery_images))[:24]

    # Active jobs posted by this business
    jobs = Job.objects.filter(
        posted_by=owner, status='active', is_approved=True,
        job_plan__in=['free', 'paid']
    ).order_by('-created_at')[:20]

    # Gallery: uploaded gallery images + ad post images + offer images
    from .models import BusinessGalleryImage
    gallery_uploaded = BusinessGalleryImage.objects.filter(user=owner).order_by('-created_at')[:20]
    gallery_images = [g.image.url for g in gallery_uploaded if g.image]
    for ap in AdPost.objects.filter(user=owner, status='approved').order_by('-created_at')[:20]:
        if ap.image:
            gallery_images.append(ap.image.url)
    for o in LocalOffer.objects.filter(business_name__iexact=profile.company_name, is_active=True):
        if o.image:
            gallery_images.append(o.image.url)
    gallery_images = list(dict.fromkeys(gallery_images))[:24]

    # Gift vouchers via vouchers Business model
    vouchers = []
    vbiz = None
    try:
        from vouchers.models import Business as VBusiness, GiftVoucher
        vbiz = VBusiness.objects.filter(owner=owner, status='approved').first()
        if vbiz:
            vouchers = GiftVoucher.objects.filter(
                business=vbiz, status='published'
            ).order_by('-created_at')[:10]
    except Exception:
        pass

    return render(request, 'business_profile.html', {
        'profile': profile,
        'owner': owner,
        'user_type': user_type,
        'offers': offers,
        'offers_count': offers.count(),
        'jobs': jobs,
        'jobs_count': jobs.count(),
        'vouchers': vouchers,
        'vouchers_count': len(vouchers),
        'flicks': flicks,
        'flicks_count': flicks.count(),
        'gallery_images': gallery_images,
        'vbiz': vbiz,
    })


# ── DASHBOARDS ────────────────────────────────────────────────────────────────
@login_required
def employer_dashboard(request):
    user = request.user

    # ── Auto-generate salesman BIZ ID for existing employers ──
    if user.is_employer() and not user.salesman_biz_id:
        from .utils import generate_biz_id
        User.objects.filter(pk=user.pk).update(salesman_biz_id=generate_biz_id())
        user.refresh_from_db(fields=['salesman_biz_id'])

    # ── Auto-expire free plans ──
    import datetime
    today = datetime.date.today()
    to_expire = Job.objects.filter(posted_by=user, job_plan='free', plan_expires_at__lt=today, status='active')
    for _job in to_expire:
        _job.job_plan = 'free_expired'
        _job.save(update_fields=['job_plan'])
        UserNotification.objects.get_or_create(
            user=user,
            link=f'/jobs/{_job.pk}/select-plan/',
            defaults={
                'title': f'Free Week Ended: {_job.title}',
                'message': f'Your 2-week free listing for "{_job.title}" has expired. Upgrade to 12 weeks for ₹499!',
                'notif_type': 'warning',
            },
        )

    # ── Jobs ──
    active_jobs       = Job.objects.filter(posted_by=user, status='active', is_approved=True, job_plan__in=['free', 'paid']).order_by('-created_at')
    expired_jobs      = Job.objects.filter(posted_by=user, status='active', is_approved=True, job_plan='free_expired').order_by('-created_at')
    paid_pending_jobs = Job.objects.filter(posted_by=user, status='active', is_approved=True, job_plan='paid_pending').order_by('-created_at')
    plan_pending      = Job.objects.filter(posted_by=user, status='active', is_approved=True, job_plan='').order_by('-created_at')
    approval_pending  = Job.objects.filter(posted_by=user, status='active', is_approved=False).order_by('-created_at')
    pending_jobs      = Job.objects.filter(posted_by=user, status='draft').order_by('-created_at')
    closed_jobs       = Job.objects.filter(posted_by=user, status='closed').order_by('-created_at')

    # ── Applications ──
    all_apps    = JobApplication.objects.filter(job__posted_by=user).select_related('applicant', 'job').order_by('-applied_at')
    shortlisted = all_apps.filter(status='shortlisted')

    # ── Saved candidates ──
    saved_candidates = SavedCandidate.objects.filter(employer=user).select_related('candidate')

    # ── Messages ──
    user_convs       = Conversation.objects.filter(Q(user_a=user) | Q(user_b=user))
    unread_msg_count = Message.objects.filter(conversation__in=user_convs, is_read=False).exclude(sender=user).count()
    recent_convs     = user_convs.select_related('user_a', 'user_b', 'job').order_by('-updated_at')[:8]
    recent_messages  = [{'conv': c, 'other': c.other_user(user),
                         'last': c.messages.order_by('-sent_at').first(),
                         'unread': c.unread_for(user)} for c in recent_convs]

    # ── Notifications ──
    notifs       = UserNotification.objects.filter(user=user)[:12]
    unread_notif_count = UserNotification.objects.filter(user=user, is_read=False).count()

    # ── Wallet ──
    wallet, _ = Wallet.objects.get_or_create(user=user)
    wallet_txns = WalletTransaction.objects.filter(wallet=wallet).order_by('-created_at')[:10]

    # ── Subscription ──
    current_sub = EmployerSubscription.objects.filter(
        employer=user, status='active'
    ).select_related('plan').first()
    available_plans = PaymentPlan.objects.filter(
        is_active=True, plan_type__startswith='employer'
    )

    # ── Billing history ──
    billing_records = BillingRecord.objects.filter(user=user).order_by('-created_at')[:10]

    # ── Profile ──
    try:
        profile = user.company
    except Exception:
        profile = None

    # ── Profile completion ──
    def _pct(u, p):
        score = 0
        if p and p.company_name: score += 10
        if u.pincode:             score += 20
        if u.city:                score += 15
        if u.address:             score += 15
        if p and p.industry:      score += 20
        if p and p.company_size:  score += 10
        if p and p.website:       score += 10
        return score

    profile_pct = _pct(user, profile)
    profile_incomplete = profile_pct < 70

    show_referral_popup = request.session.pop('show_referral_popup', False)
    referral_link = request.build_absolute_uri(f'/register/?ref={request.user.referral_code}') if request.user.referral_code else ''
    job_posted_title = request.session.pop('show_job_posted_popup', None)

    from .models import Flick, FlickLike
    recent_flicks = Flick.objects.select_related('user').prefetch_related('likes')[:12]
    liked_ids = set(FlickLike.objects.filter(user=request.user).values_list('flick_id', flat=True))

    # ── Gift Voucher stats ──
    try:
        from vouchers.models import Business as VoucherBusiness, GiftVoucher, VoucherPurchase
        from django.db.models import Sum as VSum
        voucher_business = VoucherBusiness.objects.filter(owner=request.user).first()
        if voucher_business:
            recent_vouchers  = GiftVoucher.objects.filter(business=voucher_business).order_by('-created_at')[:5]
            voucher_count    = GiftVoucher.objects.filter(business=voucher_business).count()
            voucher_purchases = VoucherPurchase.objects.filter(
                gift_voucher__business=voucher_business, status__in=['paid','sent','redeemed']).count()
            voucher_revenue  = VoucherPurchase.objects.filter(
                gift_voucher__business=voucher_business, status__in=['paid','sent','redeemed']
            ).aggregate(t=VSum('amount_paid'))['t'] or 0
        else:
            recent_vouchers = voucher_count = voucher_purchases = voucher_revenue = None
    except Exception:
        voucher_business = recent_vouchers = voucher_count = voucher_purchases = voucher_revenue = None

    from .models import AdPost, LocalOffer, BusinessGalleryImage
    my_ad_posts = AdPost.objects.filter(user=user, status='approved').order_by('-created_at')[:30]
    my_gallery = BusinessGalleryImage.objects.filter(user=user).order_by('-created_at')[:60]
    my_offers = LocalOffer.objects.filter(
        business_name__iexact=profile.company_name if profile else '', is_active=True
    ).order_by('-created_at')[:30] if profile else []

    return render(request, 'employer_dashboard.html', {
        'active_jobs':        active_jobs,
        'my_ad_posts':        my_ad_posts,
        'my_offers':          my_offers,
        'my_gallery':         my_gallery,
        'expired_jobs':       expired_jobs,
        'paid_pending_jobs':  paid_pending_jobs,
        'plan_pending':       plan_pending,
        'approval_pending':   approval_pending,
        'pending_jobs':       pending_jobs,
        'closed_jobs':        closed_jobs,
        'all_apps':           all_apps,
        'shortlisted':        shortlisted,
        'saved_candidates':   saved_candidates,
        'unread_msg_count':   unread_msg_count,
        'recent_messages':    recent_messages,
        'notifs':             notifs,
        'unread_notif_count': unread_notif_count,
        'wallet':             wallet,
        'wallet_txns':        wallet_txns,
        'current_sub':        current_sub,
        'available_plans':    available_plans,
        'billing_records':    billing_records,
        'profile':            profile,
        'profile_pct':        profile_pct,
        'profile_incomplete': profile_incomplete,
        'show_referral_popup': show_referral_popup,
        'referral_link':      referral_link,
        'job_posted_title':   job_posted_title,
        'recent_flicks':      recent_flicks,
        'liked_ids':          liked_ids,
        'voucher_business':   voucher_business,
        'recent_vouchers':    recent_vouchers,
        'voucher_count':      voucher_count,
        'voucher_purchases':  voucher_purchases,
        'voucher_revenue':    voucher_revenue,
    })


@login_required
def gallery_upload(request):
    if request.method != 'POST':
        return redirect('employer_dashboard')
    from .models import BusinessGalleryImage
    images = request.FILES.getlist('gallery_images')
    for img in images[:10]:
        BusinessGalleryImage.objects.create(
            user=request.user,
            image=img,
            caption=request.POST.get('caption', '').strip()[:200],
        )
    from django.contrib import messages as dj_messages
    dj_messages.success(request, f'{len(images)} image(s) uploaded to your gallery.')
    return redirect('/employer/dashboard/#gallery')


@login_required
def gallery_delete(request, pk):
    from .models import BusinessGalleryImage
    img = get_object_or_404(BusinessGalleryImage, pk=pk, user=request.user)
    img.image.delete(save=False)
    img.delete()
    return redirect('/employer/dashboard/#gallery')


@login_required
def employer_profile_save(request):
    if request.method != 'POST':
        return redirect('employer_dashboard')
    user = request.user
    p = request.POST
    user.city    = p.get('city', '').strip()
    user.address = p.get('address', '').strip()
    user.pincode = p.get('pincode', '').strip()
    user.email   = p.get('email', '').strip()
    user.whatsapp = p.get('whatsapp', '').strip()
    biz_phone = p.get('business_phone', '').strip()
    if biz_phone:
        # Make sure no other user has this business phone
        User = get_user_model()
        if not User.objects.filter(business_phone=biz_phone).exclude(pk=user.pk).exists():
            user.business_phone = biz_phone
    try:
        user.save()
    except Exception:
        logger.exception('employer_profile_save: user.save() failed for user %s', user.pk)
        messages.error(request, 'Could not save your profile. Please try again.')
        return redirect('employer_dashboard')
    try:
        prof = user.company
    except Exception:
        prof = None
    if prof:
        prof.industry     = p.get('industry', '').strip()
        prof.company_size = p.get('company_size', '').strip()
        prof.website      = p.get('website', '').strip()
        if request.FILES.get('logo'):
            prof.logo = request.FILES['logo']
        if request.FILES.get('banner_image'):
            prof.banner_image = request.FILES['banner_image']
        try:
            prof.save()
        except Exception:
            logger.exception('employer_profile_save: prof.save() failed for user %s', user.pk)
            messages.error(request, 'Could not save your profile. Please try again.')
            return redirect('employer_dashboard')
    messages.success(request, 'Profile saved successfully.')
    return redirect('employer_dashboard')


@login_required
def jobseeker_dashboard(request):
    applications = JobApplication.objects.filter(applicant=request.user).select_related('job')
    try:
        profile = request.user.seeker
        qs = Job.objects.filter(status='active', is_approved=True, job_plan__in=['free', 'paid'])
        if profile.job_category and profile.job_category != 'any':
            qs = qs.filter(collar_type=profile.job_category)
        recommended = qs.order_by('-created_at')[:4]
    except Exception:
        profile = None
        recommended = Job.objects.filter(status='active', is_approved=True, job_plan__in=['free', 'paid']).order_by('-created_at')[:4]
    notifs = UserNotification.objects.filter(user=request.user).order_by('-created_at')[:12]
    unread_notif_count = UserNotification.objects.filter(user=request.user, is_read=False).count()
    show_referral_popup = request.session.pop('show_referral_popup', False)
    referral_link = request.build_absolute_uri(f'/register/?ref={request.user.referral_code}') if request.user.referral_code else ''
    from .models import Flick, FlickLike
    recent_flicks = Flick.objects.filter(user=request.user).select_related('user').prefetch_related('likes').order_by('-created_at')[:12]
    liked_ids = set(FlickLike.objects.filter(user=request.user).values_list('flick_id', flat=True))
    return render(request, 'jobseeker_dashboard.html', {
        'applications':       applications,
        'recommended':        recommended,
        'profile':            profile,
        'notifs':             notifs,
        'unread_notif_count': unread_notif_count,
        'show_referral_popup': show_referral_popup,
        'referral_link':      referral_link,
        'recent_flicks':      recent_flicks,
        'liked_ids':          liked_ids,
    })


@login_required
def view_applicant_profile(request, pk):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    applicant = get_object_or_404(User, pk=pk)
    seeker = getattr(applicant, 'seeker', None)
    # Only employers who have received an application from this person can view
    if not request.user.is_employer():
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    return render(request, 'applicant_profile.html', {'applicant': applicant, 'seeker': seeker})


@login_required
def seeker_profile(request):
    profile, _ = JobSeekerProfile.objects.get_or_create(user=request.user)
    states    = State.objects.filter(is_active=True).order_by('name')
    districts = District.objects.filter(is_active=True).order_by('name')
    industries = Industry.objects.filter(is_active=True).prefetch_related('roles')
    certificates = profile.certificates.all()

    if request.method == 'POST':
        p = request.POST
        f = request.FILES

        # ── Personal ──────────────────────────────────────────
        user = request.user
        first_name = p.get('first_name', '').strip()
        last_name  = p.get('last_name', '').strip()
        if first_name:
            user.first_name = first_name
        if last_name:
            user.last_name = last_name
        user.address  = p.get('address', '').strip()
        user.city     = p.get('city', '').strip()
        user.pincode  = p.get('pincode', '').strip()
        user.whatsapp = p.get('whatsapp', '').strip()
        user.save()

        dob_str = p.get('dob', '').strip()
        try:
            from datetime import date
            profile.dob = date.fromisoformat(dob_str) if dob_str else None
        except ValueError:
            profile.dob = None

        profile.gender   = p.get('gender', '')
        if 'photo' in f:
            profile.photo = f['photo']

        # ── Location ──────────────────────────────────────────
        district_id = p.get('district', '')
        state_id    = p.get('state', '')
        profile.district_id       = int(district_id) if district_id else None
        profile.state_id          = int(state_id)    if state_id    else None
        profile.preferred_location = p.get('preferred_location', '').strip()
        profile.preferred_pincode  = p.get('preferred_pincode',  '').strip()
        profile.open_to_relocate   = 'open_to_relocate' in p

        # ── Career ────────────────────────────────────────────
        profile.job_category     = p.get('job_category', 'any')
        profile.blue_collar_type = p.get('blue_collar_type', '').strip()
        profile.industry         = p.get('industry', '').strip()
        profile.preferred_roles = p.get('preferred_roles', '').strip()
        profile.availability    = p.get('availability', 'immediate')

        # ── Salary ────────────────────────────────────────────
        sal_min = p.get('salary_min', '').strip()
        sal_max = p.get('salary_max', '').strip()
        profile.salary_min  = int(sal_min) if sal_min.isdigit() else None
        profile.salary_max  = int(sal_max) if sal_max.isdigit() else None
        profile.salary_type = p.get('salary_type', 'month')
        profile.rate        = p.get('rate', '').strip()

        # ── Qualifications ────────────────────────────────────
        profile.education         = p.get('education', '').strip()
        profile.education_details = p.get('education_details', '').strip()
        profile.experience        = p.get('experience', '').strip()
        profile.skills            = p.get('skills', '').strip()
        profile.languages         = p.get('languages', '').strip()
        profile.primary_skill     = p.get('primary_skill', '').strip()

        # ── Documents ─────────────────────────────────────────
        if 'resume' in f:
            profile.resume = f['resume']
        if 'driving_license' in f:
            profile.driving_license = f['driving_license']
        if 'portfolio_file' in f:
            profile.portfolio_file = f['portfolio_file']
        profile.portfolio_url = p.get('portfolio_url', '').strip()

        profile.profile_completed = True
        profile.save()

        # ── Certificates (add new ones) ────────────────────────
        cert_titles = p.getlist('cert_title')
        cert_issuers = p.getlist('cert_issuer')
        cert_years  = p.getlist('cert_year')
        cert_files  = f.getlist('cert_file')
        for i, title in enumerate(cert_titles):
            title = title.strip()
            if not title:
                continue
            cert = SeekerCertificate(
                seeker=profile,
                title=title,
                issued_by=cert_issuers[i] if i < len(cert_issuers) else '',
                issued_year=cert_years[i] if i < len(cert_years) else '',
            )
            if i < len(cert_files) and cert_files[i]:
                cert.file = cert_files[i]
            cert.save()

        # ── Delete removed certificates ────────────────────────
        delete_cert_ids = p.getlist('delete_cert')
        if delete_cert_ids:
            SeekerCertificate.objects.filter(
                pk__in=delete_cert_ids, seeker=profile
            ).delete()

        return redirect('seeker_profile')

    pct = profile.completion_percent()
    ctx = {
        'profile':              profile,
        'certificates':         certificates,
        'states':               states,
        'districts':            districts,
        'industries':           industries,
        'user':                 request.user,
        'skills_list':          [s.strip() for s in (profile.skills or '').split(',') if s.strip()],
        'langs_list':           [l.strip() for l in (profile.languages or '').split(',') if l.strip()],
        'roles_list':           [r.strip() for r in (profile.preferred_roles or '').split(',') if r.strip()],
        'completion_pct':       pct,
        'completion_remaining': 100 - pct,
    }
    return render(request, 'seeker_profile.html', ctx)


@login_required
def seeker_cert_delete(request, cert_id):
    SeekerCertificate.objects.filter(pk=cert_id, seeker__user=request.user).delete()
    return redirect('seeker_profile')




# ── Rate limiting helpers ─────────────────────────────────────────────────────
def _rate_limit(cache_key, max_attempts, window_seconds):
    """Returns True if the action is allowed, False if rate limit exceeded."""
    from django.core.cache import cache
    count = cache.get(cache_key, 0)
    if count >= max_attempts:
        return False
    cache.set(cache_key, count + 1, window_seconds)
    return True


def _get_client_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


# ── OTP via 2Factor.in ────────────────────────────────────────────────────────
def send_otp(request):
    if request.method != 'POST':
        return JsonResponse({'success': False})

    import json, random, requests as _req
    try:
        data = json.loads(request.body)
        phone = data.get('phone', '').strip()
    except Exception:
        phone = request.POST.get('phone', '').strip()

    if not phone or len(phone) != 10 or not phone.isdigit():
        return JsonResponse({'success': False, 'error': 'Enter a valid 10-digit mobile number.'})

    # Rate limit: max 3 OTP sends per phone per 10 minutes
    if not _rate_limit(f'otp_send_{phone}', max_attempts=3, window_seconds=600):
        return JsonResponse({'success': False, 'error': 'Too many OTP requests. Please wait 10 minutes.'}, status=429)

    User = get_user_model()
    allow_existing = data.get('allow_existing', False) if isinstance(data, dict) else False
    if User.objects.filter(phone=phone).exists() and not allow_existing:
        return JsonResponse({'success': False,
                             'error': 'This phone number is already registered. Please sign in.'})

    import secrets as _secrets
    otp = str(_secrets.randbelow(900000) + 100000)

    from django.conf import settings as _s
    api_key  = _s.TWO_FACTOR_API_KEY
    template = _s.TWO_FACTOR_OTP_TEMPLATE

    # Dev fallback: if no API key, skip SMS and print OTP to console
    if not api_key:
        print(f'\n[DEV OTP] Phone: {phone}  OTP: {otp}\n', flush=True)
        request.session['otp']          = otp
        request.session['otp_phone']    = phone
        request.session['otp_verified'] = False
        request.session.modified = True
        return JsonResponse({'success': True})

    url = f'https://2factor.in/API/V1/{api_key}/SMS/{phone}/{otp}/{template}'

    try:
        resp   = _req.get(url, timeout=10)
        result = resp.json()
    except Exception:
        return JsonResponse({'success': False, 'error': 'SMS service unavailable. Try again.'})

    if result.get('Status') == 'Success':
        request.session['otp']         = otp
        request.session['otp_phone']   = phone
        request.session['otp_verified'] = False
        request.session.modified = True
        return JsonResponse({'success': True})
    else:
        logger.warning('send_otp: 2factor API error for phone=%s status=%s details=%s',
                       phone, result.get('Status'), result.get('Details'))
        return JsonResponse({'success': False, 'error': 'Failed to send OTP. Please try again.'})


def verify_otp(request):
    if request.method != 'POST':
        return JsonResponse({'success': False})

    import json
    data    = json.loads(request.body)
    entered = data.get('otp', '').strip()
    stored  = request.session.get('otp', '')
    phone   = request.session.get('otp_phone', '')

    if not stored:
        return JsonResponse({'success': False, 'error': 'OTP expired. Please resend.'})

    # Rate limit: max 5 wrong attempts per phone before requiring re-send
    if phone and not _rate_limit(f'otp_verify_{phone}', max_attempts=5, window_seconds=600):
        request.session.pop('otp', None)
        request.session.pop('otp_verified', None)
        return JsonResponse({'success': False, 'error': 'Too many wrong attempts. Please request a new OTP.'}, status=429)

    if entered == stored:
        request.session['otp_verified'] = True
        request.session.pop('otp', None)
        # Clear verify attempt counter on success
        from django.core.cache import cache
        cache.delete(f'otp_verify_{phone}')
        return JsonResponse({'success': True})

    return JsonResponse({'success': False, 'error': 'Wrong OTP. Please try again.'})


def check_phone(request):
    """Check if a phone number is already registered."""
    if request.method != 'POST':
        return JsonResponse({'exists': False})
    import json
    data  = json.loads(request.body)
    phone = data.get('phone', '').strip()
    User  = get_user_model()
    user  = User.objects.filter(phone=phone).first()
    if user:
        return JsonResponse({'exists': True, 'name': user.first_name or user.username})
    return JsonResponse({'exists': False})


def forgot_password(request):
    phone = request.GET.get('phone', '')
    return render(request, 'forgot_password.html', {'prefill_phone': phone})


def reset_password(request):
    """Reset password after OTP verification (forgot-password flow)."""
    if request.method != 'POST':
        return JsonResponse({'success': False})
    import json
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'success': False, 'error': 'Invalid request'})
    phone    = data.get('phone', '').strip()
    password = data.get('password', '').strip()

    if not request.session.get('otp_verified'):
        return JsonResponse({'success': False, 'error': 'OTP not verified'})

    # Ensure the OTP was verified for THIS phone number, not a different one
    if request.session.get('otp_phone') != phone:
        return JsonResponse({'success': False, 'error': 'OTP verification mismatch. Please restart.'})

    if not phone or not password or len(password) < 6:
        return JsonResponse({'success': False, 'error': 'Invalid data'})

    User = get_user_model()
    user = User.objects.filter(phone=phone).first()
    if not user:
        return JsonResponse({'success': False, 'error': 'Invalid request. Please restart the process.'})

    user.set_password(password)
    user.save()
    from django.contrib.auth import login as auth_login
    auth_login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    request.session.pop('otp_verified', None)
    request.session.pop('otp_phone', None)

    if user.is_employer() or CompanyProfile.objects.filter(user=user).exists():
        redirect_url = '/employer/dashboard/'
    else:
        redirect_url = '/'
    return JsonResponse({'success': True, 'redirect': redirect_url})


def phone_login(request):
    """Login with personal phone or business phone + password."""
    if request.method != 'POST':
        return JsonResponse({'success': False})
    import json
    data     = json.loads(request.body)
    phone    = data.get('phone', '').strip()
    password = data.get('password', '')

    # Rate limit: max 5 login attempts per IP per 5 minutes
    ip = _get_client_ip(request)
    if not _rate_limit(f'login_ip_{ip}', max_attempts=5, window_seconds=300):
        return JsonResponse({'success': False, 'error': 'Too many login attempts. Please wait 5 minutes.'}, status=429)

    User     = get_user_model()
    # Try personal phone first, then business phone
    user = User.objects.filter(phone=phone).first() or \
           User.objects.filter(business_phone=phone).first()
    if user and user.check_password(password):
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        if user.is_employer() or CompanyProfile.objects.filter(user=user).exists():
            redirect_url = '/employer/dashboard/'
        else:
            redirect_url = '/'
        return JsonResponse({'success': True, 'redirect': redirect_url})
    return JsonResponse({'success': False, 'error': 'Wrong phone number or password. Try again.'})


def send_register_otp(request):
    """Generate OTP, store in session, send via email if phone looks like email."""
    if request.method != 'POST':
        return JsonResponse({'success': False})
    import json, random
    from django.core.mail import send_mail
    data  = json.loads(request.body)
    phone = data.get('phone', '').strip()
    name  = data.get('name', '').strip()
    if not phone or not name:
        return JsonResponse({'success': False, 'error': 'Name and phone are required'})
    User = get_user_model()
    if User.objects.filter(phone=phone).exists():
        return JsonResponse({'success': False, 'error': 'This phone number is already registered. Please sign in.'})
    otp = str(random.randint(100000, 999999))
    request.session['reg_otp']   = otp
    request.session['reg_phone'] = phone
    request.session['reg_name']  = name
    request.session['reg_data']  = data
    # Try to email if input looks like email
    if '@' in phone:
        try:
            send_mail(
                'OUR PINCODE — Your OTP',
                f'Hi {name},\n\nYour OTP to register on OUR PINCODE is: {otp}\n\nValid for 10 minutes.',
                None, [phone], fail_silently=True,
            )
        except Exception:
            pass
    return JsonResponse({'success': True, 'otp_sent': True})


def verify_register_otp(request):
    """Verify OTP then create the user account."""
    if request.method != 'POST':
        return JsonResponse({'success': False})
    import json
    data = json.loads(request.body)
    otp_input = data.get('otp', '').strip()
    stored_otp = request.session.get('reg_otp')
    if not stored_otp or otp_input != stored_otp:
        return JsonResponse({'success': False, 'error': 'Invalid OTP. Please try again.'})
    reg_data = request.session.get('reg_data', {})
    name     = reg_data.get('name', '').strip()
    phone    = reg_data.get('phone', '').strip()
    pincode  = reg_data.get('pincode', '').strip()
    password = reg_data.get('password', '').strip()
    if not name or not phone or not pincode or not password:
        return JsonResponse({'success': False, 'error': 'Missing registration data. Please start again.'})
    User = get_user_model()
    if User.objects.filter(phone=phone).exists():
        return JsonResponse({'success': False, 'error': 'Already registered. Please sign in.'})
    username = phone
    if User.objects.filter(username=username).exists():
        import random as _r
        username = phone + str(_r.randint(10, 99))
    user = User.objects.create_user(
        username=username, first_name=name, phone=phone,
        pincode=pincode, user_type='individual', password=password,
    )
    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    for k in ('reg_otp', 'reg_phone', 'reg_name', 'reg_data'):
        request.session.pop(k, None)
    return JsonResponse({'success': True, 'redirect': '/'})


def quick_register(request):
    """Create basic user profile after OTP verification from onboarding modal."""
    if request.method != 'POST':
        return JsonResponse({'success': False})

    import json
    data     = json.loads(request.body)
    name     = data.get('name', '').strip()
    phone    = data.get('phone', '').strip()
    pincode  = data.get('pincode', '').strip()
    job_type = data.get('job_type', 'find')
    collar   = data.get('collar', '')
    password = data.get('password', '').strip()

    if not name or not phone or not pincode:
        return JsonResponse({'success': False, 'error': 'Missing required fields'})
    if not password or len(password) < 6:
        return JsonResponse({'success': False, 'error': 'Password must be at least 6 characters'})

    User = get_user_model()

    if User.objects.filter(phone=phone).exists():
        return JsonResponse({'success': False, 'error': 'This phone number is already registered. Please sign in.'})

    user_type = 'individual'
    username  = phone
    if User.objects.filter(username=username).exists():
        import random
        username = phone + str(random.randint(10, 99))

    user = User.objects.create_user(
        username   = username,
        first_name = name,
        phone      = phone,
        pincode    = pincode,
        user_type  = user_type,
        password   = password,
    )

    # Store collar preference in seeker profile
    if job_type == 'find' and collar:
        from .models import JobSeekerProfile
        profile, _ = JobSeekerProfile.objects.get_or_create(user=user)
        profile.job_category = collar
        profile.save()

    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    return JsonResponse({'success': True, 'redirect': '/'})


# ── SAVE JOB ──────────────────────────────────────────────────────────────────
@login_required
def save_job(request, pk):
    job = get_object_or_404(Job, pk=pk)
    saved, created = SavedJob.objects.get_or_create(user=request.user, job=job)
    if not created:
        saved.delete()
        return JsonResponse({'saved': False, 'msg': 'Job removed from saved list'})
    return JsonResponse({'saved': True, 'msg': 'Job saved!'})


@login_required
def saved_jobs(request):
    saves = SavedJob.objects.filter(user=request.user).select_related('job')
    return render(request, 'saved_jobs.html', {'saves': saves})


# ── CLOSE JOB ─────────────────────────────────────────────────────────────────
@login_required
def close_job(request, pk):
    from .models import Job
    job = get_object_or_404(Job, pk=pk, posted_by=request.user)
    job.status = 'closed'
    job.save(update_fields=['status'])
    messages.success(request, f'"{job.title}" has been closed.')
    return redirect('employer_dashboard')


# ── SHORTLIST APPLICATION ──────────────────────────────────────────────────────
@login_required
def shortlist_application(request, pk):
    app = get_object_or_404(JobApplication, pk=pk, job__posted_by=request.user)
    app.status = 'shortlisted'
    app.save(update_fields=['status'])
    messages.success(request, f'{app.applicant.get_full_name() or app.applicant.username} shortlisted.')
    return redirect('employer_dashboard')


# ── REJECT APPLICATION ─────────────────────────────────────────────────────────
@login_required
def reject_application(request, pk):
    app = get_object_or_404(JobApplication, pk=pk, job__posted_by=request.user)
    app.status = 'rejected'
    app.save(update_fields=['status'])
    messages.success(request, 'Application rejected.')
    return redirect('employer_dashboard')


# ── WITHDRAW APPLICATION ───────────────────────────────────────────────────────
@login_required
def withdraw_application(request, pk):
    app = get_object_or_404(JobApplication, pk=pk, applicant=request.user)
    if app.status in ('pending', 'shortlisted'):
        app.status = 'withdrawn'
        app.save()
        messages.success(request, 'Application withdrawn.')
    else:
        messages.error(request, 'Cannot withdraw at this stage.')
    return redirect('jobseeker_dashboard')


# ── MESSAGING ─────────────────────────────────────────────────────────────────
def _get_or_create_conv(user1, user2, job=None):
    a, b = (user1, user2) if user1.pk < user2.pk else (user2, user1)
    conv, _ = Conversation.objects.get_or_create(user_a=a, user_b=b, job=job)
    return conv


def _render_bubble(msg, me):
    from django.template.loader import render_to_string
    return render_to_string('partials/msg_bubble.html', {'msg': msg, 'me': me})


def _msg_to_dict(msg, me):
    d = {
        'id':      msg.pk,
        'sender':  msg.sender_id,
        'mine':    msg.sender_id == me.id,
        'type':    msg.msg_type,
        'content': msg.content,
        'time':    msg.sent_at.strftime('%I:%M %p'),
        'is_read': msg.is_read,
        'html':    _render_bubble(msg, me),
    }
    if msg.file:
        d['file_url']  = msg.file.url
        d['file_name'] = msg.file_name
    if msg.msg_type == 'interview_invite':
        d['invite'] = {
            'date':     str(msg.invite_date) if msg.invite_date else '',
            'time':     str(msg.invite_time) if msg.invite_time else '',
            'mode':     msg.invite_mode,
            'location': msg.invite_location,
            'link':     msg.invite_link,
            'notes':    msg.invite_notes,
            'status':   msg.invite_status,
        }
    return d


def _sidebar_data(user):
    convs = Conversation.objects.filter(
        Q(user_a=user) | Q(user_b=user)
    ).select_related('user_a', 'user_b', 'job').order_by('-updated_at')
    rows = []
    for c in convs:
        last = c.messages.order_by('-sent_at').first()
        rows.append({'conv': c, 'other': c.other_user(user),
                     'last': last, 'unread': c.unread_for(user)})
    return rows


@login_required
def chat_list(request):
    sidebar      = _sidebar_data(request.user)
    total_unread = sum(d['unread'] for d in sidebar)
    return render(request, 'messages.html', {
        'conversations': sidebar,
        'total_unread':  total_unread,
        'active_conv':   None,
    })


@login_required
def chat_room(request, conv_id, **_):
    conv = get_object_or_404(Conversation, pk=conv_id)
    me   = request.user
    if conv.user_a != me and conv.user_b != me:
        return redirect('chat_list')
    conv.messages.filter(is_read=False).exclude(sender=me).update(
        is_read=True, read_at=timezone.now()
    )
    sidebar = _sidebar_data(me)
    msgs    = conv.messages.select_related('sender').order_by('sent_at')
    return render(request, 'messages.html', {
        'conversations': sidebar,
        'active_conv':   conv,
        'other':         conv.other_user(me),
        'msgs':          msgs,
        'total_unread':  sum(d['unread'] for d in sidebar),
    })


@login_required
def start_conversation(request, user_id, job_id=0):
    other = get_object_or_404(User, pk=user_id)
    job   = Job.objects.filter(pk=job_id).first() if job_id else None
    conv  = _get_or_create_conv(request.user, other, job)
    return redirect('chat_room', conv_id=conv.pk)


@login_required
def send_message(request):
    if request.method != 'POST':
        return JsonResponse({'ok': False})
    conv = get_object_or_404(Conversation, pk=request.POST.get('conv_id'))
    me   = request.user
    if conv.user_a != me and conv.user_b != me:
        return JsonResponse({'ok': False}, status=403)

    other    = conv.other_user(me)
    msg_type = request.POST.get('msg_type', 'text')
    content  = request.POST.get('content', '').strip()
    f        = request.FILES.get('file')

    msg = Message(conversation=conv, sender=me, receiver=other,
                  job=conv.job, msg_type=msg_type, content=content)

    if msg_type == 'interview_invite':
        msg.invite_date     = request.POST.get('invite_date') or None
        msg.invite_time     = request.POST.get('invite_time') or None
        msg.invite_mode     = request.POST.get('invite_mode', '')
        msg.invite_location = request.POST.get('invite_location', '')
        msg.invite_link     = request.POST.get('invite_link', '')
        msg.invite_notes    = request.POST.get('invite_notes', '')
        msg.invite_status   = 'pending'
        msg.content         = content or 'Interview Invitation'

    if f:
        ext = f.name.rsplit('.', 1)[-1].lower() if '.' in f.name else ''
        if ext in ('jpg', 'jpeg', 'png', 'gif', 'webp'):
            try:
                from PIL import Image as _PILImage
                import io as _io
                _img = _PILImage.open(_io.BytesIO(f.read()))
                _img.verify()
                f.seek(0)
            except Exception:
                return JsonResponse({'ok': False, 'error': 'Invalid image file.'}, status=400)
            msg.msg_type = 'image'
        else:
            msg.msg_type = msg_type if msg_type == 'resume' else 'file'
        msg.file      = f
        msg.file_name = f.name

    msg.save()
    conv.save()   # bumps updated_at

    UserNotification.objects.create(
        user=other,
        title=f'New message from {me.get_full_name() or me.username}',
        message=(content or (f.name if f else ''))[:80],
        notif_type='info',
        link=f'/messages/{conv.pk}/',
    )
    return JsonResponse({'ok': True, 'msg_id': msg.pk, 'html': _render_bubble(msg, me)})


@login_required
def poll_messages(request, conv_id):
    conv = get_object_or_404(Conversation, pk=conv_id)
    me   = request.user
    if conv.user_a != me and conv.user_b != me:
        return JsonResponse({'ok': False}, status=403)
    after    = int(request.GET.get('after', 0))
    new_msgs = conv.messages.filter(pk__gt=after).exclude(sender=me)
    new_msgs.filter(is_read=False).update(is_read=True, read_at=timezone.now())
    return JsonResponse({'ok': True, 'messages': [_msg_to_dict(m, me) for m in new_msgs]})


@login_required
def respond_invite(request, msg_id):
    msg    = get_object_or_404(Message, pk=msg_id, msg_type='interview_invite')
    me     = request.user
    action = request.POST.get('action', '')
    if msg.receiver == me and action in ('accepted', 'rejected'):
        msg.invite_status = action
        msg.save()
        UserNotification.objects.create(
            user=msg.sender,
            title=f'Interview {action.title()} by {me.get_full_name() or me.username}',
            message=f'Your interview invitation was {action}.',
            notif_type='success' if action == 'accepted' else 'warning',
            link=f'/messages/{msg.conversation_id}/',
        )
    return JsonResponse({'ok': True, 'status': msg.invite_status})


@login_required
def chat_messages_api(request, user_id, job_id=0):
    other = get_object_or_404(User, pk=user_id)
    conv  = _get_or_create_conv(request.user, other)
    return redirect('chat_room', conv_id=conv.pk)


# ==============================================================
# ADVERTISER MODULE
# ==============================================================

@login_required
def smart_marketing_story(request):
    return render(request, 'smart_marketing_story.html')

def ads_gallery(request):
    """Public page: show all ads same style as home page."""
    ads = Advertisement.objects.select_related('advertiser', 'package').order_by('-created_at')
    advertiser_banners = Advertiser.objects.filter(
        status='approved', banner_image__isnull=False
    ).exclude(banner_image='')
    cat = request.GET.get('cat', '')
    offers_qs = LocalOffer.objects.filter(is_active=True)
    if cat:
        offers_qs = offers_qs.filter(category=cat)
    flash_offers  = offers_qs.filter(is_flash=True)
    normal_offers = offers_qs.filter(is_flash=False)
    return render(request, 'ads_gallery.html', {
        'ads':               ads,
        'advertiser_banners': advertiser_banners,
        'flash_offers':      flash_offers,
        'normal_offers':     normal_offers,
        'active_cat':        cat,
        'offer_categories':  LocalOffer.CATEGORY_CHOICES,
    })


@login_required
def offer_post(request):
    """Only registered employers/companies can post offers."""
    user = request.user
    if not user.is_employer():
        from django.contrib import messages
        messages.error(request, 'Only registered companies can post offers. Please register as an employer.')
        return redirect('/register/')
    if request.method == 'POST':
        phone = request.POST.get('contact_phone', '').strip().replace(' ', '')
        # Build WhatsApp link from phone number
        wa_url = f"https://wa.me/91{phone}" if phone else ''
        obj = LocalOffer(
            business_name = request.POST.get('business_name', '').strip(),
            title         = request.POST.get('title', '').strip(),
            discount_text = request.POST.get('discount_text', '').strip(),
            category      = request.POST.get('category', 'other'),
            description   = request.POST.get('description', '').strip(),
            contact_phone = phone,
            link_url      = wa_url,
            is_flash      = request.POST.get('is_flash') == '1',
            is_active     = False,  # pending admin approval
        )
        valid_until = request.POST.get('valid_until', '').strip()
        if valid_until:
            obj.valid_until = valid_until
        valid_days = request.POST.get('valid_days', '').strip()
        if valid_days:
            obj.valid_days = valid_days
        if request.FILES.get('image'):
            obj.image = request.FILES['image']
        obj.save()
        return redirect('/offers/post/success/')
    profile = CompanyProfile.objects.filter(user=user).first()
    return render(request, 'offer_post.html', {
        'categories': LocalOffer.CATEGORY_CHOICES,
        'company_profile': profile,
    })


def offer_post_success(request):
    return render(request, 'offer_post_success.html')


def advertiser_register(request):
    """Only registered employer accounts can apply to advertise."""
    user = request.user

    if not user.is_authenticated:
        return redirect(f'/login/?next=/advertise/register/')

    # Block non-employer users
    if not user.is_employer():
        messages.error(request, 'Only registered business accounts (Company, Shop, Factory, etc.) can post advertisements. Please register as a business first.')
        return redirect('/register/?type=company')

    # Already has an advertiser profile — allow through only if rejected (re-apply flow)
    existing_adv = getattr(user, 'advertiser', None)
    if existing_adv and existing_adv.status != 'rejected':
        messages.info(request, 'You already have an advertiser profile.')
        return redirect('advertiser_dashboard')

    if request.method == 'POST':
        if existing_adv:
            # Re-apply: update existing record and reset to pending
            existing_adv.business_name  = request.POST.get('business_name', '').strip()
            existing_adv.contact_person = request.POST.get('contact_person', user.get_full_name()).strip()
            existing_adv.phone          = request.POST.get('phone', user.phone).strip()
            existing_adv.email          = request.POST.get('email', user.email).strip()
            existing_adv.address        = request.POST.get('address', '').strip()
            existing_adv.description    = request.POST.get('description', '').strip()
            existing_adv.gst            = request.POST.get('gst', '').strip()
            existing_adv.website        = request.POST.get('website', '').strip()
            existing_adv.status = 'pending'
            existing_adv.save()
        else:
            Advertiser.objects.create(
                business_name  = request.POST.get('business_name', '').strip(),
                contact_person = request.POST.get('contact_person', user.get_full_name()).strip(),
                phone          = request.POST.get('phone', user.phone).strip(),
                email          = request.POST.get('email', user.email).strip(),
                address        = request.POST.get('address', '').strip(),
                description    = request.POST.get('description', '').strip(),
                gst            = request.POST.get('gst', '').strip(),
                website        = request.POST.get('website', '').strip(),
                status         = 'pending',
                user           = user,
            )
        return redirect('advertiser_register_success')

    from .models import Flick, FlickLike
    recent_flicks = Flick.objects.select_related('user').order_by('-created_at')[:16]
    liked_ids = set()
    if request.user.is_authenticated:
        liked_ids = set(FlickLike.objects.filter(user=request.user).values_list('flick_id', flat=True))
    return render(request, 'advertiser_register.html', {
        'user': user,
        'adv': existing_adv,
        'reapply': existing_adv is not None,
        'recent_flicks': recent_flicks,
        'liked_ids': liked_ids,
    })


def advertiser_register_success(request):
    return render(request, 'advertiser_register_success.html')


@login_required
def advertiser_dashboard(request):
    try:
        adv = request.user.advertiser
    except Advertiser.DoesNotExist:
        messages.info(request, 'Please register as an advertiser first.')
        return redirect('advertiser_register')
    from .models import AdPost, AdSettings
    simple_ads   = AdPost.objects.filter(user=request.user).prefetch_related('renewals').order_by('-created_at')
    ad_settings  = AdSettings.get()
    total_views  = sum(a.views or 0 for a in simple_ads)
    total_clicks = sum(getattr(a, 'clicks', 0) or 0 for a in simple_ads)
    active_count = sum(1 for a in simple_ads if a.is_live)
    packages     = AdPackage.objects.filter(is_active=True)
    return render(request, 'advertiser_dashboard.html', {
        'adv': adv, 'ads': simple_ads,
        'total_views': total_views, 'total_clicks': total_clicks,
        'active_count': active_count, 'expiring': [],
        'packages': packages, 'settings': ad_settings,
    })


@login_required
def create_advertisement(request):
    return redirect('post_simple_ad')
    try:
        adv = request.user.advertiser
    except Advertiser.DoesNotExist:
        return redirect('advertiser_register')

    if adv.status != 'approved':
        messages.error(request, 'Your advertiser account is pending admin approval.')
        return redirect('advertiser_dashboard')

    packages = AdPackage.objects.filter(is_active=True)

    if request.method == 'POST':
        pkg_id = request.POST.get('package')
        pkg = get_object_or_404(AdPackage, pk=pkg_id, is_active=True)
        ad = Advertisement.objects.create(
            advertiser = adv,
            package    = pkg,
            title      = request.POST.get('title', '').strip(),
            link_url   = request.POST.get('link_url', '').strip(),
            content    = request.POST.get('content', '').strip(),
            district   = request.POST.get('district', '').strip(),
            state      = request.POST.get('state', '').strip(),
            status     = 'pending_payment',
        )
        if 'image' in request.FILES:
            ad.image = request.FILES['image']
            ad.save()
        import decimal
        gst   = (pkg.price * decimal.Decimal('0.18')).quantize(decimal.Decimal('0.01'))
        total = pkg.price + gst
        import random, string
        inv   = ''.join(random.choices(string.digits, k=8))
        AdPayment.objects.create(
            advertisement  = ad,
            amount         = pkg.price,
            gst_amount     = gst,
            total_amount   = total,
            invoice_number = inv,
        )
        return redirect('ad_payment', ad_id=ad.pk)

    # Pre-fill website from company/shop/advertiser profile
    user = request.user
    prefill_website = (
        adv.website
        or (user.company.website if hasattr(user, 'company') else '')
        or (user.shop.website    if hasattr(user, 'shop')    else '')
    )
    return render(request, 'create_ad.html', {'packages': packages, 'prefill_website': prefill_website})


@login_required
def ad_payment(request, ad_id):
    ad = get_object_or_404(Advertisement, pk=ad_id, advertiser__user=request.user)
    payment = ad.payment
    if request.method == 'POST':
        method = request.POST.get('method', 'upi')
        import uuid
        from django.utils import timezone as tz
        payment.status         = 'paid'
        payment.payment_method = method
        payment.transaction_id = str(uuid.uuid4())[:18].upper()
        payment.paid_at        = tz.now()
        payment.save()
        from datetime import date, timedelta
        ad.status     = 'pending_review'
        ad.start_date = date.today()
        ad.end_date   = date.today() + timedelta(days=ad.package.duration_days)
        ad.save()
        messages.success(request, f'Payment successful! Ad is under review and will go live soon.')
        return redirect('ad_payment_success', ad_id=ad.pk)
    return render(request, 'ad_payment.html', {'ad': ad, 'payment': payment})


@login_required
def ad_payment_success(request, ad_id):
    ad = get_object_or_404(Advertisement, pk=ad_id, advertiser__user=request.user)
    return render(request, 'ad_payment_success.html', {'ad': ad})


@login_required
def ad_performance(request, ad_id):
    ad = get_object_or_404(Advertisement, pk=ad_id, advertiser__user=request.user)
    return render(request, 'ad_performance.html', {'ad': ad})


@login_required
def advertiser_renew_ad(request, ad_id):
    ad = get_object_or_404(Advertisement, pk=ad_id, advertiser__user=request.user)
    if request.method == 'POST':
        import decimal
        pkg   = ad.package
        gst   = (pkg.price * decimal.Decimal('0.18')).quantize(decimal.Decimal('0.01'))
        total = pkg.price + gst
        import random, string
        inv   = ''.join(random.choices(string.digits, k=8))
        new_ad = Advertisement.objects.create(
            advertiser = ad.advertiser,
            package    = pkg,
            title      = ad.title,
            image      = ad.image,
            link_url   = ad.link_url,
            content    = ad.content,
            district   = ad.district,
            state      = ad.state,
            status     = 'pending_payment',
        )
        AdPayment.objects.create(
            advertisement  = new_ad,
            amount         = pkg.price,
            gst_amount     = gst,
            total_amount   = total,
            invoice_number = inv,
        )
        return redirect('ad_payment', ad_id=new_ad.pk)
    return render(request, 'renew_ad.html', {'ad': ad})


def _safe_ad_url(url):
    """Return url only if it uses http/https scheme; otherwise return None."""
    if url and isinstance(url, str):
        stripped = url.strip()
        if stripped.lower().startswith(('http://', 'https://')):
            return stripped
    return None


def ad_click_track(request, ad_id):
    """Tracks click and redirects to destination."""
    try:
        ad = Advertisement.objects.get(pk=ad_id, status='active')
        Advertisement.objects.filter(pk=ad_id).update(clicks=ad.clicks + 1)
        safe_url = _safe_ad_url(ad.link_url)
        if safe_url:
            return redirect(safe_url)
    except Advertisement.DoesNotExist:
        pass
    return redirect('home')


def adpost_click_track(request, ad_id):
    """Tracks click on an AdPost and redirects to its website."""
    from .models import AdPost
    try:
        ad = AdPost.objects.get(pk=ad_id, status='approved')
        AdPost.objects.filter(pk=ad_id).update(clicks=F('clicks') + 1)
        safe_url = _safe_ad_url(ad.website)
        if safe_url:
            return redirect(safe_url)
    except AdPost.DoesNotExist:
        pass
    return redirect('home')


# ── ADMIN: Advertiser Management ─────────────────────────────────────────────

def admin_required(view_func):
    from functools import wraps
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_staff:
            return redirect('login')
        return view_func(request, *args, **kwargs)
    return wrapper


@admin_required
def admin_advertisers(request):
    from urllib.parse import quote
    status_filter = request.GET.get('status', 'pending')
    advs = Advertiser.objects.filter(status=status_filter).order_by('-created_at')
    counts = {s: Advertiser.objects.filter(status=s).count()
              for s in ('pending', 'approved', 'rejected', 'suspended')}
    for adv in advs:
        phone = ''.join(ch for ch in (adv.phone or '') if ch.isdigit())
        if phone and not phone.startswith('91'):
            phone = '91' + phone
        name = adv.contact_person or adv.business_name
        msg_inquiry = f"Hi {name}, we received your advertiser registration ({adv.business_name}) on OURPINCODE.com. Are you interested in proceeding? Please confirm."
        msg_reject  = (
            f"Hi {name}, we received your advertiser registration ({adv.business_name}) on OURPINCODE.com. "
            f"Unfortunately, we are unable to approve this ad account creation. "
            f"Please make necessary edits and re-apply. "
            f"If you feel everything is correct, reach us at +91 9876543210. Thanks"
        )
        adv.wa_link        = f"https://wa.me/{phone}?text={quote(msg_inquiry)}" if phone else ''
        adv.wa_link_reject = f"https://wa.me/{phone}?text={quote(msg_reject)}"  if phone else ''
    return render(request, 'admin_advertisers.html', {
        'advs': advs, 'status_filter': status_filter, 'counts': counts,
    })


@admin_required
def admin_approve_advertiser(request, adv_id):
    adv = get_object_or_404(Advertiser, pk=adv_id)
    adv.status      = 'approved'
    adv.approved_at = timezone.now()
    adv.save()
    messages.success(request, f'{adv.business_name} approved!')
    return redirect('admin_advertisers')


@admin_required
def admin_reject_advertiser(request, adv_id):
    adv = get_object_or_404(Advertiser, pk=adv_id)
    adv.status         = 'rejected'
    adv.rejection_note = request.POST.get('note', '')
    adv.save()
    messages.info(request, f'{adv.business_name} rejected.')
    return redirect('admin_advertisers')


@admin_required
def admin_remove_advertiser(request, adv_id):
    if request.method == 'POST':
        adv = get_object_or_404(Advertiser, pk=adv_id)
        name = adv.business_name
        adv.delete()
        messages.success(request, f'{name} removed.')
    return redirect('admin_advertisers')


@admin_required
def admin_upload_advertiser_banner(request, adv_id):
    if request.method == 'POST':
        adv = get_object_or_404(Advertiser, pk=adv_id)
        if 'banner_image' in request.FILES:
            adv.banner_image = request.FILES['banner_image']
            adv.save()
            messages.success(request, f'Banner uploaded for {adv.business_name}.')
    return redirect(f'/admin-panel/advertisers/?status={request.POST.get("status", "approved")}')


@admin_required
def admin_ad_list(request):
    from urllib.parse import quote
    status_filter = request.GET.get('status', 'pending_review')
    ads = Advertisement.objects.filter(status=status_filter).select_related('advertiser', 'package').order_by('-created_at')
    for ad in ads:
        phone = ''.join(ch for ch in (ad.advertiser.phone or '') if ch.isdigit())
        if phone and not phone.startswith('91'):
            phone = '91' + phone
        name = ad.advertiser.contact_person or ad.advertiser.business_name
        msg = f"Hi {name}, we received your ad '{ad.title}' on Pincode Job Portal. Are you interested in proceeding? Please confirm."
        ad.wa_link = f"https://wa.me/{phone}?text={quote(msg)}" if phone else ''
    return render(request, 'admin_ad_list.html', {'ads': ads, 'status_filter': status_filter})


@admin_required
def admin_set_ad_image(request, ad_id):
    ad = get_object_or_404(Advertisement, pk=ad_id)
    if request.method == 'POST' and 'image' in request.FILES:
        ad.image = request.FILES['image']
        ad.save()
        messages.success(request, f'Image updated for "{ad.title}".')
    status_filter = request.POST.get('status_filter', 'pending_review')
    return redirect(f"/admin-panel/ads/?status={status_filter}")


@admin_required
def admin_activate_ad(request, ad_id):
    ad = get_object_or_404(Advertisement, pk=ad_id)
    ad.status = 'active'
    ad.save()
    Advertisement.objects.filter(pk=ad_id).update(views=ad.views)
    messages.success(request, f'Ad "{ad.title}" is now live!')
    return redirect('admin_ad_list')


@admin_required
def admin_reject_ad(request, ad_id):
    ad = get_object_or_404(Advertisement, pk=ad_id)
    ad.status = 'rejected'
    ad.save()
    messages.info(request, f'Ad "{ad.title}" rejected.')
    return redirect('admin_ad_list')


@admin_required
def admin_delete_ad(request, ad_id):
    ad = get_object_or_404(Advertisement, pk=ad_id)
    title = ad.title
    status_filter = request.POST.get('status_filter', 'pending_review')
    ad.delete()
    messages.success(request, f'Ad "{title}" deleted.')
    return redirect(f'/admin-panel/ads/?status={status_filter}')


# ── ADMIN USERS LIST ────────────────────────────────────────────────────────
@admin_required
def admin_users(request):
    return _users_list(request)


def super_admin_users(request):
    if not request.user.is_authenticated or request.user.admin_role != 'super_admin':
        messages.error(request, 'Super Admin access required.')
        return redirect('login')
    return _users_list(request)


def super_admin_delete_user(request, user_id):
    if not request.user.is_authenticated or request.user.admin_role != 'super_admin':
        messages.error(request, 'Super Admin access required.')
        return redirect('login')
    if request.method != 'POST':
        return redirect('super_admin_users')
    target = get_object_or_404(User, pk=user_id)
    if target.admin_role == 'super_admin':
        messages.error(request, 'Cannot delete another Super Admin.')
        return redirect('super_admin_users')
    name = target.get_full_name() or target.username
    target.delete()
    messages.success(request, f'User "{name}" deleted.')
    return redirect('super_admin_users')


def _users_list(request):
    from django.db.models import Q
    search   = request.GET.get('q', '').strip()
    utype    = request.GET.get('type', '')

    qs = User.objects.exclude(user_type='advertiser').order_by('-date_joined')

    if utype == 'employer':
        qs = qs.filter(user_type__in=User.EMPLOYER_TYPES)
    elif utype == 'jobseeker':
        qs = qs.filter(user_type__in=['employee', 'individual', 'freelancer'])
    elif utype == 'admin':
        qs = qs.exclude(admin_role='')

    if search:
        qs = qs.filter(
            Q(first_name__icontains=search) | Q(last_name__icontains=search) |
            Q(phone__icontains=search) | Q(email__icontains=search) |
            Q(pincode__icontains=search) | Q(city__icontains=search)
        )

    employer_count  = User.objects.filter(user_type__in=User.EMPLOYER_TYPES).count()
    jobseeker_count = User.objects.filter(user_type__in=['employee','individual','freelancer']).count()
    admin_count     = User.objects.exclude(admin_role='').count()

    return render(request, 'admin_users.html', {
        'users': qs,
        'search': search,
        'utype': utype,
        'employer_count': employer_count,
        'jobseeker_count': jobseeker_count,
        'admin_count': admin_count,
        'total_count': User.objects.exclude(user_type='advertiser').count(),
    })


# ── ADMIN PANEL LOGIN ────────────────────────────────────────────────────────
def admin_panel_login(request):
    if request.method != 'POST':
        return redirect('home')
    if not _rate_limit(f'admin_login_{_get_client_ip(request)}', max_attempts=5, window_seconds=300):
        messages.error(request, 'Too many login attempts. Please wait 5 minutes.')
        return redirect('home')
    phone    = request.POST.get('phone', '').strip()
    password = request.POST.get('password', '').strip()
    user = authenticate(request, username=phone, password=password)
    if user and getattr(user, 'admin_role', None):
        login(request, user, backend='jobs.backends.PhoneOrEmailBackend')
        role = user.admin_role
        if role == 'super_admin':
            return redirect('/super-admin/')
        elif role == 'state_admin':
            return redirect('/state-admin/')
        else:
            return redirect('/district-admin/')
    messages.error(request, 'Invalid phone number / password, or not an admin account.')
    return redirect('home')


# ── NEARBY JOBS API ──────────────────────────────────────────────────────────
def nearby_jobs_api(request):
    """
    GET /api/nearby-jobs/?pincode=600001&radius=5&collar=blue&q=driver
    Returns JSON list of jobs within radius_km, sorted by distance.
    """
    pincode   = request.GET.get('pincode', '').strip()
    radius_km = float(request.GET.get('radius', 5))
    collar    = request.GET.get('collar', '')
    q         = request.GET.get('q', '')

    if not pincode:
        return JsonResponse({'error': 'pincode is required'}, status=400)

    from .utils import geocode_pincode, jobs_within_radius

    lat, lng = geocode_pincode(pincode)
    if lat is None:
        logger.warning('nearby_jobs_api: geocode failed for pincode=%s', pincode)
        return JsonResponse({'error': 'Location not found for the given pincode.'}, status=404)

    base_qs = Job.objects.filter(status='active')
    if collar:
        base_qs = base_qs.filter(collar_type=collar)
    if q:
        base_qs = base_qs.filter(Q(title__icontains=q) | Q(category__icontains=q))

    pairs = jobs_within_radius(lat, lng, radius_km, queryset=base_qs)

    results = []
    for job, dist in pairs:
        results.append({
            'id':          job.pk,
            'title':       job.title,
            'category':    job.category,
            'industry':    job.industry,
            'collar':      job.collar_type,
            'location':    job.location,
            'pincode':     job.pincode,
            'distance_km': dist,
            'salary':      job.salary_display(),
            'job_type':    job.job_type,
            'is_urgent':   job.is_urgent,
            'url':         f'/jobs/{job.pk}/',
        })

    return JsonResponse({
        'center':    {'lat': lat, 'lng': lng, 'pincode': pincode},
        'radius_km': radius_km,
        'count':     len(results),
        'jobs':      results,
    })


# ── AI JOB DESCRIPTION ───────────────────────────────────────────────────────
@login_required
def ai_generate_description(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    from django.conf import settings as django_settings
    api_key = getattr(django_settings, 'ANTHROPIC_API_KEY', '').strip()
    if not api_key:
        logger.error('ai_generate_description: ANTHROPIC_API_KEY is not configured')
        return JsonResponse({'error': 'AI feature is temporarily unavailable.'}, status=500)
    try:
        import anthropic
        title       = request.POST.get('title', '').strip()
        industry    = request.POST.get('industry', '').strip()
        role        = request.POST.get('category', '').strip()
        job_type    = request.POST.get('job_type', '').strip()
        experience  = request.POST.get('experience', '').strip()
        salary_min  = request.POST.get('salary_min', '').strip()
        salary_max  = request.POST.get('salary_max', '').strip()
        salary_type = request.POST.get('salary_type', 'month').strip()
        collar      = request.POST.get('collar_type', '').strip()

        salary_text = ''
        if salary_min and salary_max:
            salary_text = f'₹{salary_min}–₹{salary_max} per {salary_type}'
        elif salary_min:
            salary_text = f'₹{salary_min}+ per {salary_type}'

        prompt = f"""Write a professional job description for a job posting on an Indian job portal.

Job Details:
- Title: {title or role}
- Industry: {industry}
- Role: {role}
- Type: {job_type.replace('_', ' ').title()}
- Experience: {experience}
- Salary: {salary_text or 'Negotiable'}
- Collar type: {collar} collar

Write 3–4 short paragraphs:
1. About the role (2–3 sentences)
2. Key responsibilities (4–5 bullet points)
3. What we're looking for (3–4 bullet points)
4. One closing sentence inviting applications

Keep it clear, professional, and suitable for Indian job seekers. Do not include headings or markdown — plain text only."""

        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=600,
            messages=[{'role': 'user', 'content': prompt}]
        )
        description = message.content[0].text.strip()
        return JsonResponse({'description': description})
    except Exception as e:
        msg = str(e)
        if 'credit balance is too low' in msg or '400' in msg:
            return JsonResponse({'error': 'Insufficient API credits. Please add credits at console.anthropic.com → Plans & Billing.'}, status=402)
        logger.exception('ai_generate_description: unexpected error for user %s', request.user.pk)
        return JsonResponse({'error': 'Something went wrong. Please try again.'}, status=500)


# ── INTERVIEW ─────────────────────────────────────────────────────────────────
@login_required
def schedule_interview(request, app_id):
    app = get_object_or_404(JobApplication, pk=app_id, job__posted_by=request.user)
    if request.method == 'POST':
        import datetime as dt
        Interview.objects.update_or_create(
            application=app,
            defaults={
                'date':     dt.datetime.strptime(request.POST['date'], '%Y-%m-%d').date(),
                'time':     dt.datetime.strptime(request.POST['time'], '%H:%M').time(),
                'mode':     request.POST.get('mode', 'in_person'),
                'location': request.POST.get('location', ''),
                'link':     request.POST.get('link', ''),
                'notes':    request.POST.get('notes', ''),
                'status':   'scheduled',
            }
        )
        app.status = 'interview_scheduled'
        app.save()
        messages.success(request, 'Interview scheduled and candidate notified.')
        return redirect('employer_dashboard')
    return render(request, 'schedule_interview.html', {'app': app})


@login_required
def accept_interview(request, app_id):
    app = get_object_or_404(JobApplication, pk=app_id, applicant=request.user)
    if hasattr(app, 'interview'):
        app.interview.status = 'accepted'
        app.interview.save()
        app.status = 'interview_accepted'
        app.save()
        messages.success(request, 'Interview accepted! Check your schedule.')
    return redirect('jobseeker_dashboard')


@login_required
def reject_interview(request, app_id):
    app = get_object_or_404(JobApplication, pk=app_id, applicant=request.user)
    if hasattr(app, 'interview'):
        app.interview.status = 'rejected'
        app.interview.save()
        app.status = 'interview_rejected'
        app.save()
        messages.info(request, 'Interview declined.')
    return redirect('jobseeker_dashboard')


# ── OFFER LETTER ──────────────────────────────────────────────────────────────
@login_required
def send_offer_letter(request, app_id):
    app = get_object_or_404(JobApplication, pk=app_id, job__posted_by=request.user)
    if request.method == 'POST':
        import datetime as dt
        OfferLetter.objects.update_or_create(
            application=app,
            defaults={
                'position':     request.POST.get('position', app.job.title),
                'salary':       request.POST.get('salary', ''),
                'joining_date': dt.datetime.strptime(request.POST['joining_date'], '%Y-%m-%d').date(),
                'content':      request.POST.get('content', ''),
            }
        )
        app.status = 'offer_sent'
        app.save()
        messages.success(request, 'Offer letter sent to candidate.')
        return redirect('employer_dashboard')
    return render(request, 'offer_letter_form.html', {'app': app})


@login_required
def download_offer_letter(request, app_id):
    app    = get_object_or_404(JobApplication, pk=app_id, applicant=request.user)
    offer  = get_object_or_404(OfferLetter, application=app)
    return render(request, 'offer_letter_print.html', {'offer': offer, 'app': app})


# ==============================================================
# ADMIN HIERARCHY MODULE  (Super → State → District)
# ==============================================================
from functools import wraps

def super_admin_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or request.user.admin_role != 'super_admin':
            messages.error(request, 'Super Admin access required.')
            return redirect('login')
        return view_func(request, *args, **kwargs)
    return wrapper

def state_admin_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or request.user.admin_role not in ('super_admin', 'state_admin'):
            messages.error(request, 'State Admin access required.')
            return redirect('login')
        return view_func(request, *args, **kwargs)
    return wrapper

def district_admin_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or request.user.admin_role not in ('super_admin', 'state_admin', 'district_admin'):
            messages.error(request, 'District Admin access required.')
            return redirect('login')
        return view_func(request, *args, **kwargs)
    return wrapper


# ─── SUPER ADMIN ──────────────────────────────────────────────────────────────

@login_required
def post_simple_ad(request):
    from .models import AdPost, AdSettings
    if not request.user.is_authenticated:
        return redirect(f'/login/?next=/ads/post/')
    adv = getattr(request.user, 'advertiser', None)
    if not adv:
        messages.error(request, 'Please register as an advertiser first.')
        return redirect('advertiser_register')
    if adv.status != 'approved':
        messages.error(request, 'Your advertiser account is pending admin approval. You can create ads once approved.')
        return redirect('advertiser_dashboard')
    if request.method == 'POST':
        import base64, io
        from django.core.files.base import ContentFile
        company_name = request.POST.get('company_name', '').strip()
        pincode      = request.POST.get('pincode', '').strip()
        description  = request.POST.get('description', '').strip()[:160]
        website      = request.POST.get('website', '').strip()
        image_data   = request.POST.get('image_data', '').strip()
        image        = request.FILES.get('image')
        # Prefer cropped base64 data over raw file
        if image_data and image_data.startswith('data:image'):
            fmt, b64 = image_data.split(';base64,', 1)
            ext = fmt.split('/')[-1].replace('jpeg', 'jpg')
            image = ContentFile(base64.b64decode(b64), name=f'ad_{request.user.pk}.{ext}')
        if not company_name or not description or not image:
            messages.error(request, 'Company name, description and image are required.')
            return redirect('post_simple_ad')
        AdPost.objects.create(
            user=request.user,
            company_name=company_name,
            pincode=pincode,
            description=description,
            website=website,
            image=image,
        )
        messages.success(request, 'Ad submitted! Admin will review and publish it shortly.')
        return redirect('my_simple_ads')
    ads      = AdPost.objects.filter(user=request.user).prefetch_related('renewals')
    settings = AdSettings.get()
    return render(request, 'post_simple_ad.html', {'ads': ads, 'settings': settings})


@login_required
def my_simple_ads(request):
    from .models import AdPost, AdSettings
    ads      = AdPost.objects.filter(user=request.user).prefetch_related('renewals')
    settings = AdSettings.get()
    return render(request, 'my_simple_ads.html', {'ads': ads, 'settings': settings})


@login_required
def renew_ad(request, pk):
    from .models import AdPost, AdRenewal, AdSettings
    ad = get_object_or_404(AdPost, pk=pk, user=request.user)
    settings = AdSettings.get()
    if request.method == 'POST':
        transaction_id = request.POST.get('transaction_id', '').strip()
        screenshot     = request.FILES.get('screenshot')
        if not transaction_id or not screenshot:
            messages.error(request, 'Transaction ID and screenshot are required.')
            return redirect('renew_ad', pk=pk)
        AdRenewal.objects.create(
            ad=ad,
            transaction_id=transaction_id,
            screenshot=screenshot,
            amount=settings.renewal_price,
        )
        messages.success(request, 'Renewal request submitted! Admin will verify and extend your ad.')
        return redirect('my_simple_ads')
    return render(request, 'renew_ad.html', {'ad': ad, 'settings': settings})


@super_admin_required
def admin_ad_posts(request):
    from .models import AdPost, AdRenewal, AdSettings
    from django.utils import timezone
    import datetime
    settings = AdSettings.get()
    if request.method == 'POST':
        action = request.POST.get('action')
        # ── renewal actions ──────────────────────────────────────────────
        if action in ('approve_renewal', 'reject_renewal'):
            renewal = get_object_or_404(AdRenewal, pk=request.POST.get('renewal_id'))
            if action == 'approve_renewal':
                renewal.status      = 'approved'
                renewal.approved_at = timezone.now()
                renewal.save()
                ad = renewal.ad
                today = timezone.now().date()
                base = max(ad.expires_at, today) if ad.expires_at else today
                ad.expires_at = base + datetime.timedelta(days=settings.renewal_days)
                ad.status     = 'approved'
                ad.save()
                messages.success(request, f'Renewal approved. Ad live until {ad.expires_at}.')
            else:
                renewal.status      = 'rejected'
                renewal.reject_note = request.POST.get('reject_note', '').strip()
                renewal.save()
                messages.success(request, 'Renewal rejected.')
            return redirect('admin_ad_posts')
        # ── ad actions ───────────────────────────────────────────────────
        ad = get_object_or_404(AdPost, pk=request.POST.get('ad_id'))
        if action == 'approve':
            ad.status      = 'approved'
            ad.approved_at = timezone.now()
            ad.expires_at  = timezone.now().date() + datetime.timedelta(days=settings.renewal_days)
            ad.reject_note = ''
            ad.save()
            UserNotification.objects.create(
                user=ad.user,
                title='Your ad is LIVE!',
                message=f'Your ad "{ad.company_name}" has been approved and is now live until {ad.expires_at.strftime("%d %b %Y")}. Check My Ads to view it.',
                notif_type='success',
            )
            messages.success(request, f'"{ad.company_name}" approved — live for {settings.renewal_days} days.')
        elif action == 'reject':
            ad.status      = 'rejected'
            ad.reject_note = request.POST.get('reject_note', '').strip()
            ad.save()
            UserNotification.objects.create(
                user=ad.user,
                title='Ad not approved',
                message=f'Your ad "{ad.company_name}" was not approved.{" Reason: " + ad.reject_note if ad.reject_note else " Please review and resubmit."}',
                notif_type='warning',
            )
            messages.success(request, f'"{ad.company_name}" rejected.')
        elif action == 'delete':
            ad.delete()
            messages.success(request, 'Ad deleted.')
        return redirect('admin_ad_posts')

    ads = AdPost.objects.select_related('user').prefetch_related('renewals').order_by('-created_at')
    renewals       = AdRenewal.objects.select_related('ad__user').filter(status='pending').order_by('-created_at')
    pending_count  = ads.filter(status='pending').count()
    approved_count = ads.filter(status='approved').count()
    renewal_count  = renewals.count()
    status_filter  = request.GET.get('status', '')
    tab            = request.GET.get('tab', 'ads')
    if status_filter:
        ads = ads.filter(status=status_filter)
    return render(request, 'admin_ad_posts.html', {
        'ads': ads,
        'renewals': renewals,
        'pending_count': pending_count,
        'approved_count': approved_count,
        'renewal_count': renewal_count,
        'status_filter': status_filter,
        'tab': tab,
        'settings': settings,
    })


@super_admin_required
def admin_ad_settings(request):
    from .models import AdSettings
    settings = AdSettings.get()
    if request.method == 'POST':
        settings.upi_id        = request.POST.get('upi_id', '').strip()
        settings.renewal_price = int(request.POST.get('renewal_price') or 199)
        settings.renewal_days  = int(request.POST.get('renewal_days') or 30)
        settings.save()
        messages.success(request, 'Ad settings saved.')
        return redirect('admin_ad_posts')
    return redirect('admin_ad_posts')


def admin_feedback(request):
    if request.method == 'POST':
        complaint_id = request.POST.get('complaint_id')
        complaint = get_object_or_404(Complaint, pk=complaint_id)
        complaint.status     = request.POST.get('status', complaint.status)
        complaint.resolution = request.POST.get('resolution', '').strip()
        complaint.save()
        messages.success(request, 'Feedback updated.')
        return redirect('admin_feedback')
    status_filter = request.GET.get('status', '')
    qs = Complaint.objects.select_related('submitted_by').order_by('-created_at')
    if status_filter:
        qs = qs.filter(status=status_filter)
    return render(request, 'admin_feedback.html', {
        'complaints': qs,
        'status_filter': status_filter,
        'open_count':       Complaint.objects.filter(status='open').count(),
        'in_review_count':  Complaint.objects.filter(status='in_review').count(),
        'resolved_count':   Complaint.objects.filter(status='resolved').count(),
    })


@super_admin_required
def admin_flicks(request):
    from .models import Flick, FlickAdPayment, FlickAdSettings
    from django.utils import timezone
    flicks   = Flick.objects.select_related('user').order_by('-created_at')
    payments = FlickAdPayment.objects.select_related('flick', 'user').filter(status='pending').order_by('-created_at')
    settings = FlickAdSettings.get()

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'save_settings':
            settings.upi_id        = request.POST.get('upi_id', settings.upi_id).strip()
            settings.price         = request.POST.get('price', settings.price)
            settings.duration_days = request.POST.get('duration_days', settings.duration_days)
            settings.save()
            messages.success(request, 'Settings saved.')
            return redirect('admin_flicks')

        if action in ('approve_payment', 'reject_payment'):
            pay = get_object_or_404(FlickAdPayment, pk=request.POST.get('payment_id'))
            if action == 'approve_payment':
                pay.status      = 'approved'
                pay.approved_at = timezone.now()
                pay.save()
                flick = pay.flick
                flick.is_promoted    = True
                flick.advertise_plan = 'basic'
                flick.promoted_until = (timezone.now().date() +
                                        timezone.timedelta(days=pay.duration_days))
                flick.save()
                messages.success(request, f'Payment approved. Flick promoted until {flick.promoted_until}.')
            else:
                pay.status = 'rejected'
                pay.save()
                messages.success(request, 'Payment rejected.')
            return redirect('admin_flicks')

        flick_id = request.POST.get('flick_id')
        flick = get_object_or_404(Flick, pk=flick_id)
        if action == 'delete':
            flick.delete()
            messages.success(request, 'Flick deleted.')
        elif action == 'set_plan':
            flick.advertise_plan = request.POST.get('plan', '')
            flick.is_promoted    = (flick.advertise_plan != '')
            flick.save()
            messages.success(request, f'Plan updated to "{flick.advertise_plan or "No Plan"}".')
        return redirect('admin_flicks')

    return render(request, 'admin_flicks.html', {
        'flicks': flicks,
        'payments': payments,
        'settings': settings,
    })


@login_required
def report_flick(request, pk):
    from .models import Flick, FlickReport
    if request.method != 'POST':
        return JsonResponse({'success': False})
    flick  = get_object_or_404(Flick, pk=pk)
    reason = request.POST.get('reason', '').strip()
    note   = request.POST.get('note', '').strip()
    if not reason:
        return JsonResponse({'success': False, 'error': 'Reason required'})
    if flick.user == request.user:
        return JsonResponse({'success': False, 'error': 'Cannot report your own flick'})
    obj, created = FlickReport.objects.get_or_create(
        flick=flick, user=request.user,
        defaults={'reason': reason, 'note': note}
    )
    if not created:
        return JsonResponse({'success': False, 'already': True, 'error': 'Already reported'})
    return JsonResponse({'success': True})


@super_admin_required
def admin_flick_reports(request):
    from .models import FlickReport, Flick
    if request.method == 'POST':
        action    = request.POST.get('action')
        report_id = request.POST.get('report_id')
        report    = get_object_or_404(FlickReport, pk=report_id)
        if action == 'delete_flick':
            report.flick.delete()
            messages.success(request, 'Flick deleted.')
        elif action == 'dismiss':
            report.status = 'dismissed'
            report.save()
            messages.success(request, 'Report dismissed.')
        elif action == 'reviewed':
            report.status = 'reviewed'
            report.save()
            messages.success(request, 'Marked as reviewed.')
        return redirect('admin_flick_reports')

    status_filter = request.GET.get('status', 'pending')
    qs = FlickReport.objects.select_related('flick', 'flick__user', 'user').order_by('-created_at')
    if status_filter:
        qs = qs.filter(status=status_filter)
    return render(request, 'admin_flick_reports.html', {
        'reports':       qs,
        'status_filter': status_filter,
        'pending_count': FlickReport.objects.filter(status='pending').count(),
    })


@login_required
def flick_advertise(request, pk):
    from .models import Flick, FlickAdPayment, FlickAdSettings
    flick    = get_object_or_404(Flick, pk=pk, user=request.user)
    settings = FlickAdSettings.get()
    pending  = FlickAdPayment.objects.filter(flick=flick, status='pending').exists()

    if request.method == 'POST':
        txn_id = request.POST.get('transaction_id', '').strip()
        if not txn_id:
            messages.error(request, 'Please enter the UPI Transaction ID.')
            return redirect('flick_advertise', pk=pk)
        if pending:
            messages.error(request, 'You already have a pending payment for this flick.')
            return redirect('flicks_feed')
        FlickAdPayment.objects.create(
            flick=flick,
            user=request.user,
            transaction_id=txn_id,
            amount=settings.price,
            duration_days=settings.duration_days,
        )
        messages.success(request, 'Payment submitted! Admin will verify and activate your promotion shortly.')
        return redirect('flicks_feed')

    return render(request, 'flick_advertise.html', {
        'flick': flick,
        'settings': settings,
        'pending': pending,
    })


@super_admin_required
def super_admin_dashboard(request):
    from vouchers.models import Business as VoucherBusiness, VoucherSlotPurchase, GiftVoucher, VoucherPurchase
    from django.db.models import Sum as DjSum
    total_users     = User.objects.count()
    total_jobs      = Job.objects.count()
    active_jobs     = Job.objects.filter(status='active').count()
    total_apps      = JobApplication.objects.count()
    total_states    = State.objects.count()
    total_districts = District.objects.count()
    total_adverts   = Advertiser.objects.count()
    pending_adverts   = Advertiser.objects.filter(status='pending').count()
    from .models import AdPost
    pending_ad_posts  = AdPost.objects.filter(status='pending').count()
    open_complaints = Complaint.objects.filter(status='open').count()
    employer_count  = User.objects.filter(user_type__in=User.EMPLOYER_TYPES, admin_role='').count()
    jobseeker_count = User.objects.filter(user_type__in=['employee','individual','freelancer'], admin_role='').count()
    recent_users       = User.objects.order_by('-date_joined')[:8]
    state_list         = State.objects.annotate(d_count=Count('districts')).order_by('name')
    recent_jobs        = Job.objects.select_related('posted_by').order_by('-created_at')[:6]
    industries         = Industry.objects.filter(is_active=True)
    notifications      = SystemNotification.objects.filter(is_active=True)[:5]
    pending_jobs_count = Job.objects.filter(status='active', is_approved=False).count()
    paid_verify_count  = Job.objects.filter(job_plan='paid_pending').count()

    # Voucher stats
    voucher_biz_pending  = VoucherBusiness.objects.filter(status='pending').count()
    voucher_slot_pending = VoucherSlotPurchase.objects.filter(status='pending').count()
    voucher_total_biz    = VoucherBusiness.objects.filter(status='approved').count()
    voucher_live         = GiftVoucher.objects.filter(status='published').count()
    voucher_revenue      = VoucherPurchase.objects.filter(
        status__in=['paid', 'sent', 'redeemed']
    ).aggregate(t=DjSum('amount_paid'))['t'] or 0
    pending_voucher_businesses = VoucherBusiness.objects.filter(
        status='pending'
    ).select_related('category', 'owner').order_by('created_at')[:5]
    pending_voucher_slots = VoucherSlotPurchase.objects.filter(
        status='pending'
    ).select_related('business').order_by('purchased_at')[:5]

    # Community pending
    from portal.models import Community
    community_pending_count = Community.objects.filter(is_verified=False, is_active=True).count()
    community_pending = Community.objects.filter(
        is_verified=False, is_active=True
    ).select_related('created_by', 'category').order_by('created_at')[:10]

    # Offers pending
    pending_offers_count = LocalOffer.objects.filter(is_active=False).count()

    return render(request, 'super_admin_dashboard.html', {
        'total_users': total_users, 'total_jobs': total_jobs, 'active_jobs': active_jobs,
        'total_apps': total_apps, 'total_states': total_states, 'total_districts': total_districts,
        'total_adverts': total_adverts, 'pending_adverts': pending_adverts,
        'pending_ad_posts': pending_ad_posts,
        'open_complaints': open_complaints, 'recent_users': recent_users,
        'state_list': state_list, 'recent_jobs': recent_jobs,
        'industries': industries, 'notifications': notifications,
        'employer_count': employer_count, 'jobseeker_count': jobseeker_count,
        'pending_jobs_count': pending_jobs_count, 'paid_verify_count': paid_verify_count,
        'voucher_biz_pending': voucher_biz_pending,
        'voucher_slot_pending': voucher_slot_pending,
        'voucher_total_biz': voucher_total_biz,
        'voucher_live': voucher_live,
        'voucher_revenue': voucher_revenue,
        'pending_voucher_businesses': pending_voucher_businesses,
        'pending_voucher_slots': pending_voucher_slots,
        'community_pending_count': community_pending_count,
        'community_pending': community_pending,
        'pending_offers_count': pending_offers_count,
    })


@super_admin_required
def manage_states(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        code = request.POST.get('code', '').strip().upper()
        if name and code:
            State.objects.get_or_create(name=name, defaults={'code': code, 'created_by': request.user})
            messages.success(request, f'State "{name}" created.')
        return redirect('manage_states')
    states = State.objects.annotate(d_count=Count('districts')).order_by('name')
    return render(request, 'manage_states.html', {'states': states})


@super_admin_required
def toggle_state(request, pk):
    state = get_object_or_404(State, pk=pk)
    state.is_active = not state.is_active
    state.save()
    messages.success(request, f'State "{state.name}" {"activated" if state.is_active else "deactivated"}.')
    return redirect('manage_states')


@super_admin_required
def manage_districts(request, state_id):
    state = get_object_or_404(State, pk=state_id)
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if name:
            District.objects.get_or_create(state=state, name=name)
            messages.success(request, f'District "{name}" created.')
        return redirect('manage_districts', state_id=state_id)
    districts = state.districts.all()
    return render(request, 'manage_districts.html', {'state': state, 'districts': districts})


@super_admin_required
def create_state_admin(request):
    states = State.objects.filter(is_active=True)
    if request.method == 'POST':
        fullname = request.POST.get('fullname', '').strip()
        phone    = request.POST.get('phone', '').strip()
        password = request.POST.get('password', '').strip()
        state_id = request.POST.get('state_id')
        state    = get_object_or_404(State, pk=state_id)
        if not phone or not phone.isdigit() or len(phone) != 10:
            messages.error(request, 'Enter a valid 10-digit mobile number.')
        elif User.objects.filter(username=phone).exists():
            messages.error(request, 'A login already exists with this mobile number.')
        else:
            parts = fullname.split(' ', 1)
            user  = User.objects.create_user(
                username=phone, password=password,
                first_name=parts[0], last_name=parts[1] if len(parts) > 1 else '',
                phone=phone, admin_role='state_admin'
            )
            AdminProfile.objects.create(user=user, role='state_admin', state=state, appointed_by=request.user)
            messages.success(request, f'State Admin "{fullname}" created for {state.name}. Login with mobile {phone}.')
            return redirect('manage_state_admins')
    return render(request, 'create_state_admin.html', {'states': states})


@super_admin_required
def manage_state_admins(request):
    admins = AdminProfile.objects.filter(role='state_admin').select_related('user', 'state').order_by('state__name')
    return render(request, 'manage_state_admins.html', {'admins': admins})


@super_admin_required
def toggle_admin(request, pk):
    profile = get_object_or_404(AdminProfile, pk=pk)
    profile.is_active = not profile.is_active
    profile.user.is_active = profile.is_active
    profile.user.save()
    profile.save()
    messages.success(request, f'Admin {"activated" if profile.is_active else "suspended"}.')
    return redirect(request.META.get('HTTP_REFERER', 'super_admin_dashboard'))


@super_admin_required
def manage_industries(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add':
            name   = request.POST.get('name', '').strip()
            collar = request.POST.get('collar', 'both')
            icon   = request.POST.get('icon', 'fas fa-industry').strip()
            if name:
                Industry.objects.get_or_create(name=name, defaults={'collar': collar, 'icon': icon})
                messages.success(request, f'Industry "{name}" added.')
        elif action == 'toggle':
            pk = request.POST.get('pk')
            ind = get_object_or_404(Industry, pk=pk)
            ind.is_active = not ind.is_active
            ind.save()
        return redirect('manage_industries')
    industries = Industry.objects.annotate(role_count=Count('roles'))
    return render(request, 'manage_industries.html', {'industries': industries})


@super_admin_required
def manage_job_roles(request, industry_id=None):
    industries = Industry.objects.filter(is_active=True)
    selected   = get_object_or_404(Industry, pk=industry_id) if industry_id else industries.first()
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add' and selected:
            name = request.POST.get('name', '').strip()
            if name:
                JobRole.objects.get_or_create(industry=selected, name=name)
                messages.success(request, f'Job role "{name}" added.')
        elif action == 'toggle':
            role = get_object_or_404(JobRole, pk=request.POST.get('pk'))
            role.is_active = not role.is_active
            role.save()
        return redirect('manage_job_roles', industry_id=selected.pk if selected else 1)
    roles = selected.roles.all() if selected else []
    return render(request, 'manage_job_roles.html', {'industries': industries, 'selected': selected, 'roles': roles})


@super_admin_required
def manage_ad_packages(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add':
            AdPackage.objects.create(
                name          = request.POST.get('name', '').strip(),
                ad_type       = request.POST.get('ad_type', 'homepage_banner'),
                duration_days = request.POST.get('duration_days', 30),
                price         = request.POST.get('price', 0),
                description   = request.POST.get('description', '').strip(),
                size_specs    = request.POST.get('size_specs', '').strip(),
                is_active     = True,
            )
            messages.success(request, 'Package created.')
        elif action == 'toggle':
            pkg = get_object_or_404(AdPackage, pk=request.POST.get('pk'))
            pkg.is_active = not pkg.is_active
            pkg.save()
        elif action == 'delete':
            pkg = get_object_or_404(AdPackage, pk=request.POST.get('pk'))
            pkg.delete()
            messages.success(request, 'Package deleted.')
        elif action == 'edit':
            pkg = get_object_or_404(AdPackage, pk=request.POST.get('pk'))
            pkg.name          = request.POST.get('name', pkg.name).strip()
            pkg.ad_type       = request.POST.get('ad_type', pkg.ad_type)
            pkg.duration_days = request.POST.get('duration_days', pkg.duration_days)
            pkg.price         = request.POST.get('price', pkg.price)
            pkg.description   = request.POST.get('description', pkg.description).strip()
            pkg.size_specs    = request.POST.get('size_specs', pkg.size_specs).strip()
            pkg.save()
            messages.success(request, 'Package updated.')
        return redirect('manage_ad_packages')
    packages = AdPackage.objects.order_by('ad_type', 'price')
    return render(request, 'manage_ad_packages.html', {'packages': packages})


@super_admin_required
def manage_payment_plans(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add':
            PaymentPlan.objects.create(
                name          = request.POST.get('name', '').strip(),
                plan_type     = request.POST.get('plan_type', 'employer_basic'),
                price         = request.POST.get('price', 0),
                duration_days = request.POST.get('duration_days', 30),
                job_posts     = request.POST.get('job_posts', 5),
                features      = request.POST.get('features', '').strip(),
                is_featured   = 'is_featured' in request.POST,
            )
            messages.success(request, 'Payment plan created.')
        elif action == 'toggle':
            plan = get_object_or_404(PaymentPlan, pk=request.POST.get('pk'))
            plan.is_active = not plan.is_active
            plan.save()
        return redirect('manage_payment_plans')
    plans = PaymentPlan.objects.all()
    return render(request, 'manage_payment_plans.html', {'plans': plans})


@super_admin_required
def manage_discounts(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add':
            Discount.objects.create(
                code          = request.POST.get('code', '').strip().upper(),
                description   = request.POST.get('description', '').strip(),
                discount_type = request.POST.get('discount_type', 'percent'),
                value         = request.POST.get('value', 0),
                min_amount    = request.POST.get('min_amount', 0),
                max_uses      = request.POST.get('max_uses', 0),
                valid_from    = request.POST.get('valid_from') or None,
                valid_until   = request.POST.get('valid_until') or None,
            )
            messages.success(request, 'Discount code created.')
        elif action == 'toggle':
            d = get_object_or_404(Discount, pk=request.POST.get('pk'))
            d.is_active = not d.is_active
            d.save()
        return redirect('manage_discounts')
    discounts = Discount.objects.all().order_by('-created_at')
    return render(request, 'manage_discounts.html', {'discounts': discounts})


@super_admin_required
def manage_pincodes(request, district_id=None):
    districts = District.objects.select_related('state').order_by('state__name', 'name')
    selected  = get_object_or_404(District, pk=district_id) if district_id else None
    if request.method == 'POST' and selected:
        code      = request.POST.get('code', '').strip()
        area_name = request.POST.get('area_name', '').strip()
        if code:
            PinCode.objects.get_or_create(district=selected, code=code, defaults={'area_name': area_name})
            messages.success(request, f'PIN {code} added.')
        return redirect('manage_pincodes', district_id=selected.pk)
    pincodes = selected.pincodes.all() if selected else []
    return render(request, 'manage_pincodes.html', {'districts': districts, 'selected': selected, 'pincodes': pincodes})


@super_admin_required
def manage_notifications(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add':
            SystemNotification.objects.create(
                title       = request.POST.get('title', '').strip(),
                message     = request.POST.get('message', '').strip(),
                notif_type  = request.POST.get('notif_type', 'info'),
                target_role = request.POST.get('target_role', '').strip(),
                created_by  = request.user,
            )
            messages.success(request, 'Notification created.')
        elif action == 'toggle':
            n = get_object_or_404(SystemNotification, pk=request.POST.get('pk'))
            n.is_active = not n.is_active
            n.save()
        return redirect('manage_notifications')
    notifs = SystemNotification.objects.all()
    return render(request, 'manage_notifications.html', {'notifs': notifs})


@login_required
def mark_all_notifications_read(request):
    UserNotification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    next_url = request.GET.get('next') or request.META.get('HTTP_REFERER') or '/'
    return redirect(next_url)


@login_required
@login_required
def update_interview_type(request):
    if request.method != 'POST':
        return JsonResponse({'success': False})
    import json
    data = json.loads(request.body)
    job_id   = data.get('job_id')
    itype    = data.get('interview_type', '').strip()
    if itype not in ('walkin', 'online'):
        return JsonResponse({'success': False, 'error': 'Invalid type'})
    try:
        job = Job.objects.get(id=job_id, posted_by=request.user)
        job.interview_type = itype
        job.save(update_fields=['interview_type'])
        return JsonResponse({'success': True, 'interview_type': itype})
    except Job.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Job not found'})


def api_pincode_lookup(request, pin):
    import re
    if not re.fullmatch(r'\d{6}', pin):
        return JsonResponse({'success': False, 'error': 'Invalid PIN code'})

    from .models import PinCode, District, State
    import requests as _req

    # Try local DB first
    try:
        pc = PinCode.objects.select_related('district__state').get(code=pin)
        return JsonResponse({
            'success': True,
            'area': pc.area_name or pc.district.name,
            'district': pc.district.name,
            'state': pc.district.state.name,
        })
    except PinCode.DoesNotExist:
        pass

    # Fall back to India Post API
    try:
        import urllib.request as _ur, json as _json
        with _ur.urlopen(f'https://api.postalpincode.in/pincode/{pin}', timeout=8) as _resp:
            data = _json.loads(_resp.read())
        if data and data[0].get('Status') == 'Success' and data[0].get('PostOffice'):
            po       = data[0]['PostOffice'][0]
            area     = po.get('Name', '')
            district = po.get('District', '')
            state    = po.get('State', '')

            # Cache in local DB if district exists
            try:
                dist_obj = District.objects.get(name__iexact=district)
                PinCode.objects.get_or_create(
                    code=pin,
                    defaults={'district': dist_obj, 'area_name': area}
                )
            except District.DoesNotExist:
                pass

            return JsonResponse({'success': True, 'area': area, 'district': district, 'state': state})
        return JsonResponse({'success': False, 'error': 'PIN code not found'})
    except Exception:
        return JsonResponse({'success': False, 'error': 'Lookup unavailable'})


def terms(request):
    return render(request, 'terms.html')


def privacy(request):
    return render(request, 'privacy.html')


def about_page(request):
    return render(request, 'about.html')


def favicon(request):
    return HttpResponse(status=204)


# ── FLICKS ────────────────────────────────────────────────────────────────────

def flicks_feed(request):
    from .models import Flick, FlickLike
    from django.utils import timezone
    today = timezone.now().date()
    cat = request.GET.get('cat', '')
    flicks = Flick.objects.select_related('user').prefetch_related('likes', 'comments').extra(
        select={'is_paid_active': "CASE WHEN promoted_until >= %s THEN 1 ELSE 0 END"},
        select_params=[today],
        order_by=['-is_paid_active', '-created_at'],
    )
    if cat:
        flicks = flicks.filter(category=cat)
    liked_ids = set()
    if request.user.is_authenticated:
        liked_ids = set(FlickLike.objects.filter(user=request.user).values_list('flick_id', flat=True))
    return render(request, 'flicks.html', {'flicks': flicks, 'liked_ids': liked_ids, 'today': today, 'active_cat': cat})


@login_required
def post_flick(request):
    from .models import Flick
    if request.method == 'POST':
        title    = request.POST.get('title', '').strip()
        caption  = request.POST.get('caption', '').strip()
        category = request.POST.get('category', 'general')
        video    = request.FILES.get('video')
        image    = request.FILES.get('image')
        if not caption and not video and not image:
            messages.error(request, 'Add a caption, image, or video.')
            return redirect('post_flick')
        Flick.objects.create(user=request.user, title=title, caption=caption,
                             category=category, video=video, image=image)
        messages.success(request, 'Flick posted!')
        return redirect('flicks_feed')
    return render(request, 'post_flick.html')


@login_required
def like_flick(request, pk):
    from .models import Flick, FlickLike
    if request.method != 'POST':
        return JsonResponse({'success': False})
    flick = get_object_or_404(Flick, pk=pk)
    like, created = FlickLike.objects.get_or_create(flick=flick, user=request.user)
    if not created:
        like.delete()
        liked = False
    else:
        liked = True
    return JsonResponse({'success': True, 'liked': liked, 'count': flick.like_count()})


@login_required
def comment_flick(request, pk):
    from .models import Flick, FlickComment
    if request.method != 'POST':
        return JsonResponse({'success': False})
    import json
    data = json.loads(request.body)
    text = data.get('text', '').strip()
    if not text:
        return JsonResponse({'success': False, 'error': 'Empty comment'})
    flick = get_object_or_404(Flick, pk=pk)
    c = FlickComment.objects.create(flick=flick, user=request.user, text=text)
    return JsonResponse({
        'success': True,
        'name': request.user.get_full_name() or request.user.username,
        'text': c.text,
        'time': c.created_at.strftime('%d %b %Y'),
    })


@login_required
def delete_flick(request, pk):
    from .models import Flick
    flick = get_object_or_404(Flick, pk=pk, user=request.user)
    flick.delete()
    messages.success(request, 'Flick deleted.')
    return redirect('flicks_feed')


@login_required
def referral_dashboard(request):
    user = request.user
    if not user.referral_code:
        from .utils import generate_referral_code
        user.referral_code = generate_referral_code()
        user.save(update_fields=['referral_code'])

    wallet, _ = PointsWallet.objects.get_or_create(user=user)
    transactions = wallet.transactions.all()[:20]
    referrals = Referral.objects.filter(referrer=user).select_related('referred').order_by('-created_at')

    referral_link = request.build_absolute_uri(f'/register/?ref={user.referral_code}')

    return render(request, 'referral.html', {
        'wallet': wallet,
        'transactions': transactions,
        'referrals': referrals,
        'referral_link': referral_link,
    })


@super_admin_required
def national_analytics(request):
    jobs_by_collar = {
        'white': Job.objects.filter(collar_type='white').count(),
        'blue':  Job.objects.filter(collar_type='blue').count(),
    }
    apps_by_status = {s: JobApplication.objects.filter(status=s).count()
                      for s, _ in JobApplication._meta.get_field('status').choices}
    advertisers_by_status = {s: Advertiser.objects.filter(status=s).count()
                              for s, _ in Advertiser.ADVERTISER_STATUS}
    top_states = State.objects.annotate(d_count=Count('districts')).order_by('-d_count')[:10]
    return render(request, 'national_analytics.html', {
        'jobs_by_collar': jobs_by_collar,
        'apps_by_status': apps_by_status,
        'advertisers_by_status': advertisers_by_status,
        'top_states': top_states,
        'total_revenue': AdPayment.objects.filter(status='paid').count(),
    })


# ─── STATE ADMIN ──────────────────────────────────────────────────────────────

@state_admin_required
def state_admin_dashboard(request):
    profile  = getattr(request.user, 'admin_profile', None)
    state    = profile.state if profile and profile.state else None
    districts= state.districts.all() if state else District.objects.none()
    pending_employers = User.objects.filter(
        user_type__in=User.EMPLOYER_TYPES, is_active=True
    ).count()
    state_jobs = Job.objects.filter(pincode__in=[]).count()
    open_complaints = Complaint.objects.filter(status='open').count()
    district_admins = AdminProfile.objects.filter(role='district_admin', state=state) if state else []
    return render(request, 'state_admin_dashboard.html', {
        'state': state, 'districts': districts,
        'pending_employers': pending_employers,
        'open_complaints': open_complaints,
        'district_admins': district_admins,
        'district_count': districts.count(),
    })


@state_admin_required
def create_district_admin(request):
    profile  = getattr(request.user, 'admin_profile', None)
    state    = profile.state if profile else None
    districts= state.districts.all() if state else District.objects.all()
    if request.method == 'POST':
        fullname    = request.POST.get('fullname', '').strip()
        phone       = request.POST.get('phone', '').strip()
        password    = request.POST.get('password', '').strip()
        district_id = request.POST.get('district_id')
        district    = get_object_or_404(District, pk=district_id)
        if not phone or not phone.isdigit() or len(phone) != 10:
            messages.error(request, 'Enter a valid 10-digit mobile number.')
        elif User.objects.filter(username=phone).exists():
            messages.error(request, 'A login already exists with this mobile number.')
        else:
            parts = fullname.split(' ', 1)
            user  = User.objects.create_user(
                username=phone, password=password,
                first_name=parts[0], last_name=parts[1] if len(parts) > 1 else '',
                phone=phone, admin_role='district_admin'
            )
            AdminProfile.objects.create(
                user=user, role='district_admin',
                state=district.state, district=district,
                appointed_by=request.user
            )
            messages.success(request, f'District Admin created for {district.name}. Login with mobile {phone}.')
            return redirect('state_admin_dashboard')
    return render(request, 'create_district_admin.html', {'districts': districts, 'state': state})


@state_admin_required
def verify_employers(request):
    employers = User.objects.filter(
        user_type__in=User.EMPLOYER_TYPES
    ).order_by('-date_joined')
    return render(request, 'verify_employers.html', {'employers': employers})


@state_admin_required
def suspend_user(request, user_id):
    target = get_object_or_404(User, pk=user_id)
    target.is_active = not target.is_active
    target.save()
    action = 'activated' if target.is_active else 'suspended'
    messages.success(request, f'User "{target.username}" {action}.')
    return redirect(request.META.get('HTTP_REFERER', 'state_admin_dashboard'))


@state_admin_required
def state_reports(request):
    profile  = getattr(request.user, 'admin_profile', None)
    state    = profile.state if profile else None
    districts = state.districts.all() if state else District.objects.none()
    district_stats = []
    for d in districts:
        d.job_count = Job.objects.filter(pincode__in=d.pincodes.values_list('code', flat=True)).count()
        d.app_count = JobApplication.objects.filter(
            job__pincode__in=d.pincodes.values_list('code', flat=True)
        ).count()
        district_stats.append(d)
    total_jobs = Job.objects.count()
    total_applications = JobApplication.objects.count()
    total_employers = User.objects.filter(user_type__in=User.EMPLOYER_TYPES).count()
    open_complaints = Complaint.objects.filter(status='open').count()
    white_jobs = Job.objects.filter(collar_type='white').count()
    blue_jobs  = Job.objects.filter(collar_type='blue').count()
    recent_employers = User.objects.filter(user_type__in=User.EMPLOYER_TYPES).order_by('-date_joined')[:10]
    app_statuses = ['applied', 'shortlisted', 'interviewed', 'offered', 'rejected']
    return render(request, 'state_reports.html', {
        'state': state,
        'district_stats': district_stats,
        'total_jobs': total_jobs,
        'total_applications': total_applications,
        'total_employers': total_employers,
        'open_complaints': open_complaints,
        'white_jobs': white_jobs,
        'blue_jobs': blue_jobs,
        'recent_employers': recent_employers,
        'apps_applied':     JobApplication.objects.filter(status='applied').count(),
        'apps_shortlisted': JobApplication.objects.filter(status='shortlisted').count(),
        'apps_interviewed': JobApplication.objects.filter(status='interviewed').count(),
        'apps_offered':     JobApplication.objects.filter(status='offered').count(),
        'apps_rejected':    JobApplication.objects.filter(status='rejected').count(),
    })


# ─── DISTRICT ADMIN ───────────────────────────────────────────────────────────

@district_admin_required
def district_admin_dashboard(request):
    profile  = getattr(request.user, 'admin_profile', None)
    district = profile.district if profile else None
    pending_employers  = Advertiser.objects.filter(status='pending').count()
    pending_ads        = Advertisement.objects.filter(status='pending_review').count()
    open_complaints    = Complaint.objects.filter(status='open', district=district).count()
    recent_jobs        = Job.objects.order_by('-created_at')[:8]
    recent_complaints  = Complaint.objects.filter(district=district).order_by('-created_at')[:5]
    return render(request, 'district_admin_dashboard.html', {
        'district': district, 'pending_employers': pending_employers,
        'pending_ads': pending_ads, 'open_complaints': open_complaints,
        'recent_jobs': recent_jobs, 'recent_complaints': recent_complaints,
    })


@district_admin_required
def approve_employers_district(request):
    employers = User.objects.filter(user_type__in=User.EMPLOYER_TYPES).order_by('-date_joined')
    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        action  = request.POST.get('action')
        target  = get_object_or_404(User, pk=user_id)
        if action == 'approve':
            target.is_active = True
            target.save()
            messages.success(request, f'{target.username} approved.')
        elif action == 'block':
            target.is_active = False
            target.save()
            messages.info(request, f'{target.username} blocked.')
        return redirect('approve_employers_district')
    return render(request, 'approve_employers_district.html', {'employers': employers})


@district_admin_required
def moderate_jobs(request):
    tab = request.GET.get('tab', 'all')

    if request.method == 'POST':
        job_id  = request.POST.get('job_id')
        action  = request.POST.get('action')
        back_tab = request.POST.get('back_tab', 'all')
        job     = get_object_or_404(Job, pk=job_id)
        if action == 'suspend':
            job.status = 'closed'
            job.save()
            messages.success(request, f'Job "{job.title}" suspended.')
        elif action == 'activate':
            job.status = 'active'
            job.save()
            messages.success(request, f'Job "{job.title}" reactivated.')
        elif action == 'approve':
            job.is_approved = True
            job.status = 'active'
            job.save()
            UserNotification.objects.create(
                user=job.posted_by,
                title=f'Job Approved! Choose Your Plan — {job.title}',
                message='Your job is approved! 🎉 Start with 2 Weeks FREE, or go straight to 12 Weeks for ₹499. Tap to choose.',
                notif_type='success',
                link=f'/jobs/{job.pk}/select-plan/',
            )
            messages.success(request, f'Job "{job.title}" approved. Employer notified to select a plan.')
        elif action == 'reject':
            job.is_approved = False
            job.status = 'closed'
            job.save()
            messages.success(request, f'Job "{job.title}" rejected.')
        elif action == 'activate_plan':
            import datetime
            job.job_plan = 'paid'
            job.plan_expires_at = datetime.date.today() + datetime.timedelta(weeks=12)
            job.save()
            from .utils import notify_seekers_for_job
            notify_seekers_for_job(job)
            UserNotification.objects.create(
                user=job.posted_by,
                title='Your Plan is Activated!',
                message=f'Your payment has been verified. "{job.title}" is now live for 12 weeks. Job seekers can now find and apply!',
                notif_type='success',
                link=f'/jobs/{job.pk}/',
            )
            messages.success(request, f'Plan activated for "{job.title}". Employer notified.')
        elif action == 'set_free_plan':
            import datetime
            job.job_plan = 'free'
            job.plan_expires_at = datetime.date.today() + datetime.timedelta(weeks=2)
            job.save()
            from .utils import notify_seekers_for_job
            notify_seekers_for_job(job)
            UserNotification.objects.create(
                user=job.posted_by,
                title='Your Job is Now Live!',
                message=f'"{job.title}" has been approved and is now live for 2 weeks. Job seekers can find and apply!',
                notif_type='success',
                link=f'/jobs/{job.pk}/',
            )
            messages.success(request, f'Free plan set for "{job.title}". Job is now live.')
        return redirect(f'/district-admin/jobs/?tab={back_tab}')

    base_qs = Job.objects.select_related('posted_by').order_by('is_approved', '-created_at')

    if tab == 'pending':
        jobs = base_qs.filter(status='active', is_approved=False)
    elif tab == 'payment':
        jobs = base_qs.filter(job_plan__in=['paid_pending', 'paid']).exclude(payment_screenshot='').exclude(payment_screenshot__isnull=True)
    else:
        jobs = base_qs

    pending_count = base_qs.filter(status='active', is_approved=False).count()
    payment_count = base_qs.filter(job_plan='paid_pending').count()

    return render(request, 'moderate_jobs.html', {
        'jobs':          jobs,
        'pending_count': pending_count,
        'payment_count': payment_count,
        'tab':           tab,
    })


@district_admin_required
def handle_complaints(request):
    profile  = getattr(request.user, 'admin_profile', None)
    district = profile.district if profile else None
    complaints = Complaint.objects.filter(district=district).order_by('-created_at')
    return render(request, 'handle_complaints.html', {'complaints': complaints, 'district': district})


@district_admin_required
def resolve_complaint(request, complaint_id):
    complaint = get_object_or_404(Complaint, pk=complaint_id)
    if request.method == 'POST':
        complaint.resolution  = request.POST.get('resolution', '').strip()
        complaint.status      = request.POST.get('status', 'resolved')
        complaint.assigned_to = request.user
        complaint.resolved_at = timezone.now()
        complaint.save()
        messages.success(request, 'Complaint updated.')
        return redirect('handle_complaints')
    return render(request, 'resolve_complaint.html', {'complaint': complaint})


@district_admin_required
def district_reports(request):
    profile  = getattr(request.user, 'admin_profile', None)
    district = profile.district if profile else None
    pin_codes = district.pincodes.values_list('code', flat=True) if district else []
    total_jobs         = Job.objects.filter(pincode__in=pin_codes).count() if pin_codes else Job.objects.count()
    total_applications = JobApplication.objects.count()
    total_employers    = User.objects.filter(user_type__in=User.EMPLOYER_TYPES).count()
    total_complaints   = Complaint.objects.filter(district=district).count()
    white_jobs = Job.objects.filter(collar_type='white').count()
    blue_jobs  = Job.objects.filter(collar_type='blue').count()
    from datetime import date, timedelta
    month_start = date.today().replace(day=1)
    recent_jobs = Job.objects.filter(created_at__date__gte=month_start).select_related('posted_by').order_by('-created_at')[:15]
    complaints  = Complaint.objects.filter(district=district).order_by('-created_at')[:10]
    return render(request, 'district_reports.html', {
        'district': district,
        'total_jobs': total_jobs,
        'total_applications': total_applications,
        'total_employers': total_employers,
        'total_complaints': total_complaints,
        'white_jobs': white_jobs,
        'blue_jobs': blue_jobs,
        'recent_jobs': recent_jobs,
        'complaints': complaints,
        'comp_open':        Complaint.objects.filter(district=district, status='open').count(),
        'comp_in_progress': Complaint.objects.filter(district=district, status='in_progress').count(),
        'comp_resolved':    Complaint.objects.filter(district=district, status='resolved').count(),
        'comp_closed':      Complaint.objects.filter(district=district, status='closed').count(),
    })


# ─── PUBLIC: Submit Complaint ──────────────────────────────────────────────────
@login_required
def submit_complaint(request):
    if request.method == 'POST':
        Complaint.objects.create(
            submitted_by   = request.user,
            complaint_type = request.POST.get('complaint_type', 'other'),
            subject        = request.POST.get('subject', '').strip(),
            description    = request.POST.get('description', '').strip(),
        )
        messages.success(request, 'Complaint submitted. Our team will review it shortly.')
        return redirect('dashboard')
    return render(request, 'submit_complaint.html', {})


# ── SAVE CANDIDATE ────────────────────────────────────────────────────────────
@login_required
def save_candidate(request, user_id):
    candidate = get_object_or_404(User, pk=user_id)
    obj, created = SavedCandidate.objects.get_or_create(employer=request.user, candidate=candidate)
    if not created:
        obj.delete()
        return JsonResponse({'saved': False})
    return JsonResponse({'saved': True})


# ── PROFILE REDIRECT ──────────────────────────────────────────────────────────
@login_required
def profile_redirect(request):
    return redirect('profile_edit')


@login_required
def my_accounts(request):
    user = request.user

    # Family account
    family_setup = None
    try:
        family_setup = user.family_setup
    except Exception:
        pass

    # Communities created (portal)
    from portal.models import Community
    communities = Community.objects.filter(created_by=user, is_active=True).order_by('-created_at')

    # Campus company
    campus_company = getattr(user, 'campus_company', None)

    # Campus placement officer
    placement_officer = getattr(user, 'placement_officer', None)

    seeker = getattr(user, 'seeker', None)
    company = getattr(user, 'company', None)

    return render(request, 'my_accounts.html', {
        'user': user,
        'family_setup': family_setup,
        'communities': communities,
        'campus_company': campus_company,
        'placement_officer': placement_officer,
        'seeker': seeker,
        'company': company,
    })


@login_required
def profile_edit(request):
    import re
    user = request.user
    company = getattr(user, 'company', None)

    # Auto-create seeker profile for individual/employee/freelancer
    if user.user_type in ('individual', 'employee', 'freelancer'):
        seeker, _ = JobSeekerProfile.objects.get_or_create(user=user)
    else:
        seeker = getattr(user, 'seeker', None)

    if request.method == 'POST':
        p = request.POST
        f = request.FILES
        # User fields
        user.first_name = p.get('first_name', '').strip()
        user.last_name  = p.get('last_name', '').strip()
        user.email      = p.get('email', '').strip()
        user.whatsapp   = p.get('whatsapp', '').strip()
        user.city       = p.get('city', '').strip()
        user.pincode    = p.get('pincode', '').strip()
        user.address    = p.get('address', '').strip()
        user.save()

        # Seeker profile fields
        if seeker:
            if 'photo' in f:
                seeker.photo = f['photo']
            dob_str = p.get('dob', '').strip()
            if dob_str:
                from datetime import datetime
                try:
                    seeker.dob = datetime.strptime(dob_str, '%Y-%m-%d').date()
                except ValueError:
                    pass
            seeker.gender           = p.get('gender', '').strip()
            seeker.experience       = p.get('experience', '').strip()
            seeker.education        = p.get('qualification', '').strip()
            seeker.education_details = p.get('education_details', '').strip()
            seeker.primary_skill    = p.get('primary_skill', '').strip()
            seeker.skills           = p.get('technical_skills', '').strip()
            seeker.languages        = p.get('languages', '').strip()
            seeker.preferred_roles  = p.get('current_title', '').strip()
            seeker.preferred_location = p.get('preferred_location', '').strip()
            seeker.open_to_relocate = p.get('willing_to_relocate') == 'yes'
            job_cat = p.get('job_category', '').strip()
            if job_cat in ('blue', 'white', 'any'):
                seeker.job_category = job_cat
            seeker.blue_collar_type = p.get('blue_collar_type', '').strip()
            salary_min = p.get('salary_min', '').strip()
            if salary_min:
                try:
                    seeker.salary_min = int(salary_min.replace(',', '').replace('₹', '').replace(' ', ''))
                except ValueError:
                    pass
            seeker.portfolio_url    = p.get('portfolio_url', '').strip()
            if 'resume' in f:
                seeker.resume = f['resume']
            seeker.save()

        next_url = request.POST.get('next') or request.GET.get('next') or ''
        missing = _application_missing_fields(seeker)
        if re.fullmatch(r'/jobs/[0-9]+/apply/', next_url) and missing:
            return render(request, 'profile_edit.html', {
                'seeker': seeker, 'company': company, 'application_missing': missing,
            }, status=400)
        messages.success(request, 'Profile updated successfully.')
        if next_url.startswith('/'):
            return redirect(next_url)
        return redirect('profile_edit')

    return render(request, 'profile_edit.html', {
        'seeker': seeker,
        'company': company,
        'application_missing': _application_missing_fields(seeker) if re.fullmatch(r'/jobs/[0-9]+/apply/', request.GET.get('next', '')) else [],
    })


# ── CANDIDATE SEARCH ──────────────────────────────────────────────────────────
def candidates(request):
    if request.user.is_authenticated and not request.user.is_employer():
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Only employers can view candidates.")
    profiles = JobSeekerProfile.objects.select_related('user').filter(
        profile_completed=True,
        user__user_type__in=['employee', 'individual', 'freelancer']
    )

    skill    = request.GET.get('skill', '').strip()
    city     = request.GET.get('city', '').strip()
    pincode  = request.GET.get('pincode', '').strip()
    collar   = request.GET.get('collar', '').strip()
    exp      = request.GET.get('exp', '').strip()
    avail    = request.GET.get('avail', '').strip()

    if skill:
        profiles = profiles.filter(
            Q(primary_skill__icontains=skill) | Q(skills__icontains=skill) | Q(preferred_roles__icontains=skill)
        )
    if city:
        profiles = profiles.filter(user__city__icontains=city)
    if pincode:
        profiles = profiles.filter(user__pincode=pincode)
    if collar:
        profiles = profiles.filter(job_category=collar)
    if exp == 'fresher':
        profiles = profiles.filter(experience__in=['', 'fresher', '0'])
    if avail == 'immediate':
        profiles = profiles.filter(availability='immediate')

    return render(request, 'candidates.html', {
        'profiles': profiles[:50],
        'skill': skill, 'city': city, 'pincode': pincode,
        'collar': collar, 'total': profiles.count(),
    })


def candidate_profile(request, user_id):
    if request.user.is_authenticated and not request.user.is_employer():
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Only employers can view candidate profiles.")
    seeker_user = get_object_or_404(User, pk=user_id, user_type__in=['employee', 'individual', 'freelancer'])
    try:
        profile = seeker_user.seeker
    except JobSeekerProfile.DoesNotExist:
        from django.http import Http404
        raise Http404
    return render(request, 'candidate_profile.html', {'p': profile, 'seeker_user': seeker_user})


# ── SPIN TO WIN ──────────────────────────────────────────────────────────────
import random, string

@login_required
def spin_api(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)

    today = timezone.now().date()
    if UserSpin.objects.filter(user=request.user, date=today).exists():
        return JsonResponse({'already_spun': True})

    gift = SpinGift.objects.filter(is_active=True).order_by('?').first()
    if not gift:
        return JsonResponse({'error': 'No active gift'}, status=404)

    won = random.random() * 100 < gift.win_pct
    if won:
        code = gift.code
    else:
        code = ''.join(random.choices(string.digits, k=6))

    UserSpin.objects.create(user=request.user, date=today, won=won, gift=gift, code_shown=code)
    return JsonResponse({
        'won': won,
        'code': code,
        'gift_name': gift.name,
        'gift_image': gift.image.url if gift.image else '',
        'gift_address': gift.address,
    })


# ── SUPER ADMIN: SPIN GIFTS ───────────────────────────────────────────────────
@super_admin_required
def manage_spin_gifts(request):
    if request.method == 'POST':
        name    = request.POST.get('name', '').strip()
        address = request.POST.get('address', '').strip()
        win_pct = float(request.POST.get('win_pct', 10))
        code    = request.POST.get('code', '').strip()[:6]
        image   = request.FILES.get('image')
        if name and code and image:
            SpinGift.objects.create(name=name, address=address, win_pct=win_pct, code=code, image=image)
        return redirect('manage_spin_gifts')

    gifts = SpinGift.objects.order_by('-created_at')
    return render(request, 'super_admin_spin_gifts.html', {'gifts': gifts})


@super_admin_required
def delete_spin_gift(request, pk):
    SpinGift.objects.filter(pk=pk).delete()
    return redirect('manage_spin_gifts')


@super_admin_required
def toggle_spin_gift(request, pk):
    gift = get_object_or_404(SpinGift, pk=pk)
    gift.is_active = not gift.is_active
    gift.save()
    return redirect('manage_spin_gifts')


# ── SUPER ADMIN: OFFERS ────────────────────────────────────────────────────────
@super_admin_required
def manage_offers(request):
    if request.method == 'POST':
        action = request.POST.get('action', 'add')
        if action == 'approve':
            pk = request.POST.get('pk')
            offer = get_object_or_404(LocalOffer, pk=pk)
            offer.is_active = not offer.is_active
            offer.save()
            return redirect('manage_offers')
        if action == 'delete':
            pk = request.POST.get('pk')
            LocalOffer.objects.filter(pk=pk).delete()
            return redirect('manage_offers')
        # action == 'add'
        obj = LocalOffer(
            business_name = request.POST.get('business_name', '').strip(),
            title         = request.POST.get('title', '').strip(),
            discount_text = request.POST.get('discount_text', '').strip(),
            category      = request.POST.get('category', 'other'),
            description   = request.POST.get('description', '').strip(),
            is_flash      = 'is_flash' in request.POST,
            is_active     = True,
        )
        phone = request.POST.get('contact_phone', '').strip()
        if phone:
            obj.contact_phone = phone
            obj.link_url = f"https://wa.me/91{phone}"
        if request.POST.get('valid_until'):
            obj.valid_until = request.POST.get('valid_until')
        if request.FILES.get('image'):
            obj.image = request.FILES['image']
        obj.save()
        return redirect('manage_offers')

    pending = LocalOffer.objects.filter(is_active=False).order_by('-created_at')
    active  = LocalOffer.objects.filter(is_active=True).order_by('-created_at')
    return render(request, 'super_admin_offers.html', {
        'pending': pending,
        'active':  active,
        'categories': LocalOffer.CATEGORY_CHOICES,
    })


@super_admin_required
def offer_approve(request, pk):
    offer = get_object_or_404(LocalOffer, pk=pk)
    offer.is_active = not offer.is_active
    offer.save()
    return redirect('manage_offers')


@super_admin_required
def offer_delete(request, pk):
    LocalOffer.objects.filter(pk=pk).delete()
    return redirect('manage_offers')
