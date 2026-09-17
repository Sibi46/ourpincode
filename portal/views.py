from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
User = get_user_model()
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Q, Count, Sum, F, ExpressionWrapper, IntegerField, Avg
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings

from .models import (
    Category, Community, CommunityLeader, CommunityMember,
    Cause, CauseSupport, Event, EventParticipant,
    EventComment, EventAnnouncement, EventPhoto, EventRating,
    VolunteerRequest, Activity, ActivityPhoto,
    Post, PostLike, PostComment, ShortVideo, PortalNotification,
    Flick, FlickLike, FlickComment,
    PointConfig, Participation, Contribution, MemberPoints,
    Badge, MemberBadge, Recognition, PointAuditLog,
    award_points, get_point_value,
)


def _notify(user, notif_type, message, link=''):
    PortalNotification.objects.create(user=user, notif_type=notif_type, message=message, link=link)


def _is_member(community, user):
    if not user.is_authenticated:
        return False
    return community.memberships.filter(user=user, status='approved').exists()


# ──────────────────────────────────────────────
# PUBLIC PAGES
# ──────────────────────────────────────────────

def portal_home(request):
    communities = Community.objects.filter(is_active=True, is_verified=True).order_by('-created_at')
    pincode = request.GET.get('pincode', '').strip()
    category = request.GET.get('category', '').strip()
    q = request.GET.get('q', '').strip()

    if pincode:
        communities = communities.filter(pincode__startswith=pincode)
    if category:
        communities = communities.filter(category__slug=category)
    if q:
        communities = communities.filter(Q(name__icontains=q) | Q(page_id__icontains=q) | Q(purpose__icontains=q))

    categories = Category.objects.all()
    upcoming_events = Event.objects.filter(is_active=True, date__gte=timezone.now().date()).order_by('date')[:6]

    return render(request, 'portal/home.html', {
        'communities': communities,
        'categories': categories,
        'upcoming_events': upcoming_events,
        'pincode': pincode, 'category': category, 'q': q,
    })


def community_list(request):
    communities = Community.objects.filter(is_active=True, is_verified=True)
    q       = request.GET.get('q', '').strip()
    pincode = request.GET.get('pincode', '').strip()
    cat     = request.GET.get('category', '').strip()
    if q:
        communities = communities.filter(Q(name__icontains=q) | Q(page_id__icontains=q))
    if pincode:
        communities = communities.filter(pincode__startswith=pincode)
    if cat:
        communities = communities.filter(category__slug=cat)
    communities = communities.order_by('-created_at')
    return render(request, 'portal/community_list.html', {
        'communities': communities,
        'categories': Category.objects.all(),
        'q': q, 'pincode': pincode, 'selected_cat': cat,
    })


def community_page(request, page_id):
    community = get_object_or_404(Community, page_id=page_id, is_active=True)
    is_member  = _is_member(community, request.user)
    is_admin   = community.is_admin(request.user)
    membership = None
    if request.user.is_authenticated:
        membership = community.memberships.filter(user=request.user).first()

    posts      = community.posts.filter(is_active=True).order_by('-created_at')[:20]
    causes     = community.causes.filter(is_active=True).order_by('-created_at')[:5]
    events     = community.events.filter(is_active=True, date__gte=timezone.now().date()).order_by('date')[:5]
    pending_events = community.events.filter(is_active=False).order_by('date') if is_admin else []
    activities = community.activities.filter(is_active=True).order_by('-date')[:5]
    videos     = community.videos.filter(is_active=True).order_by('-created_at')[:6]
    flicks     = community.flicks.filter(is_active=True).order_by('-created_at')[:6]
    leaders    = community.leaders.filter(status='accepted').order_by('role')
    members    = community.memberships.filter(status='approved').select_related('user').prefetch_related('user__seeker')[:12]

    # Gallery timeline — image posts grouped by year/month
    _MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
    gallery_groups = []
    image_posts = community.posts.filter(is_active=True).exclude(image='').order_by('-event_date', '-created_at')
    _cur_ym = None
    _cur_grp = None
    _last_year = None
    for p in image_posts:
        d = p.event_date or p.created_at.date()
        ym = (d.year, d.month)
        if ym != _cur_ym:
            if _cur_grp:
                gallery_groups.append(_cur_grp)
            _cur_grp = {
                'year': d.year,
                'show_year': d.year != _last_year,
                'month_name': _MONTHS[d.month - 1],
                'count': 0,
                'items': [],
            }
            _last_year = d.year
            _cur_ym = ym
        _cur_grp['items'].append(p)
        _cur_grp['count'] += 1
    if _cur_grp:
        gallery_groups.append(_cur_grp)

    return render(request, 'portal/community_page.html', {
        'community': community, 'is_member': is_member,
        'is_admin': is_admin, 'membership': membership,
        'posts': posts, 'causes': causes, 'events': events, 'pending_events': pending_events,
        'activities': activities, 'videos': videos, 'flicks': flicks,
        'leaders': leaders, 'members': members,
        'gallery_groups': gallery_groups,
    })


def causes_list(request):
    causes = Cause.objects.filter(is_active=True).select_related('community').order_by('-created_at')
    q = request.GET.get('q', '')
    if q:
        causes = causes.filter(Q(name__icontains=q) | Q(description__icontains=q))
    return render(request, 'portal/causes_list.html', {'causes': causes, 'q': q})


def cause_detail(request, pk):
    cause    = get_object_or_404(Cause, pk=pk, is_active=True)
    supported = request.user.is_authenticated and CauseSupport.objects.filter(cause=cause, user=request.user).exists()
    events   = cause.events.filter(is_active=True).order_by('date')
    return render(request, 'portal/cause_detail.html', {
        'cause': cause, 'supported': supported, 'events': events,
    })


def events_list(request):
    from django.utils.timezone import now
    events  = Event.objects.filter(is_active=True).select_related('community').order_by('date')
    q       = request.GET.get('q', '')
    date    = request.GET.get('date', '')
    mode    = request.GET.get('mode', '')
    free    = request.GET.get('free', '')
    pincode = request.GET.get('pincode', '')
    tab     = request.GET.get('tab', 'upcoming')
    today   = now().date()
    if tab == 'upcoming':
        events = events.filter(date__gte=today)
    elif tab == 'past':
        events = events.filter(date__lt=today)
    if q:
        events = events.filter(Q(name__icontains=q) | Q(location__icontains=q) | Q(tags__icontains=q))
    if date:
        events = events.filter(date=date)
    if mode == 'online':
        events = events.filter(is_online=True)
    elif mode == 'offline':
        events = events.filter(is_online=False)
    if free == '1':
        events = events.filter(is_paid=False)
    if pincode:
        events = events.filter(pincode=pincode)
    return render(request, 'portal/events_list.html', {
        'events': events, 'q': q, 'tab': tab,
        'mode': mode, 'free': free, 'pincode': pincode,
    })


def event_detail(request, pk):
    event = get_object_or_404(Event, pk=pk, is_active=True)
    is_admin = event.community and event.community.is_admin(request.user)
    is_super_admin = request.user.is_authenticated and (request.user.is_staff or request.user.is_superuser)
    registration = None
    user_rating = None
    if request.user.is_authenticated:
        registration = event.participants.filter(user=request.user).first()
        user_rating  = event.ratings.filter(user=request.user).first()
        # Build ordered list of user's RSVP answers matching event questions
        if registration and event.rsvp_questions:
            registration.answers_list = [
                (q, registration.rsvp_answers.get(str(i), ''))
                for i, q in enumerate(event.rsvp_questions)
            ]
    attendees   = event.participants.filter(status='approved').select_related('user')[:20]
    waitlist    = event.participants.filter(status='waitlist').select_related('user')
    comments    = event.comments.select_related('user').order_by('created_at')
    announcements = event.announcements.select_related('created_by').order_by('-created_at')
    photos      = event.photos.select_related('uploaded_by')[:12]
    ratings     = event.ratings.select_related('user').order_by('-created_at')
    avg_rating  = event.avg_rating()
    similar     = Event.objects.filter(
        community=event.community, is_active=True
    ).exclude(pk=event.pk).order_by('date')[:3]
    community_president = None
    if event.community:
        pres = event.community.president()
        if pres:
            community_president = pres.user
    join_required = request.session.pop('join_required_community', None)
    already_rated = False
    if request.user.is_authenticated:
        from portal.models import AttendeeRating
        already_rated = AttendeeRating.objects.filter(event=event, rater=request.user).exists()
    return render(request, 'portal/event_detail.html', {
        'event': event, 'is_admin': is_admin, 'is_super_admin': is_super_admin,
        'registration': registration, 'user_rating': user_rating,
        'attendees': attendees, 'waitlist': waitlist,
        'comments': comments, 'announcements': announcements,
        'photos': photos, 'ratings': ratings, 'avg_rating': avg_rating,
        'similar': similar,
        'going_count': event.participants.filter(status='approved').count(),
        'waitlist_count': waitlist.count(),
        'community_president': community_president,
        'join_required': join_required,
        'already_rated': already_rated,
    })


def activities_list(request):
    activities = Activity.objects.filter(is_active=True).select_related('community').order_by('-date')
    q = request.GET.get('q', '')
    if q:
        activities = activities.filter(Q(name__icontains=q) | Q(location__icontains=q))
    return render(request, 'portal/activities_list.html', {'activities': activities, 'q': q})


def activity_detail(request, pk):
    activity = get_object_or_404(Activity, pk=pk)
    return render(request, 'portal/activity_detail.html', {'activity': activity})


def videos_list(request):
    videos = ShortVideo.objects.filter(is_active=True).select_related('community', 'uploader').order_by('-created_at')
    cat = request.GET.get('category', '')
    if cat:
        videos = videos.filter(category=cat)
    return render(request, 'portal/videos_list.html', {
        'videos': videos, 'cat': cat,
        'categories': ShortVideo.VIDEO_CATS,
    })


def portal_search(request):
    q = request.GET.get('q', '').strip()
    results = {}
    if q:
        results['communities'] = Community.objects.filter(
            Q(name__icontains=q) | Q(page_id__icontains=q) | Q(purpose__icontains=q),
            is_active=True, is_verified=True)[:8]
        results['causes']  = Cause.objects.filter(Q(name__icontains=q), is_active=True)[:6]
        results['events']  = Event.objects.filter(Q(name__icontains=q) | Q(location__icontains=q), is_active=True)[:6]
        results['activities'] = Activity.objects.filter(Q(name__icontains=q), is_active=True)[:6]
        results['videos']  = ShortVideo.objects.filter(Q(title__icontains=q), is_active=True)[:6]
    return render(request, 'portal/search.html', {'q': q, 'results': results})


# ──────────────────────────────────────────────
# COMMUNITY CREATE / EDIT
# ──────────────────────────────────────────────

@login_required
def create_community(request):
    categories = Category.objects.all()
    if request.method == 'POST':
        p = request.POST

        # ── resolve creator account ──────────────────────────────
        if request.user.is_authenticated:
            creator = request.user
            full_name = p.get('full_name', '').strip()
            new_email = p.get('creator_email', '').strip().lower()
            new_pass  = p.get('creator_password', '').strip()
            if full_name:
                parts = full_name.split(' ', 1)
                creator.first_name = parts[0]
                creator.last_name  = parts[1] if len(parts) > 1 else ''
            if new_email and new_email != creator.email:
                if not User.objects.filter(email=new_email).exclude(pk=creator.pk).exists():
                    creator.email = new_email
            if new_pass:
                creator.set_password(new_pass)
            creator.save()
            if new_pass:
                from django.contrib.auth import login as auth_login
                auth_login(request, creator, backend='django.contrib.auth.backends.ModelBackend')
            if 'creator_photo' in request.FILES:
                from jobs.models import JobSeekerProfile
                profile, _ = JobSeekerProfile.objects.get_or_create(user=creator)
                profile.photo = request.FILES['creator_photo']
                profile.save(update_fields=['photo'])
        else:
            full_name = p.get('full_name', '').strip()
            email     = p.get('creator_email', '').strip().lower()
            password  = p.get('creator_password', '').strip()
            phone_c   = p.get('creator_phone', '').strip()

            # If phone matches an existing account, require login first
            if phone_c and User.objects.filter(phone=phone_c).exists():
                messages.error(request, 'An account with this phone number already exists. Please log in first, then create your community.')
                return redirect(f'/login/?next=/portal/community/create/')

            if not email or not password:
                messages.error(request, 'Email and password are required to create your account.')
                return render(request, 'portal/community_create.html', {'categories': categories})
            if User.objects.filter(email=email).exists():
                messages.error(request, 'An account with this email already exists. Please log in first.')
                return render(request, 'portal/community_create.html', {'categories': categories})

            base_uname = email.split('@')[0]
            username = base_uname
            n = 1
            while User.objects.filter(username=username).exists():
                username = f'{base_uname}{n}'; n += 1

            creator = User(username=username, email=email, user_type='individual')
            creator.set_password(password)
            if full_name:
                parts = full_name.split(' ', 1)
                creator.first_name = parts[0]
                creator.last_name  = parts[1] if len(parts) > 1 else ''
            if phone_c:
                creator.phone = phone_c
            creator.save()
            from django.contrib.auth import login as auth_login
            auth_login(request, creator, backend='django.contrib.auth.backends.ModelBackend')

        # save profile photo if provided
        if 'creator_photo' in request.FILES:
            from jobs.models import JobSeekerProfile
            profile, _ = JobSeekerProfile.objects.get_or_create(user=creator)
            profile.photo = request.FILES['creator_photo']
            profile.save(update_fields=['photo'])

        # ── create community ─────────────────────────────────────
        community = Community(
            name=p.get('name','').strip(),
            purpose=p.get('purpose','').strip(),
            description=p.get('description','').strip(),
            location=p.get('location','').strip(),
            pincode=p.get('pincode','').strip(),
            email=p.get('comm_email','').strip(),
            phone=p.get('comm_phone','').strip(),
            join_mode=p.get('join_mode','open'),
            created_by=creator,
        )
        cat_id = p.get('category')
        if cat_id:
            community.category_id = cat_id
        if 'logo' in request.FILES:
            community.logo = request.FILES['logo']
        if 'cover' in request.FILES:
            community.cover = request.FILES['cover']
        if getattr(request.user, 'admin_role', '') == 'super_admin':
            community.is_verified = True
        community.save()

        CommunityMember.objects.create(community=community, user=creator, status='approved', approved_at=timezone.now())
        CommunityLeader.objects.create(community=community, user=creator, role='president', status='accepted')

        messages.success(request, f'Community "{community.name}" created! Page ID: {community.page_id}')
        return redirect('portal_community', page_id=community.page_id)

    return render(request, 'portal/community_create.html', {'categories': categories})


def _notify_leader(leader, email, phone='', temp_password=''):
    try:
        accept_url = f"https://www.mypincod.com/portal/leader/accept/{leader.token}/"
        login_url  = f"https://www.mypincod.com/login/"
        community  = leader.community
        role_label = leader.get_role_display()
        msg = (
            f"Dear {leader.user.get_full_name() or leader.user.username},\n\n"
            f"You have been nominated as {role_label} of {community.name}.\n\n"
            f"Community   : {community.name} ({community.page_id})\n"
            f"Nominated by: {leader.nominated_by.get_full_name() or leader.nominated_by.username}\n"
        )
        if phone:
            msg += f"Phone       : {phone}\n"
        if temp_password:
            msg += (
                f"\nYour login credentials:\n"
                f"  Website  : https://www.mypincod.com\n"
                f"  Email    : {email}\n"
                f"  Password : {temp_password}\n"
                f"  (Please change your password after first login)\n"
            )
        msg += f"\nClick below to accept your nomination:\n{accept_url}\n\nThank you,\nOUR PINCODE Team"
        send_mail(
            subject=f"Nomination: {role_label} — {community.name}",
            message=msg,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=True,
        )
    except Exception:
        pass


@login_required
def nominations_step(request, page_id):
    community = get_object_or_404(Community, page_id=page_id, created_by=request.user)
    errors = []

    if request.method == 'POST':
        action = request.POST.get('action', 'nominate')
        if action == 'skip':
            messages.info(request, 'You can add leaders later from the community dashboard.')
            return redirect('portal_community', page_id=community.page_id)

        email = request.POST.get('email', '').strip()
        role  = request.POST.get('role', 'president')

        if not email:
            errors.append('Please enter an email address.')
        else:
            try:
                nominee = User.objects.get(email=email)
            except User.DoesNotExist:
                nominee = None

            leader = CommunityLeader(
                community=community, role=role,
                nominated_by=request.user,
                user=nominee if nominee else request.user,
            )
            leader.save()
            leader.generate_token()
            _notify_leader(leader, email if not nominee else nominee.email)
            messages.success(request, f'Nomination sent to {email}.')
            return redirect('portal_nominations_step', page_id=community.page_id)

    leaders = community.leaders.select_related('user')
    roles   = CommunityLeader.ROLES
    return render(request, 'portal/nominations_step.html', {
        'community': community, 'leaders': leaders, 'roles': roles, 'errors': errors,
    })


def leader_accept(request, token):
    leader = get_object_or_404(CommunityLeader, token=token)
    if leader.status != 'pending':
        messages.info(request, f'This nomination has already been {leader.status}.')
        return redirect('portal_community', page_id=leader.community.page_id)

    action = request.GET.get('action', '')
    if action == 'accept':
        leader.status = 'accepted'
        leader.accepted_at = timezone.now()
        leader.save()
        # Also ensure they are a member
        CommunityMember.objects.get_or_create(
            community=leader.community, user=leader.user,
            defaults={'status': 'approved', 'approved_at': timezone.now()}
        )
        messages.success(request, f'You have accepted the role of {leader.get_role_display()} in {leader.community.name}!')
    elif action == 'decline':
        leader.status = 'declined'
        leader.save()
        messages.info(request, 'You have declined the nomination.')
    return render(request, 'portal/leader_accept.html', {'leader': leader, 'action': action})


# ──────────────────────────────────────────────
# JOIN COMMUNITY
# ──────────────────────────────────────────────

@login_required
def join_community(request, page_id):
    community = get_object_or_404(Community, page_id=page_id, is_active=True)
    existing  = community.memberships.filter(user=request.user).first()

    if existing:
        messages.info(request, f'Your membership status: {existing.get_status_display()}')
        return redirect('portal_community', page_id=page_id)

    user = request.user
    # Check if profile is complete
    try:
        profile = user.seeker
        has_photo = bool(profile.photo)
    except Exception:
        profile = None
        has_photo = False

    profile_incomplete = (
        not user.get_full_name().strip() or
        not user.pincode or
        not has_photo
    )

    if profile_incomplete and request.method != 'POST':
        return render(request, 'portal/join_profile.html', {
            'community': community,
            'user': user,
        })

    if request.method == 'POST':
        # Save profile details
        first_name = request.POST.get('first_name', '').strip()
        last_name  = request.POST.get('last_name', '').strip()
        pincode    = request.POST.get('pincode', '').strip()
        email      = request.POST.get('email', '').strip().lower()

        if first_name:
            user.first_name = first_name
            user.last_name  = last_name
        if pincode:
            user.pincode = pincode
        if email and not user.email:
            if not User.objects.filter(email=email).exclude(pk=user.pk).exists():
                user.email = email
        user.save(update_fields=['first_name', 'last_name', 'pincode', 'email'])

        # Save profile photo
        if 'photo' in request.FILES and profile:
            profile.photo = request.FILES['photo']
            profile.save(update_fields=['photo'])
        elif 'photo' in request.FILES and not profile:
            from jobs.models import JobSeekerProfile
            try:
                profile = JobSeekerProfile.objects.create(user=user)
                profile.photo = request.FILES['photo']
                profile.save()
            except Exception:
                pass

        # Re-check after saving — block join if still missing photo or pincode
        try:
            has_photo = bool(user.seeker.photo)
        except Exception:
            has_photo = False
        errors = []
        if not has_photo:
            errors.append('Please upload a profile photo.')
        if not user.pincode:
            errors.append('Please enter your pincode.')
        if not user.get_full_name().strip():
            errors.append('Please enter your full name.')
        if errors:
            for e in errors:
                messages.error(request, e)
            return render(request, 'portal/join_profile.html', {
                'community': community,
                'user': user,
            })

    # Do the join
    if community.join_mode == 'open':
        CommunityMember.objects.create(community=community, user=request.user, status='approved', approved_at=timezone.now())
        _notify(request.user, 'join_approved', f'Welcome to {community.name}!', f'/portal/c/{page_id}/')
        messages.success(request, f'You joined {community.name}!')
    else:
        CommunityMember.objects.create(community=community, user=request.user, status='pending')
        if community.created_by:
            _notify(community.created_by, 'join_request',
                    f'{request.user.get_full_name()} wants to join {community.name}.',
                    f'/portal/c/{page_id}/members/')
        messages.success(request, 'Join request sent. Awaiting admin approval.')

    return redirect('portal_community', page_id=page_id)


# ──────────────────────────────────────────────
# COMMUNITY ADMIN DASHBOARD
# ──────────────────────────────────────────────

@login_required
def community_dashboard(request, page_id):
    community = get_object_or_404(Community, page_id=page_id)
    if not community.is_admin(request.user):
        messages.error(request, 'Access denied.')
        return redirect('portal_community', page_id=page_id)

    return render(request, 'portal/community_dashboard.html', {
        'community': community,
        'can_manage_members': community.can_manage_members(request.user),
        'members_pending': community.memberships.filter(status='pending').count(),
        'members_approved': community.memberships.filter(status='approved').count(),
        'volunteers_pending': community.volunteer_requests.filter(status='pending').count(),
        'volunteers_approved': community.volunteer_requests.filter(status='approved').count(),
        'events_count': community.events.filter(is_active=True).count(),
        'videos_count': community.videos.filter(is_active=True).count(),
        'posts_count': community.posts.filter(is_active=True).count(),
        'recent_requests': community.memberships.filter(status='pending').select_related('user')[:5],
        'recent_volunteers': community.volunteer_requests.filter(status='pending')[:5],
        'upcoming_events': community.events.filter(is_active=True, date__gte=timezone.now().date()).order_by('date')[:3],
        'pending_events': community.events.filter(is_active=False).select_related('created_by').order_by('date'),
        'pending_flicks': community.flicks.filter(is_active=False).select_related('posted_by').order_by('-created_at'),
    })


def manage_members(request, page_id):
    community = get_object_or_404(Community, page_id=page_id, is_active=True)
    can_manage = community.can_manage_members(request.user)  # president / creator only
    is_admin   = can_manage  # controls template — only president gets admin view

    # Non-presidents (including VP/other role holders): read-only member list
    if not can_manage:
        memberships = community.memberships.filter(status='approved').select_related('user').prefetch_related('user__seeker').order_by('-joined_at')
        leader_map = {l.user_id: l for l in CommunityLeader.objects.filter(community=community, status='accepted')}
        memberships = list(memberships)
        for m in memberships:
            ldr = leader_map.get(m.user_id)
            m.current_role     = ldr.get_role_label() if ldr else ''
            m.current_role_key = ldr.role if ldr else ''
        return render(request, 'portal/manage_members.html', {
            'community': community, 'memberships': memberships,
            'status_filter': 'approved', 'is_admin': False, 'taken_roles': set(),
        })

    if request.method == 'POST':
        member_id = request.POST.get('member_id')
        action    = request.POST.get('action')
        member    = get_object_or_404(CommunityMember, pk=member_id, community=community)
        if action == 'approve':
            member.status = 'approved'
            member.approved_at = timezone.now()
            member.save()
            _notify(member.user, 'join_approved', f'Your membership in {community.name} has been approved!', f'/portal/c/{page_id}/')
        elif action in ('reject', 'remove'):
            member.status = 'rejected' if action == 'reject' else 'removed'
            member.save()
            _notify(member.user, 'join_rejected', f'Your membership in {community.name} was {member.status}.', '')
        elif action == 'assign_role':
            role = request.POST.get('role', '').strip()
            valid_roles = [r[0] for r in CommunityLeader.ROLES]
            custom_role = request.POST.get('custom_role', '').strip()
            if role and role in valid_roles:
                CommunityLeader.objects.filter(community=community, user=member.user).delete()
                CommunityLeader.objects.create(
                    community=community, user=member.user, role=role, status='accepted',
                    custom_role=custom_role if role == 'member' else ''
                )
                role_label = custom_role if role == 'member' and custom_role else dict(CommunityLeader.ROLES).get(role, role)
                messages.success(request, f'{member.user.get_full_name() or member.user.username} assigned as {role_label}.')
        return redirect(f'/portal/c/{page_id}/members/?status={request.POST.get("status_filter","approved")}')

    status_filter = request.GET.get('status', 'pending')
    memberships = community.memberships.filter(status=status_filter).select_related('user').prefetch_related('user__seeker').order_by('-joined_at')

    # Roles already taken in this community (excluding 'other')
    taken_roles = set(
        CommunityLeader.objects.filter(community=community, status='accepted')
        .exclude(role='member')
        .values_list('role', flat=True)
    )
    # Annotate each membership with the member's current leader role label
    leader_map = {
        l.user_id: l
        for l in CommunityLeader.objects.filter(community=community, status='accepted')
    }
    memberships = list(memberships)
    for m in memberships:
        ldr = leader_map.get(m.user_id)
        m.current_role      = ldr.get_role_label() if ldr else ''
        m.current_role_key  = ldr.role if ldr else ''

    return render(request, 'portal/manage_members.html', {
        'community': community,
        'memberships': memberships,
        'status_filter': status_filter,
        'taken_roles': taken_roles,
        'is_admin': True,
    })


@login_required
def add_leader(request, page_id):
    community = get_object_or_404(Community, page_id=page_id)
    if not community.is_admin(request.user):
        return redirect('portal_community', page_id=page_id)

    if request.method == 'POST':
        import random, string
        p          = request.POST
        role       = p.get('role', 'member')
        email      = p.get('email', '').strip()
        phone      = p.get('phone', '').strip()
        role_label = dict(CommunityLeader.ROLES).get(role, role)
        temp_password = ''
        is_new     = False

        # ── Phone uniqueness check ─────────────────────────
        if phone and User.objects.filter(phone=phone).exclude(email=email).exists():
            messages.error(request, f'Phone {phone} is already linked to another account.')
            return redirect('portal_add_leader', page_id=page_id)

        # ── Get or create account ──────────────────────────
        try:
            nominee = User.objects.get(email=email)
            if phone and not nominee.phone:
                nominee.phone = phone
                nominee.save(update_fields=['phone'])
        except User.DoesNotExist:
            is_new = True
            temp_password = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
            uname = email.split('@')[0] + str(random.randint(10, 99))
            while User.objects.filter(username=uname).exists():
                uname = email.split('@')[0] + str(random.randint(100, 999))
            nominee = User.objects.create_user(
                username=uname, email=email,
                password=temp_password, phone=phone,
            )

        # ── Remove old pending nomination, create accepted one ──
        CommunityLeader.objects.filter(community=community, user=nominee).delete()
        leader = CommunityLeader.objects.create(
            community=community, user=nominee, role=role,
            custom_role=p.get('custom_role', ''),
            nominated_by=request.user,
            status='accepted',
        )
        leader.generate_token()

        # ── Auto-add as approved community member ──────────
        mem, created = CommunityMember.objects.get_or_create(
            community=community, user=nominee,
            defaults={'status': 'approved', 'approved_at': timezone.now()}
        )
        if not created and mem.status != 'approved':
            mem.status = 'approved'
            mem.approved_at = timezone.now()
            mem.save()

        # ── Send email with credentials ────────────────────
        try:
            msg = (
                f"Dear Friend,\n\n"
                f"You have been appointed as {role_label} of {community.name}.\n\n"
                f"{'─'*40}\n"
                f"Community : {community.name}\n"
                f"Your Role : {role_label}\n"
                f"Appointed by: {request.user.get_full_name() or request.user.username}"
                + (f"\nPhone     : {phone}" if phone else "") +
                f"\n{'─'*40}\n\n"
                f"Login to OUR PINCODE:\n"
                f"  Website  : https://www.mypincod.com\n"
                f"  Email    : {email}\n"
            )
            if is_new:
                msg += (
                    f"  Password : {temp_password}\n"
                    f"  (Please change your password after first login)\n\n"
                )
            msg += (
                f"\nAfter login you will be taken directly to {community.name}.\n\n"
                f"As {role_label} you can:\n"
                f"  ✓ Create and manage events\n"
                f"  ✓ Post updates and announcements\n"
                f"  ✓ Manage community members\n"
                f"  ✓ Create causes and activities\n\n"
                f"Community page: https://www.mypincod.com/portal/c/{community.page_id}/\n\n"
                f"Thank you,\nOUR PINCODE Team"
            )
            send_mail(
                subject=f"You are now {role_label} of {community.name} — OUR PINCODE",
                message=msg,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                fail_silently=True,
            )
        except Exception:
            pass

        _notify(nominee, 'leader_nomination',
                f'You are now {role_label} of {community.name}!',
                f'/portal/c/{community.page_id}/')
        messages.success(request, f'✅ {email} appointed as {role_label} and email sent with login details.')
        return redirect('portal_dashboard', page_id=page_id)

    return render(request, 'portal/add_leader.html', {
        'community': community,
        'roles': CommunityLeader.ROLES,
        'leaders': community.leaders.select_related('user').order_by('role'),
    })


# ──────────────────────────────────────────────
# CAUSES
# ──────────────────────────────────────────────

@login_required
def create_cause(request, page_id):
    community = get_object_or_404(Community, page_id=page_id)
    if not community.is_admin(request.user):
        messages.error(request, 'Only community admins can create causes.')
        return redirect('portal_community', page_id=page_id)

    if request.method == 'POST':
        p = request.POST
        cause = Cause(
            community=community, created_by=request.user,
            name=p.get('name','').strip(),
            description=p.get('description','').strip(),
            objective=p.get('objective','').strip(),
            start_date=p.get('start_date'),
            end_date=p.get('end_date') or None,
            location=p.get('location','').strip(),
            target_goal=p.get('target_goal','').strip(),
        )
        if 'image' in request.FILES:
            cause.image = request.FILES['image']
        cause.save()
        # Notify all members
        for m in community.memberships.filter(status='approved').select_related('user'):
            _notify(m.user, 'new_cause', f'New cause in {community.name}: {cause.name}', f'/portal/cause/{cause.pk}/')
        messages.success(request, 'Cause created!')
        return redirect('portal_cause_detail', pk=cause.pk)
    return render(request, 'portal/cause_create.html', {'community': community})


@login_required
def support_cause(request, pk):
    cause = get_object_or_404(Cause, pk=pk)
    obj, created = CauseSupport.objects.get_or_create(cause=cause, user=request.user)
    if not created:
        obj.delete()
        return JsonResponse({'status': 'unsupported', 'count': cause.support_count()})
    return JsonResponse({'status': 'supported', 'count': cause.support_count()})


# ──────────────────────────────────────────────
# EVENTS
# ──────────────────────────────────────────────

@login_required
def create_event_standalone(request):
    """Any logged-in user can create an event. Community is optional."""
    # communities the user belongs to (for optional linking)
    user_communities = Community.objects.filter(
        Q(created_by=request.user) |
        Q(memberships__user=request.user, memberships__status='approved')
    ).distinct()

    selected_community = None
    causes = []

    if request.method == 'POST':
        p = request.POST
        community = None
        page_id = p.get('community_page_id', '').strip()
        if page_id:
            community = Community.objects.filter(page_id=page_id).first()

        event = Event(
            community=community,
            created_by=request.user,
            name=p.get('name','').strip(),
            description=p.get('description','').strip(),
            date=p.get('date'),
            time=p.get('time'),
            location='Online' if p.get('is_online') == 'on' else p.get('location','').strip(),
            map_link=p.get('map_link','').strip(),
            contact_person=p.get('contact_person','').strip(),
            contact_phone=p.get('contact_phone','').strip(),
            is_paid=p.get('is_paid') == 'on',
            is_online=p.get('is_online') == 'on',
            online_link=p.get('online_link','').strip(),
            meeting_password=p.get('meeting_password','').strip(),
            pincode=p.get('pincode','').strip(),
            tags=p.get('tags','').strip(),
            rsvp_questions=[q.strip() for q in p.getlist('rsvp_questions[]') if q.strip()][:5],
            require_profile_photo=p.get('require_profile_photo') == 'on',
            collect_contact=p.get('collect_contact') == 'on',
            upi_id=p.get('upi_id','').strip(),
        )
        if p.get('end_date'):
            event.end_date = p.get('end_date')
        if p.get('end_time'):
            event.end_time = p.get('end_time')
        if p.get('ticket_price'):
            event.ticket_price = p.get('ticket_price')
        if p.get('max_participants'):
            event.max_participants = int(p.get('max_participants'))
        if p.get('cause'):
            event.cause_id = p.get('cause')
        if 'image' in request.FILES:
            event.image = request.FILES['image']
        if 'payment_qr' in request.FILES:
            event.payment_qr = request.FILES['payment_qr']
        event.save()
        # Notify community members if linked
        if community:
            for m in community.memberships.filter(status='approved').select_related('user'):
                _notify(m.user, 'new_event', f'New event in {community.name}: {event.name} on {event.date}', f'/portal/event/{event.pk}/')
        messages.success(request, 'Event created!')
        return redirect('portal_event_detail', pk=event.pk)

    # GET
    preselect = request.GET.get('community')
    if preselect:
        selected_community = user_communities.filter(page_id=preselect).first()
    if selected_community:
        causes = selected_community.causes.filter(is_active=True)

    return render(request, 'portal/event_create_standalone.html', {
        'user_communities': user_communities,
        'selected_community': selected_community,
        'causes': causes,
    })


@login_required
def create_event(request, page_id):
    community = get_object_or_404(Community, page_id=page_id)
    is_admin = community.is_admin(request.user)
    is_member = _is_member(community, request.user)
    if not (is_admin or is_member):
        messages.error(request, 'Only community members can request events.')
        return redirect('portal_community', page_id=page_id)

    causes = community.causes.filter(is_active=True)
    if request.method == 'POST':
        p = request.POST
        event = Event(
            community=community, created_by=request.user,
            name=p.get('name','').strip(),
            description=p.get('description','').strip(),
            date=p.get('date'),
            time=p.get('time'),
            location=p.get('location','').strip(),
            map_link=p.get('map_link','').strip(),
            contact_person=p.get('contact_person','').strip(),
            contact_phone=p.get('contact_phone','').strip(),
            is_paid=p.get('is_paid') == 'on',
            is_online=p.get('is_online') == 'on',
            online_link=p.get('online_link','').strip(),
            meeting_password=p.get('meeting_password','').strip(),
            pincode=p.get('pincode','').strip(),
            tags=p.get('tags','').strip(),
            rsvp_questions=[q.strip() for q in p.getlist('rsvp_questions[]') if q.strip()][:5],
            require_profile_photo=p.get('require_profile_photo') == 'on',
            collect_contact=p.get('collect_contact') == 'on',
            upi_id=p.get('upi_id','').strip(),
            is_active=is_admin,
        )
        if p.get('end_date'):
            event.end_date = p.get('end_date')
        if p.get('end_time'):
            event.end_time = p.get('end_time')
        if p.get('ticket_price'):
            event.ticket_price = p.get('ticket_price')
        if p.get('max_participants'):
            event.max_participants = int(p.get('max_participants'))
        if p.get('cause'):
            event.cause_id = p.get('cause')
        if 'image' in request.FILES:
            event.image = request.FILES['image']
        if 'payment_qr' in request.FILES:
            event.payment_qr = request.FILES['payment_qr']
        event.save()
        if is_admin:
            for m in community.memberships.filter(status='approved').select_related('user'):
                _notify(m.user, 'new_event', f'New event in {community.name}: {event.name} on {event.date}', f'/portal/event/{event.pk}/')
            messages.success(request, 'Event created!')
        else:
            if community.created_by:
                _notify(community.created_by, 'event_request', f'{request.user.get_full_name() or request.user.username} requested to create event "{event.name}" in {community.name}', f'/portal/c/{community.page_id}/dashboard/')
            messages.success(request, 'Event request submitted! Waiting for admin approval.')
        return redirect('portal_community', page_id=page_id)
    return render(request, 'portal/event_create.html', {'community': community, 'causes': causes, 'is_admin': is_admin})


@login_required
def event_register(request, pk):
    event = get_object_or_404(Event, pk=pk, is_active=True)
    existing = EventParticipant.objects.filter(event=event, user=request.user).first()

    # Check community membership first
    community = event.community
    if not (_is_member(community, request.user) or community.is_admin(request.user)):
        request.session['join_required_community'] = {'name': community.name, 'page_id': community.page_id}
        return redirect('portal_event_detail', pk=pk)

    # Always check profile photo (compulsory for all RSVPs)
    try:
        has_photo = bool(request.user.seeker.photo)
    except Exception:
        has_photo = False

    needs_rsvp_page = event.rsvp_questions or event.is_paid or event.collect_contact or event.require_profile_photo or not has_photo

    if needs_rsvp_page and request.method == 'GET':
        return render(request, 'portal/event_rsvp.html', {'event': event, 'has_photo': has_photo})

    # --- Profile photo check / upload ---
    if event.require_profile_photo:
        if 'profile_photo' in request.FILES:
            from jobs.models import JobSeekerProfile
            profile, _ = JobSeekerProfile.objects.get_or_create(user=request.user)
            profile.photo = request.FILES['profile_photo']
            profile.save(update_fields=['photo'])
        else:
            try:
                has_photo = bool(request.user.seeker.photo)
            except Exception:
                has_photo = False
            if not has_photo:
                messages.error(request, 'This event requires a profile photo. Please upload one on the RSVP page.')
                return redirect('portal_event_detail', pk=pk)

    # --- Collect contact + answers ---
    rsvp_email = request.POST.get('rsvp_email', '').strip()
    rsvp_phone = request.POST.get('rsvp_phone', '').strip()
    rsvp_answers = {}
    for i, _ in enumerate(event.rsvp_questions):
        ans = request.POST.get(f'rsvp_answer_{i}', '').strip()
        if ans:
            rsvp_answers[str(i)] = ans

    # --- Payment screenshot ---
    payment_screenshot = request.FILES.get('payment_screenshot')
    payment_status = 'pending' if (event.is_paid and payment_screenshot) else ''

    # --- Status ---
    initial_status = 'waitlist' if event.is_full() else ('pending' if event.is_paid else 'approved')

    if existing:
        if existing.status == 'cancelled':
            existing.status = initial_status
            existing.rsvp_answers = rsvp_answers
            existing.rsvp_email = rsvp_email
            existing.rsvp_phone = rsvp_phone
            if payment_screenshot:
                existing.payment_screenshot = payment_screenshot
                existing.payment_status = 'pending'
            existing.save()
            if existing.status == 'waitlist':
                messages.info(request, 'Event is full — added to waitlist.')
            elif existing.status == 'pending':
                messages.success(request, 'Payment screenshot submitted! Awaiting creator approval.')
            else:
                if community:
                    award_points(request.user, community, 5, f'Event RSVP: {event.name}')
                messages.success(request, "You're going! 🎉 +5 points awarded!")
        else:
            messages.info(request, 'You are already registered.')
        return redirect('portal_event_detail', pk=pk)

    role = request.POST.get('role', 'attendee')
    p = EventParticipant(
        event=event, user=request.user, role=role, status=initial_status,
        rsvp_answers=rsvp_answers, rsvp_email=rsvp_email, rsvp_phone=rsvp_phone,
        payment_status=payment_status,
    )
    if payment_screenshot:
        p.payment_screenshot = payment_screenshot
    p.save()

    if initial_status == 'waitlist':
        messages.info(request, 'Event is full — you have been added to the waitlist.')
    elif initial_status == 'pending':
        messages.success(request, 'Payment screenshot submitted! Awaiting creator approval.')
    else:
        # Award 5 points automatically on approved RSVP
        if community:
            award_points(request.user, community, 5, f'Event RSVP: {event.name}')
        messages.success(request, "You're going! See you there. 🎉 +5 points awarded!")
    return redirect('portal_event_detail', pk=pk)


@login_required
def event_cancel_registration(request, pk):
    event = get_object_or_404(Event, pk=pk)
    part  = get_object_or_404(EventParticipant, event=event, user=request.user)
    part.status = 'cancelled'
    part.save()
    # Promote first waitlist person
    next_wait = event.participants.filter(status='waitlist').order_by('registered_at').first()
    if next_wait:
        next_wait.status = 'approved'
        next_wait.save()
        _notify(next_wait.user, 'event_approved',
                f'Great news! A spot opened up for {event.name}. You are now registered!',
                f'/portal/event/{pk}/')
    messages.success(request, 'Your registration has been cancelled.')
    return redirect('portal_event_detail', pk=pk)


@login_required
def edit_event(request, pk):
    event = get_object_or_404(Event, pk=pk)
    if event.created_by != request.user and not (event.community and event.community.is_admin(request.user)):
        messages.error(request, 'Only the event creator or admin can edit this event.')
        return redirect('portal_event_detail', pk=pk)

    if request.method == 'POST':
        p = request.POST
        event.name        = p.get('name', '').strip()
        event.description = p.get('description', '').strip()
        event.date        = p.get('date')
        event.time        = p.get('time')
        event.location    = 'Online' if p.get('is_online') == 'on' else p.get('location', '').strip()
        event.is_online        = p.get('is_online') == 'on'
        event.online_link      = p.get('online_link', '').strip()
        event.meeting_password = p.get('meeting_password', '').strip()
        event.map_link         = p.get('map_link', '').strip()
        event.pincode     = p.get('pincode', '').strip()
        event.tags        = p.get('tags', '').strip()
        event.contact_person = p.get('contact_person', '').strip()
        event.contact_phone  = p.get('contact_phone', '').strip()
        event.is_paid     = p.get('is_paid') == 'on'
        event.end_date    = p.get('end_date') or None
        event.end_time    = p.get('end_time') or None
        event.ticket_price = p.get('ticket_price') or None
        event.max_participants = int(p.get('max_participants')) if p.get('max_participants') else None
        event.rsvp_questions = [q.strip() for q in p.getlist('rsvp_questions[]') if q.strip()][:5]
        event.require_profile_photo = p.get('require_profile_photo') == 'on'
        event.collect_contact       = p.get('collect_contact') == 'on'
        event.upi_id                = p.get('upi_id', '').strip()
        if 'image' in request.FILES:
            event.image = request.FILES['image']
        if 'payment_qr' in request.FILES:
            event.payment_qr = request.FILES['payment_qr']
        event.save()
        messages.success(request, 'Event updated successfully.')
        return redirect('portal_event_detail', pk=pk)

    return render(request, 'portal/event_edit.html', {'event': event})


@login_required
def manage_event(request, pk):
    event    = get_object_or_404(Event, pk=pk)
    community = event.community
    if not community.is_admin(request.user):
        return redirect('portal_event_detail', pk=pk)

    if request.method == 'POST':
        action = request.POST.get('action')
        part_id = request.POST.get('participant_id')
        part = get_object_or_404(EventParticipant, pk=part_id, event=event)
        if action == 'approve':
            part.status = 'approved'
            part.save()
            _notify(part.user, 'event_approved', f'Your registration for {event.name} has been approved!', f'/portal/event/{pk}/')
        elif action == 'reject':
            part.status = 'rejected'
            part.save()
        elif action == 'attend':
            part.attended = not part.attended
            part.save()
        elif action == 'approve_payment':
            part.payment_status = 'approved'
            part.status = 'approved'
            part.save()
            _notify(part.user, 'event_approved', f'Your payment for {event.name} has been approved!', f'/portal/event/{pk}/')
        elif action == 'reject_payment':
            part.payment_status = 'rejected'
            part.status = 'rejected'
            part.save()
            _notify(part.user, 'event_approved', f'Your payment for {event.name} was rejected. Please contact the organiser.', f'/portal/event/{pk}/')
        elif action == 'block':
            part.status = 'rejected'
            part.save()
            # Block from community if community admin
            from .models import CommunityMembership
            CommunityMembership.objects.filter(community=community, user=part.user).update(status='blocked')
            _notify(part.user, 'event_approved', f'You have been blocked from the event "{event.name}".', f'/portal/event/{pk}/')
        return redirect('portal_manage_event', pk=pk)

    status_filter = request.GET.get('status', 'pending' if event.is_paid else 'approved')
    participants = list(event.participants.filter(status=status_filter).select_related('user').order_by('role'))
    for p in participants:
        p.answers_list = [p.rsvp_answers.get(str(i), '') for i in range(len(event.rsvp_questions))]
    all_counts = {s: event.participants.filter(status=s).count() for s, _ in EventParticipant.STATUSES}
    return render(request, 'portal/manage_event.html', {
        'event': event, 'participants': participants, 'status_filter': status_filter,
        'all_counts': all_counts,
        'counts': {r: event.participants.filter(role=r).count() for r, _ in EventParticipant.ROLES},
    })


@login_required
def event_comment(request, pk):
    event = get_object_or_404(Event, pk=pk, is_active=True)
    text  = request.POST.get('text', '').strip()
    if text:
        EventComment.objects.create(event=event, user=request.user, text=text)
    return redirect('portal_event_detail', pk=pk)


@login_required
def event_announce(request, pk):
    event = get_object_or_404(Event, pk=pk)
    if not event.community.is_admin(request.user):
        return redirect('portal_event_detail', pk=pk)
    title = request.POST.get('title', '').strip()
    body  = request.POST.get('body', '').strip()
    if title and body:
        ann = EventAnnouncement.objects.create(event=event, created_by=request.user, title=title, body=body)
        # Notify all approved attendees
        for p in event.participants.filter(status='approved').select_related('user'):
            _notify(p.user, 'announcement',
                    f'[{event.name}] {title}',
                    f'/portal/event/{pk}/')
        messages.success(request, 'Announcement sent to all attendees.')
    return redirect('portal_event_detail', pk=pk)


@login_required
def event_photo_upload(request, pk):
    event = get_object_or_404(Event, pk=pk)
    is_admin = event.community.is_admin(request.user)
    is_attendee = event.participants.filter(user=request.user, status='approved').exists()
    if not (is_admin or is_attendee):
        messages.error(request, 'Only attendees can upload photos.')
        return redirect('portal_event_detail', pk=pk)
    if request.FILES.get('image'):
        EventPhoto.objects.create(
            event=event, uploaded_by=request.user,
            image=request.FILES['image'],
            caption=request.POST.get('caption', '').strip(),
        )
        messages.success(request, 'Photo uploaded!')
    return redirect('portal_event_detail', pk=pk)


@login_required
def event_rate(request, pk):
    event = get_object_or_404(Event, pk=pk)
    attended = event.participants.filter(user=request.user, status='approved').exists()
    if not attended:
        messages.error(request, 'Only attendees can rate this event.')
        return redirect('portal_event_detail', pk=pk)
    rating_val = int(request.POST.get('rating', 0))
    review = request.POST.get('review', '').strip()
    if 1 <= rating_val <= 5:
        EventRating.objects.update_or_create(
            event=event, user=request.user,
            defaults={'rating': rating_val, 'review': review},
        )
        messages.success(request, 'Thanks for your review!')
    return redirect('portal_event_detail', pk=pk)


@login_required
def event_attendee_ratings(request, pk):
    """Show all attendees of a completed event with their average received ratings."""
    from .models import AttendeeRating
    event = get_object_or_404(Event, pk=pk)
    attendees = event.participants.filter(status='approved').select_related('user')
    attendee_users = [p.user for p in attendees]
    # Build rating data for each attendee
    attendee_data = []
    for user in attendee_users:
        ratings = AttendeeRating.objects.filter(event=event, ratee=user)
        avg = ratings.aggregate(a=Avg('rating'))['a']
        my_rating = AttendeeRating.objects.filter(event=event, rater=request.user, ratee=user).first()
        attendee_data.append({
            'user': user,
            'avg_rating': round(avg, 1) if avg else None,
            'count': ratings.count(),
            'my_rating': my_rating.rating if my_rating else None,
            'is_self': user == request.user,
        })
    # Check if user has already submitted any rating for this event
    already_rated = AttendeeRating.objects.filter(event=event, rater=request.user).exists()

    if request.method == 'POST':
        if already_rated:
            messages.info(request, 'You have already submitted your ratings for this event.')
            return redirect('portal_event_detail', pk=pk)
        community = event.community

        def _save_and_award(ratee, rating_val):
            obj, created = AttendeeRating.objects.get_or_create(
                event=event, rater=request.user, ratee=ratee,
                defaults={'rating': rating_val},
            )
            if created and community:
                award_points(ratee, community, rating_val,
                             f'Peer rating at event: {event.name} ({rating_val}⭐ from {request.user.get_full_name or request.user.username})')

        # Single-rating POST (from separate ratings page)
        ratee_id = request.POST.get('ratee_id')
        if ratee_id:
            rating_val = int(request.POST.get('rating', 0))
            if 1 <= rating_val <= 5:
                ratee = get_object_or_404(User, pk=ratee_id)
                if ratee in attendee_users and ratee != request.user:
                    _save_and_award(ratee, rating_val)
        else:
            # Multi-rating POST from embedded event detail form (rating_<uid> fields)
            for key, val in request.POST.items():
                if key.startswith('rating_'):
                    try:
                        uid = int(key[7:])
                        rating_val = int(val)
                    except (ValueError, TypeError):
                        continue
                    if 1 <= rating_val <= 5:
                        try:
                            ratee = User.objects.get(pk=uid)
                        except User.DoesNotExist:
                            continue
                        if ratee in attendee_users and ratee != request.user:
                            _save_and_award(ratee, rating_val)
            messages.success(request, 'Your ratings have been submitted! ⭐')
        return redirect('portal_event_detail', pk=pk)
    return render(request, 'portal/event_attendee_ratings.html', {
        'event': event,
        'attendee_data': attendee_data,
        'already_rated': already_rated,
    })


@login_required
def event_update_status(request, pk):
    event = get_object_or_404(Event, pk=pk)
    if not event.community.is_admin(request.user):
        return redirect('portal_event_detail', pk=pk)
    new_status = request.POST.get('status')
    if new_status in dict(Event.STATUS_CHOICES):
        event.status = new_status
        event.save(update_fields=['status'])
        if new_status == 'cancelled':
            for p in event.participants.filter(status__in=['approved','pending','waitlist']).select_related('user'):
                _notify(p.user, 'announcement',
                        f'Event cancelled: {event.name}',
                        f'/portal/event/{pk}/')
    return redirect('portal_manage_event', pk=pk)


# ──────────────────────────────────────────────
# VOLUNTEER
# ──────────────────────────────────────────────

def volunteer_form(request, page_id):
    community = get_object_or_404(Community, page_id=page_id, is_active=True)
    events    = community.events.filter(is_active=True, date__gte=timezone.now().date()).order_by('date')

    if request.method == 'POST':
        p = request.POST
        vr = VolunteerRequest(
            community=community,
            name=p.get('name','').strip(),
            email=p.get('email','').strip(),
            mobile=p.get('mobile','').strip(),
            volunteer_interest=p.get('volunteer_interest','').strip(),
            message=p.get('message','').strip(),
            availability=p.get('availability','').strip(),
        )
        if request.user.is_authenticated:
            vr.user = request.user
        if p.get('event'):
            vr.event_id = p.get('event')
        vr.save()
        if community.created_by:
            _notify(community.created_by, 'join_request',
                    f'{vr.name} wants to volunteer for {community.name}.',
                    f'/portal/c/{page_id}/volunteers/')
        messages.success(request, 'Volunteer request submitted! Community admin will review it.')
        return redirect('portal_community', page_id=page_id)

    return render(request, 'portal/volunteer_form.html', {'community': community, 'events': events})


@login_required
def manage_volunteers(request, page_id):
    community = get_object_or_404(Community, page_id=page_id)
    if not community.is_admin(request.user):
        return redirect('portal_community', page_id=page_id)

    if request.method == 'POST':
        vr_id  = request.POST.get('vr_id')
        action = request.POST.get('action')
        vr = get_object_or_404(VolunteerRequest, pk=vr_id, community=community)
        if action == 'approve':
            vr.status = 'approved'
            vr.save()
            if vr.user:
                _notify(vr.user, 'volunteer_approved', f'Your volunteer request for {community.name} is approved!', f'/portal/c/{page_id}/')
        elif action == 'reject':
            vr.status = 'rejected'
            vr.save()
        return redirect('portal_manage_volunteers', page_id=page_id)

    status_filter = request.GET.get('status', 'pending')
    vrs = community.volunteer_requests.filter(status=status_filter).order_by('-created_at')
    return render(request, 'portal/manage_volunteers.html', {
        'community': community, 'vrs': vrs, 'status_filter': status_filter,
        'pending_count': community.volunteer_requests.filter(status='pending').count(),
        'approved_count': community.volunteer_requests.filter(status='approved').count(),
    })


# ──────────────────────────────────────────────
# ACTIVITIES
# ──────────────────────────────────────────────

@login_required
def create_activity(request, page_id):
    community = get_object_or_404(Community, page_id=page_id)
    if not community.is_admin(request.user):
        messages.error(request, 'Only community admins can log activities.')
        return redirect('portal_community', page_id=page_id)

    causes = community.causes.filter(is_active=True)
    if request.method == 'POST':
        p = request.POST
        activity = Activity(
            community=community, created_by=request.user,
            name=p.get('name','').strip(),
            description=p.get('description','').strip(),
            date=p.get('date'),
            location=p.get('location','').strip(),
            participant_count=int(p.get('participant_count',0) or 0),
            volunteer_count=int(p.get('volunteer_count',0) or 0),
            result_impact=p.get('result_impact','').strip(),
        )
        if p.get('cause'):
            activity.cause_id = p.get('cause')
        activity.save()
        # Save photos
        for f in request.FILES.getlist('photos'):
            ActivityPhoto.objects.create(activity=activity, image=f)
        messages.success(request, 'Activity logged!')
        return redirect('portal_activity_detail', pk=activity.pk)
    return render(request, 'portal/activity_create.html', {'community': community, 'causes': causes})


# ──────────────────────────────────────────────
# COMMUNITY FEED (POSTS)
# ──────────────────────────────────────────────

@login_required
def create_post(request, page_id):
    community = get_object_or_404(Community, page_id=page_id)
    if not (_is_member(community, request.user) or community.is_admin(request.user)):
        messages.error(request, 'Only members can post.')
        return redirect('portal_community', page_id=page_id)

    if request.method == 'POST':
        from datetime import date as _date
        p = request.POST
        event_date = None
        raw_date = p.get('event_date', '').strip()
        if raw_date:
            try:
                event_date = _date.fromisoformat(raw_date)
            except ValueError:
                pass
        post = Post(
            community=community, author=request.user,
            post_type=p.get('post_type', 'update'),
            content=p.get('content', '').strip(),
            event_date=event_date,
        )
        imgs = request.FILES.getlist('image')
        if imgs:
            post.image = imgs[0]
        post.save()
        messages.success(request, 'Post published!')
    return redirect('portal_community', page_id=page_id)


@login_required
def like_post(request, pk):
    post = get_object_or_404(Post, pk=pk)
    obj, created = PostLike.objects.get_or_create(post=post, user=request.user)
    if not created:
        obj.delete()
    return JsonResponse({'liked': created, 'count': post.like_count()})


@login_required
def comment_post(request, pk):
    post = get_object_or_404(Post, pk=pk)
    if request.method == 'POST':
        content = request.POST.get('content','').strip()
        if content:
            PostComment.objects.create(post=post, user=request.user, content=content)
    return redirect(request.META.get('HTTP_REFERER', f'/portal/c/{post.community.page_id}/'))


@login_required
def delete_post(request, pk):
    post = get_object_or_404(Post, pk=pk)
    community = post.community
    if post.author == request.user or community.is_admin(request.user):
        page_id = community.page_id
        post.delete()
        return redirect(f'/portal/c/{page_id}/')
    messages.error(request, 'Permission denied.')
    return redirect(f'/portal/c/{community.page_id}/')


# ──────────────────────────────────────────────
# VIDEOS
# ──────────────────────────────────────────────

@login_required
def upload_video(request, page_id):
    community = get_object_or_404(Community, page_id=page_id)
    if not (_is_member(community, request.user) or community.is_admin(request.user)):
        messages.error(request, 'Only members can upload videos.')
        return redirect('portal_community', page_id=page_id)

    causes     = community.causes.filter(is_active=True)
    events     = community.events.filter(is_active=True)
    activities = community.activities.filter(is_active=True)

    if request.method == 'POST':
        p = request.POST
        video = ShortVideo(
            community=community, uploader=request.user,
            title=p.get('title','').strip(),
            category=p.get('category','story'),
            pincode=p.get('pincode','').strip(),
            location=p.get('location','').strip(),
        )
        if 'video' in request.FILES:
            video.video = request.FILES['video']
        if 'thumbnail' in request.FILES:
            video.thumbnail = request.FILES['thumbnail']
        if p.get('related_event'):
            video.related_event_id = p.get('related_event')
        if p.get('related_cause'):
            video.related_cause_id = p.get('related_cause')
        if p.get('related_activity'):
            video.related_activity_id = p.get('related_activity')
        video.save()
        messages.success(request, 'Video uploaded!')
        return redirect('portal_community', page_id=page_id)

    return render(request, 'portal/video_upload.html', {
        'community': community, 'causes': causes, 'events': events, 'activities': activities,
        'categories': ShortVideo.VIDEO_CATS,
    })


@login_required
def delete_video(request, pk):
    video = get_object_or_404(ShortVideo, pk=pk)
    if request.user == video.uploader or video.community.is_admin(request.user) or request.user.is_staff:
        video.is_active = False
        video.save()
        messages.success(request, 'Video removed.')
    return redirect(request.META.get('HTTP_REFERER', '/portal/videos/'))


# ──────────────────────────────────────────────
# USER: MY PAGES
# ──────────────────────────────────────────────

@login_required
def my_communities(request):
    memberships = CommunityMember.objects.filter(user=request.user).select_related('community').order_by('-joined_at')
    return render(request, 'portal/my_communities.html', {'memberships': memberships})


@login_required
def my_events(request):
    registrations = EventParticipant.objects.filter(user=request.user).select_related('event__community').order_by('-registered_at')
    return render(request, 'portal/my_events.html', {'registrations': registrations})


@login_required
def portal_notifications(request):
    notifs = request.user.portal_notifications.all()[:50]
    request.user.portal_notifications.filter(is_read=False).update(is_read=True)
    return render(request, 'portal/notifications.html', {'notifs': notifs})


# ──────────────────────────────────────────────
# PLATFORM ADMIN
# ──────────────────────────────────────────────

def _require_staff(request):
    return request.user.is_authenticated and request.user.is_staff


# ──────────────────────────────────────────────
# COMMUNITY EDIT
# ──────────────────────────────────────────────

@login_required
def edit_community(request, page_id):
    community = get_object_or_404(Community, page_id=page_id, is_active=True)
    if not community.is_admin(request.user):
        messages.error(request, 'Only community admins can edit.')
        return redirect('portal_community', page_id=page_id)

    if request.method == 'POST':
        p = request.POST
        community.name        = p.get('name', '').strip() or community.name
        community.purpose     = p.get('purpose', '').strip()
        community.description = p.get('description', '').strip()
        community.location    = p.get('location', '').strip()
        community.pincode     = p.get('pincode', '').strip()
        community.email       = p.get('comm_email', '').strip()
        community.phone       = p.get('comm_phone', '').strip()
        community.join_mode   = p.get('join_mode', community.join_mode)
        cat_id = p.get('category')
        community.category_id = cat_id if cat_id else None
        def _save_b64(field_name, file_name):
            import base64, io
            from django.core.files.base import ContentFile
            data = request.POST.get(field_name + '_cropped', '')
            if data and data.startswith('data:image'):
                fmt, imgstr = data.split(';base64,', 1)
                return ContentFile(base64.b64decode(imgstr), name=file_name + '.jpg')
            return None
        logo_file = _save_b64('logo', f'logo_{community.page_id}')
        cover_file = _save_b64('cover', f'cover_{community.page_id}')
        if logo_file:
            community.logo = logo_file
        elif 'logo' in request.FILES:
            community.logo = request.FILES['logo']
        if cover_file:
            community.cover = cover_file
        elif 'cover' in request.FILES:
            community.cover = request.FILES['cover']
        community.save()
        messages.success(request, 'Community updated successfully!')
        return redirect('portal_community', page_id=community.page_id)

    return render(request, 'portal/community_edit.html', {
        'community': community,
        'categories': Category.objects.all(),
    })


# ──────────────────────────────────────────────
# FLICK
# ──────────────────────────────────────────────

def flick_feed(request):
    community_filter = request.GET.get('community', '')

    # Auto-promote ShortVideos to Flick records so likes/comments work
    videos_qs = ShortVideo.objects.filter(is_active=True).select_related('community', 'uploader')
    if community_filter:
        videos_qs = videos_qs.filter(community__page_id=community_filter)
    for v in videos_qs:
        Flick.objects.get_or_create(
            source_video_id=v.pk,
            defaults={
                'community': v.community,
                'posted_by': v.uploader,
                'caption': v.title,
                'media': v.video,
                'media_type': 'video',
                'is_active': True,
                'created_at': v.created_at,
            }
        )

    flicks_qs = Flick.objects.filter(is_active=True).select_related('community', 'posted_by')
    if community_filter:
        flicks_qs = flicks_qs.filter(community__page_id=community_filter)
    flicks_qs = flicks_qs.order_by('-created_at')

    liked_ids = set()
    admin_community_ids = set()
    if request.user.is_authenticated:
        liked_ids = set(FlickLike.objects.filter(user=request.user).values_list('flick_id', flat=True))
        # Communities where current user is admin/leader
        from portal.models import CommunityLeader
        admin_community_ids = set(
            Community.objects.filter(created_by=request.user, is_active=True).values_list('page_id', flat=True)
        ) | set(
            CommunityLeader.objects.filter(user=request.user, status='accepted').values_list('community__page_id', flat=True)
        )
        if getattr(request.user, 'admin_role', '') == 'super_admin':
            admin_community_ids = set(Community.objects.values_list('page_id', flat=True))

    my_pending = []
    if request.user.is_authenticated:
        my_pending = Flick.objects.filter(posted_by=request.user, is_active=False).order_by('-created_at')

    return render(request, 'portal/flick_feed.html', {
        'flicks': flicks_qs,
        'liked_ids': liked_ids,
        'community_filter': community_filter,
        'admin_community_ids': admin_community_ids,
        'my_pending': my_pending,
    })


@login_required
def create_flick(request):
    user_communities = Community.objects.filter(
        memberships__user=request.user, memberships__status='approved', is_active=True
    ).distinct()

    if request.method == 'POST':
        p = request.POST
        community_id = p.get('community')
        community = get_object_or_404(Community, page_id=community_id)
        if not community.memberships.filter(user=request.user, status='approved').exists():
            messages.error(request, 'You must be a member of this community to post a Flick.')
            return redirect('portal_flicks')

        if 'media' not in request.FILES:
            messages.error(request, 'Please upload a video or image.')
            return render(request, 'portal/flick_create.html', {'user_communities': user_communities})

        media = request.FILES['media']
        media_type = 'video' if media.content_type.startswith('video') else 'image'

        is_comm_admin = community.is_admin(request.user)
        flick = Flick.objects.create(
            community=community,
            posted_by=request.user,
            caption=p.get('caption', '').strip()[:300],
            media=media,
            media_type=media_type,
            is_active=is_comm_admin,
        )
        if is_comm_admin:
            messages.success(request, 'Flick posted!')
        else:
            if community.created_by:
                _notify(community.created_by, 'flick_request', f'{request.user.get_full_name() or request.user.username} posted a Flick in {community.name} — awaiting your approval.', f'/portal/c/{community.page_id}/dashboard/')
            messages.success(request, 'Flick submitted! Waiting for admin approval.')
        return redirect('portal_flicks')

    preselect = request.GET.get('community', '')
    return render(request, 'portal/flick_create.html', {
        'user_communities': user_communities,
        'preselect': preselect,
    })


@login_required
def like_flick(request, pk):
    flick = get_object_or_404(Flick, pk=pk, is_active=True)
    obj, created = FlickLike.objects.get_or_create(flick=flick, user=request.user)
    if not created:
        obj.delete()
        return JsonResponse({'liked': False, 'count': flick.like_count()})
    return JsonResponse({'liked': True, 'count': flick.like_count()})


@login_required
def delete_flick(request, pk):
    flick = get_object_or_404(Flick, pk=pk, posted_by=request.user)
    if request.method == 'POST':
        flick.is_active = False
        flick.save()
        return JsonResponse({'deleted': True})
    return JsonResponse({'error': 'POST required'}, status=405)


def member_profile(request, user_id):
    target = get_object_or_404(User, pk=user_id)
    # Only community admins can view this
    if not request.user.is_authenticated:
        return redirect(f'/login/?next=/portal/member/{user_id}/')
    is_any_admin = (
        getattr(request.user, 'admin_role', '') == 'super_admin' or
        CommunityLeader.objects.filter(user=request.user, status='accepted').exists() or
        Community.objects.filter(created_by=request.user).exists()
    )
    if not is_any_admin:
        messages.error(request, 'Access denied.')
        return redirect('portal_home')
    try:
        profile = target.seeker
    except Exception:
        profile = None
    return render(request, 'portal/member_profile.html', {
        'target': target,
        'profile': profile,
    })


@login_required
def approve_flick(request, pk):
    flick = get_object_or_404(Flick, pk=pk)
    if flick.community and flick.community.is_admin(request.user):
        flick.is_active = True
        flick.approved_by = request.user
        flick.save(update_fields=['is_active', 'approved_by'])
        messages.success(request, 'Flick approved and published.')
    return redirect(f'/portal/c/{flick.community.page_id}/dashboard/')


@login_required
def reject_flick(request, pk):
    flick = get_object_or_404(Flick, pk=pk)
    if flick.community and flick.community.is_admin(request.user):
        page_id = flick.community.page_id
        flick.delete()
        messages.success(request, 'Flick rejected and removed.')
        return redirect(f'/portal/c/{page_id}/dashboard/')
    return redirect('portal_home')


def flick_comments(request, pk):
    flick = get_object_or_404(Flick, pk=pk, is_active=True)
    comments = list(flick.flick_comments.select_related('user').values(
        'id', 'text', 'created_at', 'user__first_name', 'user__last_name', 'user__username'
    ))
    for c in comments:
        name = (c['user__first_name'] + ' ' + c['user__last_name']).strip()
        c['name'] = name or c['user__username']
        del c['user__first_name']; del c['user__last_name']; del c['user__username']
        c['created_at'] = c['created_at'].strftime('%d %b')
    return JsonResponse({'comments': comments, 'count': len(comments)})


@login_required
def flick_comment_add(request, pk):
    flick = get_object_or_404(Flick, pk=pk, is_active=True)
    if request.method == 'POST':
        import json
        data = json.loads(request.body)
        text = data.get('text', '').strip()[:500]
        if text:
            c = FlickComment.objects.create(flick=flick, user=request.user, text=text)
            name = request.user.get_full_name() or request.user.username
            return JsonResponse({'ok': True, 'id': c.pk, 'name': name, 'text': text, 'created_at': c.created_at.strftime('%d %b'), 'count': flick.flick_comments.count()})
    return JsonResponse({'ok': False})


@login_required
def admin_communities(request):
    if not _require_staff(request):
        return redirect('portal_home')
    communities = Community.objects.all().select_related('created_by', 'category').order_by('-created_at')
    status = request.GET.get('status', '')
    if status == 'pending':
        communities = communities.filter(is_verified=False, is_active=True)
    elif status == 'unverified':
        communities = communities.filter(is_verified=False, is_active=True)
    elif status == 'verified':
        communities = communities.filter(is_verified=True, is_active=True)
    elif status == 'rejected':
        communities = communities.filter(is_verified=False, is_active=False)
    elif status == 'suspended':
        communities = communities.filter(is_verified=True, is_active=False)
    return render(request, 'portal/admin_communities.html', {
        'communities': communities, 'status': status,
        'total': Community.objects.count(),
        'unverified': Community.objects.filter(is_verified=False, is_active=True).count(),
        'verified': Community.objects.filter(is_verified=True, is_active=True).count(),
        'rejected': Community.objects.filter(is_verified=False, is_active=False).count(),
    })


@login_required
def admin_verify_community(request, pk):
    if not _require_staff(request):
        return redirect('portal_home')
    community = get_object_or_404(Community, pk=pk)
    community.is_verified = True
    community.save()
    if community.created_by:
        _notify(community.created_by, 'announcement',
                f'Your community {community.name} has been verified and is now live!',
                f'/portal/c/{community.page_id}/')
    messages.success(request, f'{community.name} verified.')
    return redirect('portal_admin_communities')


@login_required
def admin_suspend_community(request, pk):
    if not _require_staff(request):
        return redirect('portal_home')
    community = get_object_or_404(Community, pk=pk)
    community.is_active = not community.is_active
    community.save()
    action = 'reactivated' if community.is_active else 'suspended'
    messages.success(request, f'{community.name} {action}.')
    return redirect('portal_admin_communities')


@login_required
def admin_reject_community(request, pk):
    if not _require_staff(request):
        return redirect('portal_home')
    community = get_object_or_404(Community, pk=pk)
    community.is_verified = False
    community.is_active = False
    community.save()
    if community.created_by:
        _notify(community.created_by, 'announcement',
                f'Your community "{community.name}" was not approved. Please contact support for details.',
                '/portal/create/')
    messages.success(request, f'{community.name} rejected.')
    return redirect('portal_admin_communities')


@login_required
def admin_delete_community(request, pk):
    if not _require_staff(request):
        return redirect('portal_home')
    community = get_object_or_404(Community, pk=pk)
    if request.method == 'POST':
        name = community.name
        community.delete()
        messages.success(request, f'Community "{name}" permanently deleted.')
        return redirect('portal_admin_communities')
    return render(request, 'portal/admin_community_confirm_delete.html', {'community': community})


@login_required
def admin_delete_video(request, pk):
    if not _require_staff(request):
        return redirect('portal_home')
    video = get_object_or_404(ShortVideo, pk=pk)
    video.is_active = False
    video.save()
    messages.success(request, 'Video removed.')
    return redirect('portal_videos')


@login_required
def approve_event(request, pk):
    event = get_object_or_404(Event, pk=pk)
    if event.community and event.community.is_admin(request.user):
        event.is_active = True
        event.save(update_fields=['is_active'])
        for m in event.community.memberships.filter(status='approved').select_related('user'):
            _notify(m.user, 'new_event', f'New event in {event.community.name}: {event.name} on {event.date}', f'/portal/event/{event.pk}/')
        messages.success(request, f'Event "{event.name}" approved and published.')
    return redirect(f'/portal/c/{event.community.page_id}/dashboard/')


@login_required
def reject_event(request, pk):
    event = get_object_or_404(Event, pk=pk)
    if event.community and event.community.is_admin(request.user):
        page_id = event.community.page_id
        event.delete()
        messages.success(request, 'Event request rejected and removed.')
        return redirect(f'/portal/c/{page_id}/dashboard/')
    return redirect('portal_home')


@login_required
def admin_delete_event(request, pk):
    if not _require_staff(request):
        return redirect('portal_home')
    event = get_object_or_404(Event, pk=pk)
    if request.method == 'POST':
        name = event.name
        event.is_active = False
        event.save()
        messages.success(request, f'Event "{name}" has been deleted.')
        return redirect('portal_events')
    return render(request, 'portal/admin_event_confirm_delete.html', {'event': event})


# ── Community Points & Recognition Views ─────────────────────────────────────

def community_leaderboard(request, slug):
    community = get_object_or_404(Community, slug=slug)
    period = request.GET.get('period', 'alltime')
    now = timezone.now()

    qs = MemberPoints.objects.filter(community=community).select_related('user').order_by('-total_points')
    board = list(qs[:50])

    my_rank = None
    if request.user.is_authenticated:
        for i, mp in enumerate(board, 1):
            if mp.user == request.user:
                my_rank = i
                break

    # top 3 for podium
    top3 = board[:3]

    # Last month best performer
    last_month_start = (now.replace(day=1) - timezone.timedelta(days=1)).replace(day=1)
    last_month_end   = now.replace(day=1) - timezone.timedelta(seconds=1)
    last_month_best = PointAuditLog.objects.filter(
        community=community,
        created_at__gte=last_month_start,
        created_at__lte=last_month_end,
    ).values('user').annotate(
        total=Sum(ExpressionWrapper(F('points_after') - F('points_before'), output_field=IntegerField()))
    ).order_by('-total').first()
    last_month_performer = None
    if last_month_best:
        try:
            last_month_performer = User.objects.get(pk=last_month_best['user'])
            last_month_performer.last_month_pts = last_month_best['total']
        except User.DoesNotExist:
            pass

    ctx = {
        'community': community,
        'board': board,
        'top3': top3,
        'my_rank': my_rank,
        'period': period,
        'is_admin': community.is_admin(request.user),
        'last_month_performer': last_month_performer,
        'last_month_label': last_month_start.strftime('%B %Y'),
    }
    return render(request, 'portal/leaderboard.html', ctx)


@login_required
def my_contribution_profile(request, slug):
    community = get_object_or_404(Community, slug=slug)
    user = request.user

    mp = MemberPoints.objects.filter(user=user, community=community).first()
    total_points = mp.total_points if mp else 0

    participations = Participation.objects.filter(
        user=user, community=community
    ).select_related('event', 'activity', 'cause').order_by('-created_at')

    contributions = Contribution.objects.filter(
        user=user, community=community
    ).select_related('event', 'activity', 'cause').order_by('-created_at')

    badges = MemberBadge.objects.filter(user=user, community=community).select_related('badge')
    recognitions = Recognition.objects.filter(user=user, community=community).order_by('-year')
    audit_log = PointAuditLog.objects.filter(user=user, community=community)[:20]

    # rank
    rank = MemberPoints.objects.filter(
        community=community, total_points__gt=total_points
    ).count() + 1

    events_count = participations.filter(event__isnull=False, status='confirmed').count()
    activities_count = participations.filter(activity__isnull=False, status='confirmed').count()
    volunteer_count = participations.filter(role='volunteer', status='confirmed').count()
    causes_count = participations.filter(cause__isnull=False, status='confirmed').values('cause').distinct().count()

    ctx = {
        'community': community,
        'total_points': total_points,
        'rank': rank,
        'events_count': events_count,
        'activities_count': activities_count,
        'volunteer_count': volunteer_count,
        'causes_count': causes_count,
        'participations': participations,
        'contributions': contributions,
        'badges': badges,
        'recognitions': recognitions,
        'audit_log': audit_log,
    }
    return render(request, 'portal/my_contribution.html', ctx)


@login_required
def contribution_submit(request, slug):
    community = get_object_or_404(Community, slug=slug)
    # must be a member
    is_member = community.memberships.filter(user=request.user, status='approved').exists()
    is_admin = community.is_admin(request.user)
    if not (is_member or is_admin):
        messages.error(request, 'You must be a member to submit contributions.')
        return redirect('portal_community', page_id=community.page_id)

    events = community.events.filter(is_active=True).order_by('-date')
    activities = community.activities.filter(is_active=True).order_by('-date')
    causes = community.causes.filter(is_active=True)

    if request.method == 'POST':
        ctype = request.POST.get('contribution_type')
        desc = request.POST.get('description', '').strip()
        if not ctype or not desc:
            messages.error(request, 'Please fill all required fields.')
        else:
            contrib = Contribution(
                user=request.user,
                community=community,
                contribution_type=ctype,
                description=desc,
                status='pending',
            )
            amt = request.POST.get('amount')
            if amt:
                try:
                    contrib.amount = float(amt)
                except ValueError:
                    pass
            ev = request.POST.get('amount')
            est = request.POST.get('estimated_value')
            if est:
                try:
                    contrib.estimated_value = float(est)
                except ValueError:
                    pass
            contrib.transaction_ref = request.POST.get('transaction_ref', '')
            eid = request.POST.get('event')
            if eid:
                try:
                    contrib.event = community.events.get(pk=eid)
                except Event.DoesNotExist:
                    pass
            aid = request.POST.get('activity')
            if aid:
                try:
                    contrib.activity = community.activities.get(pk=aid)
                except Activity.DoesNotExist:
                    pass
            cid = request.POST.get('cause')
            if cid:
                try:
                    contrib.cause = community.causes.get(pk=cid)
                except Cause.DoesNotExist:
                    pass
            contrib.save()
            # notify admin
            _notify(community.created_by, 'contribution_pending',
                    f'💙 {request.user.get_full_name() or request.user.username} submitted a contribution in {community.name}.',
                    f'/portal/c/{community.slug}/contributions/pending/')
            messages.success(request, 'Contribution submitted! Waiting for admin approval.')
            return redirect('my_contribution_profile', slug=slug)

    ctx = {
        'community': community,
        'events': events,
        'activities': activities,
        'causes': causes,
        'contribution_types': Contribution.TYPES,
    }
    return render(request, 'portal/contribution_form.html', ctx)


@login_required
def contributions_pending(request, slug):
    community = get_object_or_404(Community, slug=slug)
    if not community.is_admin(request.user):
        messages.error(request, 'Admin access required.')
        return redirect('portal_community', page_id=community.page_id)
    pending = Contribution.objects.filter(community=community, status='pending').select_related('user', 'event').order_by('-created_at')
    return render(request, 'portal/contributions_pending.html', {
        'community': community, 'pending': pending,
    })


@login_required
def contribution_verify(request, slug, pk):
    community = get_object_or_404(Community, slug=slug)
    if not community.is_admin(request.user):
        messages.error(request, 'Admin access required.')
        return redirect('portal_community', page_id=community.page_id)
    contrib = get_object_or_404(Contribution, pk=pk, community=community)
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'approve' and contrib.status == 'pending':
            contrib.status = 'approved'
            contrib.verified_by = request.user
            contrib.verified_at = timezone.now()
            # Points = estimated_value / 200 (min 1, max 100)
            if contrib.estimated_value and contrib.estimated_value > 0:
                pts = max(1, min(100, int(float(contrib.estimated_value) / 200)))
            else:
                pts = 15 if contrib.contribution_type == 'financial' else 10
            contrib.points_awarded = pts
            contrib.save()
            award_points(contrib.user, community, pts,
                         f'Contribution approved: {contrib.contribution_type}', done_by=request.user)
            _notify(contrib.user, 'points',
                    f'🙌 Your contribution to {community.name} was approved! You earned {pts} points.',
                    f'/portal/c/{community.slug}/my-contribution/')
            messages.success(request, f'Contribution approved. {pts} points awarded.')
        elif action == 'reject':
            contrib.status = 'rejected'
            contrib.verified_by = request.user
            contrib.verified_at = timezone.now()
            contrib.save()
            _notify(contrib.user, 'announcement',
                    f'❌ Your contribution to {community.name} was not approved this time.',
                    f'/portal/c/{community.slug}/my-contribution/')
            messages.success(request, 'Contribution rejected.')
        return redirect(request.META.get('HTTP_REFERER', '/'))
    return redirect('portal_community', page_id=community.page_id)


@login_required
def participation_confirm(request, slug, pk):
    community = get_object_or_404(Community, slug=slug)
    if not community.is_admin(request.user):
        messages.error(request, 'Admin access required.')
        return redirect('portal_community', page_id=community.page_id)
    part = get_object_or_404(Participation, pk=pk, community=community)
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'confirm' and part.status == 'pending':
            part.status = 'confirmed'
            part.verified_by = request.user
            part.verified_at = timezone.now()
            # determine point key
            role_map = {
                'attendee': 'attend_event',
                'organiser': 'organise_event',
                'volunteer': 'volunteer_event' if part.event else 'volunteer_activity',
                'contributor': 'upload_contribution',
            }
            key = role_map.get(part.role, 'attend_event')
            pts = get_point_value(key, 10)
            part.points_awarded = pts
            part.save()
            award_points(part.user, community, pts,
                         f'Participation confirmed: {part.role}', done_by=request.user)
            messages.success(request, f'Participation confirmed. {pts} points awarded.')
        elif action == 'reject':
            part.status = 'rejected'
            part.verified_by = request.user
            part.verified_at = timezone.now()
            part.save()
            messages.success(request, 'Participation rejected.')
        return redirect(request.META.get('HTTP_REFERER', '/'))
    return redirect('portal_community', page_id=community.page_id)


@login_required
def event_participation_admin(request, slug, event_id):
    community = get_object_or_404(Community, slug=slug)
    if not community.is_admin(request.user):
        messages.error(request, 'Admin access required.')
        return redirect('portal_community', page_id=community.page_id)
    event = get_object_or_404(Event, pk=event_id, community=community)

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'confirm_all':
            # confirm all pending participations for this event
            pending = Participation.objects.filter(event=event, community=community, status='pending')
            for p in pending:
                p.status = 'confirmed'
                p.verified_by = request.user
                p.verified_at = timezone.now()
                pts = get_point_value('attend_event', 10)
                p.points_awarded = pts
                p.save()
                award_points(p.user, community, pts, f'Event attended: {event.name}', done_by=request.user)
            messages.success(request, f'All {pending.count()} participants confirmed.')
        else:
            part_id = request.POST.get('participation_id')
            part = get_object_or_404(Participation, pk=part_id, event=event, community=community)
            if action == 'confirm' and part.status == 'pending':
                part.status = 'confirmed'
                part.verified_by = request.user
                part.verified_at = timezone.now()
                role_map = {'attendee': 'attend_event', 'organiser': 'organise_event', 'volunteer': 'volunteer_event'}
                key = role_map.get(part.role, 'attend_event')
                pts = get_point_value(key, 10)
                part.points_awarded = pts
                part.save()
                award_points(part.user, community, pts, f'Event: {event.name} ({part.role})', done_by=request.user)
                messages.success(request, f'Confirmed. {pts} pts awarded.')
            elif action == 'reject':
                part.status = 'rejected'
                part.verified_by = request.user
                part.verified_at = timezone.now()
                part.save()
                messages.success(request, 'Rejected.')
        return redirect('event_participation_admin', slug=slug, event_id=event_id)

    participations = Participation.objects.filter(
        event=event, community=community
    ).select_related('user').order_by('status', 'created_at')

    ctx = {
        'community': community,
        'event': event,
        'participations': participations,
        'is_admin': True,
    }
    return render(request, 'portal/event_participants_admin.html', ctx)


@login_required
def record_participation(request, slug):
    community = get_object_or_404(Community, slug=slug)
    if not community.is_admin(request.user):
        messages.error(request, 'Admin access required.')
        return redirect('portal_community', page_id=community.page_id)

    members = community.memberships.filter(status='approved').select_related('user')
    events = community.events.filter(is_active=True).order_by('-date')
    activities = community.activities.filter(is_active=True).order_by('-date')
    causes = community.causes.filter(is_active=True)

    if request.method == 'POST':
        uid = request.POST.get('user_id')
        role = request.POST.get('role', 'attendee')
        eid = request.POST.get('event_id')
        aid = request.POST.get('activity_id')
        cid = request.POST.get('cause_id')
        notes = request.POST.get('notes', '')
        try:
            target_user = User.objects.get(pk=uid)
        except User.DoesNotExist:
            messages.error(request, 'Invalid user.')
            return redirect('record_participation', slug=slug)

        kwargs = dict(user=target_user, community=community, role=role)
        if eid:
            try:
                kwargs['event'] = community.events.get(pk=eid)
            except Event.DoesNotExist:
                pass
        if aid:
            try:
                kwargs['activity'] = community.activities.get(pk=aid)
            except Activity.DoesNotExist:
                pass
        if cid:
            try:
                kwargs['cause'] = community.causes.get(pk=cid)
            except Cause.DoesNotExist:
                pass

        part, created = Participation.objects.get_or_create(
            **kwargs,
            defaults={'status': 'confirmed', 'notes': notes, 'verified_by': request.user,
                      'verified_at': timezone.now()}
        )
        if not created:
            messages.warning(request, 'Participation record already exists.')
        else:
            role_map = {'attendee': 'attend_event', 'organiser': 'organise_event',
                        'volunteer': 'volunteer_event', 'contributor': 'upload_contribution'}
            key = role_map.get(role, 'attend_event')
            pts = get_point_value(key, 10)
            part.points_awarded = pts
            part.save()
            award_points(target_user, community, pts, f'Manual participation: {role}', done_by=request.user)
            messages.success(request, f'Participation recorded. {pts} pts awarded.')
        return redirect('record_participation', slug=slug)

    ctx = {
        'community': community,
        'members': members,
        'events': events,
        'activities': activities,
        'causes': causes,
        'roles': Participation.ROLES,
    }
    return render(request, 'portal/record_participation.html', ctx)


@login_required
def adjust_points(request, slug, member_id):
    community = get_object_or_404(Community, slug=slug)
    if not community.is_admin(request.user):
        messages.error(request, 'Admin access required.')
        return redirect('portal_community', page_id=community.page_id)
    target_user = get_object_or_404(User, pk=member_id)
    if request.method == 'POST':
        try:
            pts = int(request.POST.get('points', 0))
        except ValueError:
            pts = 0
        reason = request.POST.get('reason', 'Manual adjustment').strip() or 'Manual adjustment'
        if pts != 0:
            award_points(target_user, community, pts, f'Manual: {reason}', done_by=request.user)
            messages.success(request, f'Points adjusted by {pts}.')
        return redirect(request.META.get('HTTP_REFERER', '/'))
    return redirect('portal_community', page_id=community.page_id)


@login_required
def create_badge(request, slug):
    community = get_object_or_404(Community, slug=slug)
    if not community.is_admin(request.user):
        messages.error(request, 'Admin access required.')
        return redirect('portal_community', page_id=community.page_id)

    badges = Badge.objects.filter(community=community).order_by('-created_at')
    members = community.memberships.filter(status='approved').select_related('user')

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'create':
            from .forms import BadgeArtworkForm
            artwork = BadgeArtworkForm(request.POST, request.FILES)
            if not artwork.is_valid():
                for errors in artwork.errors.values():
                    for error in errors:
                        messages.error(request, error)
                return redirect('create_badge', slug=slug)
            name = request.POST.get('name', '').strip()
            if name:
                Badge.objects.create(
                    community=community,
                    name=name,
                    description=request.POST.get('description', ''),
                    icon_image=artwork.cleaned_data.get('icon_image'),
                    image=artwork.cleaned_data.get('image'),
                    icon=request.POST.get('icon', '🏅'),
                    criteria_type=request.POST.get('criteria_type', 'manual'),
                    criteria_value=int(request.POST.get('criteria_value', 0) or 0),
                )
                messages.success(request, f'Badge "{name}" created.')
            return redirect('create_badge', slug=slug)
        elif action == 'award':
            badge_id = request.POST.get('badge_id')
            uid = request.POST.get('user_id')
            try:
                badge = Badge.objects.get(pk=badge_id, community=community)
                target_user = User.objects.get(pk=uid)
                MemberBadge.objects.get_or_create(
                    user=target_user, community=community, badge=badge,
                    defaults={'awarded_by': request.user}
                )
                messages.success(request, f'Badge awarded to {target_user.get_full_name()}.')
            except (Badge.DoesNotExist, User.DoesNotExist):
                messages.error(request, 'Invalid badge or user.')
            return redirect('create_badge', slug=slug)

    ctx = {
        'community': community,
        'badges': badges,
        'members': members,
        'criteria_choices': Badge.CRITERIA_CHOICES,
    }
    return render(request, 'portal/badges_admin.html', ctx)


@login_required
def award_badge_view(request, slug):
    """Simple POST endpoint to award a badge."""
    community = get_object_or_404(Community, slug=slug)
    if not community.is_admin(request.user):
        messages.error(request, 'Admin access required.')
        return redirect('portal_community', page_id=community.page_id)
    if request.method == 'POST':
        badge_id = request.POST.get('badge_id')
        uid = request.POST.get('user_id')
        try:
            badge = Badge.objects.get(pk=badge_id, community=community)
            target_user = User.objects.get(pk=uid)
            MemberBadge.objects.get_or_create(
                user=target_user, community=community, badge=badge,
                defaults={'awarded_by': request.user}
            )
            messages.success(request, 'Badge awarded.')
        except (Badge.DoesNotExist, User.DoesNotExist):
            messages.error(request, 'Invalid badge or user.')
    return redirect(request.META.get('HTTP_REFERER', '/'))


@login_required
def year_end_recognition(request, slug):
    community = get_object_or_404(Community, slug=slug)
    if not community.is_admin(request.user):
        messages.error(request, 'Admin access required.')
        return redirect('portal_community', page_id=community.page_id)

    year = int(request.GET.get('year', timezone.now().year))
    members_qs = community.memberships.filter(status='approved').select_related('user')

    # build stats per member
    member_stats = []
    for m in members_qs:
        u = m.user
        pts = MemberPoints.objects.filter(user=u, community=community).first()
        stats = {
            'user': u,
            'points': pts.total_points if pts else 0,
            'events': Participation.objects.filter(user=u, community=community, role='attendee', status='confirmed').count(),
            'volunteered': Participation.objects.filter(user=u, community=community, role='volunteer', status='confirmed').count(),
            'organised': Participation.objects.filter(user=u, community=community, role='organiser', status='confirmed').count(),
        }
        member_stats.append(stats)
    member_stats.sort(key=lambda x: x['points'], reverse=True)

    existing = Recognition.objects.filter(community=community, year=year)

    if request.method == 'POST':
        award_names = request.POST.getlist('award_name')
        user_ids = request.POST.getlist('user_id')
        descriptions = request.POST.getlist('description')
        for award, uid, desc in zip(award_names, user_ids, descriptions):
            award = award.strip()
            if award and uid:
                try:
                    u = User.objects.get(pk=uid)
                    Recognition.objects.get_or_create(
                        community=community, user=u, award_name=award, year=year,
                        defaults={'description': desc, 'awarded_by': request.user}
                    )
                except User.DoesNotExist:
                    pass
        messages.success(request, f'{year} recognitions saved.')
        return redirect('year_end_recognition', slug=slug)

    ctx = {
        'community': community,
        'year': year,
        'member_stats': member_stats[:20],
        'existing': existing,
        'years': range(timezone.now().year, timezone.now().year - 5, -1),
    }
    return render(request, 'portal/year_end_recognition.html', ctx)


def community_impact_page(request, slug):
    community = get_object_or_404(Community, slug=slug)
    year = int(request.GET.get('year', timezone.now().year))

    member_count = community.memberships.filter(status='approved').count()
    events_count = community.events.filter(is_active=True).count()
    activities_count = community.activities.filter(is_active=True).count()
    volunteer_count = Participation.objects.filter(community=community, role='volunteer', status='confirmed').count()
    total_participation = Participation.objects.filter(community=community, status='confirmed').count()
    causes_count = community.causes.filter(is_active=True).count()

    top_contributors = MemberPoints.objects.filter(community=community).select_related('user').order_by('-total_points')[:5]
    recognitions = Recognition.objects.filter(community=community, year=year).select_related('user')

    ctx = {
        'community': community,
        'year': year,
        'year_choices': (2026, 2025, 2024, 2023),
        'member_count': member_count,
        'events_count': events_count,
        'activities_count': activities_count,
        'volunteer_count': volunteer_count,
        'total_participation': total_participation,
        'causes_count': causes_count,
        'top_contributors': top_contributors,
        'recognitions': recognitions,
        'is_admin': community.is_admin(request.user),
    }
    return render(request, 'portal/community_impact.html', ctx)


@login_required
def point_config_admin(request, slug):
    community = get_object_or_404(Community, slug=slug)
    if not community.is_admin(request.user):
        messages.error(request, 'Admin access required.')
        return redirect('portal_community', page_id=community.page_id)

    # ensure all default configs exist
    DEFAULTS = [
        ('attend_event', 'Attend Event', 10),
        ('volunteer_event', 'Volunteer at Event', 20),
        ('organise_event', 'Organise Event', 50),
        ('complete_activity', 'Complete Activity', 30),
        ('volunteer_activity', 'Volunteer Activity', 20),
        ('support_cause', 'Support Cause', 10),
        ('upload_contribution', 'Upload Contribution', 5),
        ('financial_contribution', 'Financial Contribution', 10),
    ]
    for action, label, pts in DEFAULTS:
        PointConfig.objects.get_or_create(action=action, defaults={'label': label, 'points': pts})

    configs = PointConfig.objects.all().order_by('action')

    if request.method == 'POST':
        for cfg in configs:
            val = request.POST.get(f'points_{cfg.pk}')
            if val is not None:
                try:
                    cfg.points = max(0, int(val))
                    cfg.save()
                except ValueError:
                    pass
        messages.success(request, 'Point values updated.')
        return redirect('point_config_admin', slug=slug)

    ctx = {
        'community': community,
        'configs': configs,
    }
    return render(request, 'portal/point_config_admin.html', ctx)
