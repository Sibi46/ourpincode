from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.contrib import messages
from django.db import transaction
from django.http import Http404
import base64
from django.core.files.base import ContentFile
from .models import (FamilyStory, FamilyStoryLike, FamilyStoryComment,
                     StudentSuccess, StudentSuccessLike, StudentSuccessComment,
                     KidsPost, KidsPostLike, KidsPostComment,
                     ParentingPost, ParentingLike, ParentingComment,
                     GrandparentStory, GrandparentLike, GrandparentComment,
                     LocalHero, LocalHeroLike, LocalHeroComment,
                     CommunityEvent, EventRSVP, EventComment,
                     VolunteerActivity, VolunteerSignup, VolunteerComment,
                     BusinessStory, BusinessStoryLike, BusinessStoryComment,
                     HallOfFameEntry, HallOfFameVote, HallOfFameComment,
                     MarketplaceListing, ListingInterest, ListingComment,
                     WatchReport, WatchConfirm, WatchComment,
                     Notification, FamilyMember, FamilySetup,
                     FamilyFlick, FamilyPost)

MODULES = [
    {'slug': 'family',       'icon': '👨‍👩‍👧', 'name': 'Family Hub',     'desc': 'Family Stories · Parenting · Grandparents Archive',  'color': '#e11d48', 'soon': False},
    {'slug': 'school-corner', 'icon': '🏫', 'name': 'School & Kids',  'desc': 'School Corner · Student Success · Kids Corner',       'color': '#0a66c2', 'soon': False},
    {'slug': 'local-heroes',        'icon': '🦸', 'name': 'Local Heroes',           'desc': 'Celebrate unsung heroes in your community',           'color': '#dc2626', 'soon': False},
    {'slug': 'community-events',    'icon': '📅', 'name': 'Community Events',       'desc': 'Local gatherings, festivals & announcements',         'color': '#0891b2', 'soon': False},
    {'slug': 'volunteer',           'icon': '🤝', 'name': 'Volunteer Activities',   'desc': 'Blood donation, tree plantation & health camps',      'color': '#16a34a', 'soon': False},
    {'slug': 'business-stories',    'icon': '🏪', 'name': 'Business Stories',       'desc': 'Local business journeys — not ads, real stories',     'color': '#ea580c', 'soon': False},
    {'slug': 'community-watch',     'icon': '👁️', 'name': 'Community Watch',        'desc': 'Report, block & keep the community safe',             'color': '#374151', 'soon': False},
]

CAT_ICONS = {
    'birthday':    '🎂',
    'achievement': '🏅',
    'tradition':   '🎎',
    'celebration': '🎉',
    'vacation':    '✈️',
    'gardening':   '🌱',
    'other':       '📸',
}

CAT_LABELS = {
    'birthday':    'Birthday',
    'achievement': 'Achievement',
    'tradition':   'Tradition',
    'celebration': 'Celebration',
    'vacation':    'Vacation',
    'gardening':   'Gardening',
    'other':       'Other',
}


# ── COMMUNITY HUB ──────────────────────────────────────────────────────────────
def hub(request):
    return render(request, 'community/hub.html', {'modules': MODULES})


def module_page(request, slug):
    module = next((m for m in MODULES if m['slug'] == slug), None)
    if not module:
        from django.http import Http404
        raise Http404
    if slug == 'jobs':
        return redirect('/jobs/')
    if slug == 'family':
        return redirect('/community/family/')
    if slug == 'school-kids':
        return redirect('/community/school-kids/')
    if slug == 'family-stories':
        return redirect('/community/family/')
    if slug == 'parenting':
        return redirect('/community/family/?tab=parenting')
    if slug == 'grandparents-archive':
        return redirect('/community/family/?tab=grandparents')
    if slug == 'school-corner':
        return redirect('/community/school-kids/')
    if slug == 'student-success':
        return redirect('/community/school-kids/?tab=student')
    if slug == 'kids-corner':
        return redirect('/community/school-kids/?tab=kids')
    if slug == 'local-heroes':
        return redirect('/community/local-heroes/')
    if slug == 'community-events':
        return redirect('/community/events/')
    if slug == 'volunteer':
        return redirect('/community/volunteer/')
    if slug == 'business-stories':
        return redirect('/community/business-stories/')
    if slug == 'hall-of-fame':
        return redirect('/community/hall-of-fame/')
    if slug == 'marketplace':
        return redirect('/community/marketplace/')
    if slug == 'community-watch':
        return redirect('/community/community-watch/')
    if slug == 'notifications':
        return redirect('/community/notifications/')
    return render(request, 'community/coming_soon.html', {'module': module})


# ── FAMILY HUB ────────────────────────────────────────────────────────────────
@login_required
def family_setup_wizard(request):
    from django.contrib.auth.hashers import make_password
    from datetime import date
    import json

    setup, _ = FamilySetup.objects.get_or_create(user=request.user)
    step = request.POST.get('step') or request.GET.get('step', '1')
    errors = []

    if request.method == 'POST':
        # ── Step 1: Family Account (email + password) ──
        if step == '1':
            email    = request.POST.get('family_email', '').strip().lower()
            password = request.POST.get('family_password', '').strip()
            if not email:
                errors.append('Please enter a family email address.')
            elif FamilySetup.objects.filter(family_email=email).exclude(pk=setup.pk).exists():
                errors.append('This email is already used by another family account.')
            if not password:
                errors.append('Please enter a password.')
            if not errors:
                setup.house_name      = request.POST.get('house_name', '').strip()
                setup.family_email    = email
                setup.family_password = make_password(password)
                setup.save()
                return redirect('/community/family/setup/?step=2')

        # ── Step 2: Gender ──
        elif step == '2':
            gender = request.POST.get('gender', '')
            if not gender:
                errors.append('Please select your gender.')
            else:
                setup.gender = gender
                setup.save()
                return redirect('/community/family/setup/?step=3')

        # ── Step 3: Marital Status ──
        elif step == '3':
            ms = request.POST.get('marital_status', '')
            if not ms:
                errors.append('Please select your marital status.')
            else:
                setup.marital_status = ms
                setup.save()
                return redirect('/community/family/setup/?step=4')

        # ── Step 4: Self Details + Your Father / Mother / Siblings ──
        elif step == '4':
            setup.self_full_name  = request.POST.get('self_full_name', '').strip()
            setup.self_dob        = request.POST.get('self_dob') or None
            setup.self_village    = request.POST.get('self_village', '').strip()
            setup.self_occupation = request.POST.get('self_occupation', '').strip()
            if 'self_photo' in request.FILES:
                setup.self_photo = request.FILES['self_photo']
            setup.save()

            # Father (your side)
            FamilyMember.objects.filter(creator=request.user, member_type='father', side='husband').delete()
            father_name = request.POST.get('father_name', '').strip()
            if father_name:
                f_status = request.POST.get('father_status', 'living')
                f_death  = request.POST.get('father_death_date') or None
                fm = FamilyMember(
                    creator=request.user, member_type='father', side='husband',
                    name=father_name,
                    dob=request.POST.get('father_dob') or None,
                    village=request.POST.get('father_village', '').strip(),
                    occupation=request.POST.get('father_occupation', '').strip(),
                    status=f_status if f_status in ('living','passed') else 'living',
                    death_date=f_death if f_status == 'passed' else None,
                )
                fp_data = request.POST.get('father_photo_data', '').strip()
                if fp_data and fp_data.startswith('data:image'):
                    fmt, b64 = fp_data.split(';base64,', 1)
                    ext = fmt.split('/')[-1].replace('jpeg','jpg')
                    fm.photo = ContentFile(base64.b64decode(b64), name=f'father_{request.user.pk}.{ext}')
                fm.save()

            # Mother (your side)
            FamilyMember.objects.filter(creator=request.user, member_type='mother', side='husband').delete()
            mother_name = request.POST.get('mother_name', '').strip()
            if mother_name:
                m_status = request.POST.get('mother_status', 'living')
                m_death  = request.POST.get('mother_death_date') or None
                mm = FamilyMember(
                    creator=request.user, member_type='mother', side='husband',
                    name=mother_name,
                    dob=request.POST.get('mother_dob') or None,
                    village=request.POST.get('mother_village', '').strip(),
                    occupation=request.POST.get('mother_occupation', '').strip(),
                    status=m_status if m_status in ('living','passed') else 'living',
                    death_date=m_death if m_status == 'passed' else None,
                )
                mp_data = request.POST.get('mother_photo_data', '').strip()
                if mp_data and mp_data.startswith('data:image'):
                    fmt, b64 = mp_data.split(';base64,', 1)
                    ext = fmt.split('/')[-1].replace('jpeg','jpg')
                    mm.photo = ContentFile(base64.b64decode(b64), name=f'mother_{request.user.pk}.{ext}')
                mm.save()

            if setup.marital_status == 'married':
                return redirect('/community/family/setup/?step=5')
            return redirect('/community/family/setup/?step=6')

        # ── Step 5: Partner Details + Partner's Father / Mother / Siblings ──
        elif step == '5':
            setup.partner_full_name  = request.POST.get('partner_full_name', '').strip()
            setup.partner_gender     = request.POST.get('partner_gender', '').strip()
            setup.partner_dob        = request.POST.get('partner_dob') or None
            setup.partner_village    = request.POST.get('partner_village', '').strip()
            setup.partner_occupation = request.POST.get('partner_occupation', '').strip()
            p_email = request.POST.get('partner_email', '').strip().lower()
            p_pwd   = request.POST.get('partner_password', '').strip()
            if p_email:
                setup.partner_email = p_email
            if p_pwd:
                setup.partner_password = make_password(p_pwd)
            if 'partner_photo' in request.FILES:
                setup.partner_photo = request.FILES['partner_photo']
            setup.save()

            # Father (partner's side)
            FamilyMember.objects.filter(creator=request.user, member_type='father', side='wife').delete()
            pf_name = request.POST.get('p_father_name', '').strip()
            if pf_name:
                FamilyMember.objects.create(
                    creator=request.user, member_type='father', side='wife',
                    name=pf_name,
                    dob=request.POST.get('p_father_dob') or None,
                    village=request.POST.get('p_father_village', '').strip(),
                    occupation=request.POST.get('p_father_occupation', '').strip(),
                )

            # Mother (partner's side)
            FamilyMember.objects.filter(creator=request.user, member_type='mother', side='wife').delete()
            pm_name = request.POST.get('p_mother_name', '').strip()
            if pm_name:
                FamilyMember.objects.create(
                    creator=request.user, member_type='mother', side='wife',
                    name=pm_name,
                    dob=request.POST.get('p_mother_dob') or None,
                    village=request.POST.get('p_mother_village', '').strip(),
                    occupation=request.POST.get('p_mother_occupation', '').strip(),
                )

            return redirect('/community/family/setup/?step=6')

        # ── Step 6: Children ──
        elif step == '6':
            FamilyMember.objects.filter(
                creator=request.user,
                member_type__in=['son', 'daughter']
            ).delete()

            names     = request.POST.getlist('child_name')
            dobs      = request.POST.getlist('child_dob')
            genders   = request.POST.getlist('child_gender')
            emails    = request.POST.getlist('child_email')
            passwords = request.POST.getlist('child_password')

            today = date.today()
            for i, name in enumerate(names):
                name = name.strip()
                if not name:
                    continue
                dob_str = dobs[i] if i < len(dobs) else ''
                gender  = genders[i] if i < len(genders) else 'male'
                email_c = emails[i].strip().lower() if i < len(emails) else ''
                pwd     = passwords[i].strip() if i < len(passwords) else ''

                dob_val = None
                age_val = None
                if dob_str:
                    try:
                        from datetime import datetime
                        dob_val = datetime.strptime(dob_str, '%Y-%m-%d').date()
                        age_val = max(0, min(150, (today - dob_val).days // 365))
                    except Exception:
                        pass

                mtype = 'son' if gender == 'male' else 'daughter'
                member = FamilyMember.objects.create(
                    creator     = request.user,
                    member_type = mtype,
                    side        = 'husband',
                    name        = name,
                    dob         = dob_val,
                    age         = age_val,
                    child_email = email_c,
                )
                photos = request.FILES.getlist('child_photo')
                if i < len(photos) and photos[i]:
                    member.photo = photos[i]
                    member.save()

                if age_val and age_val >= 18 and email_c and pwd:
                    from django.contrib.auth import get_user_model
                    User = get_user_model()
                    child_user, created = User.objects.get_or_create(
                        email=email_c,
                        defaults={
                            'username': email_c.split('@')[0] + '_fam',
                            'user_type': 'family_child',
                        }
                    )
                    if created:
                        child_user.set_password(pwd)
                        child_user.save()
                    member.child_password    = make_password(pwd)
                    member.child_linked_user = child_user
                    member.save()

            return redirect('/community/family/setup/?step=7')

        # ── Step 7: Pets ──
        elif step == '7':
            FamilyMember.objects.filter(creator=request.user, member_type='pet').delete()
            names   = request.POST.getlist('pet_name')
            species = request.POST.getlist('pet_species')
            breeds  = request.POST.getlist('pet_breed')
            for i, name in enumerate(names):
                name = name.strip()
                if not name:
                    continue
                pet = FamilyMember.objects.create(
                    creator     = request.user,
                    member_type = 'pet',
                    side        = 'husband',
                    name        = name,
                    species     = species[i] if i < len(species) else '',
                    breed       = breeds[i] if i < len(breeds) else '',
                )
                photos = request.FILES.getlist('pet_photo')
                if i < len(photos) and photos[i]:
                    pet.photo = photos[i]
                    pet.save()
            setup.setup_done = True
            setup.save()
            return redirect('/community/family/?setup_done=1')

        # ── Step 8: Grandparents (optional, accessed from hub) ──
        elif step == '8':
            FamilyMember.objects.filter(
                creator=request.user,
                member_type__in=['grandfather', 'grandmother']
            ).delete()

            gp_fields = [
                ('grandfather', 'gf_name', 'gf_dob', 'gf_village', 'gf_occupation', 'husband'),
                ('grandmother', 'gm_name', 'gm_dob', 'gm_village', 'gm_occupation', 'husband'),
            ]
            if setup.marital_status == 'married':
                gp_fields += [
                    ('grandfather', 'wgf_name', 'wgf_dob', 'wgf_village', 'wgf_occupation', 'wife'),
                    ('grandmother', 'wgm_name', 'wgm_dob', 'wgm_village', 'wgm_occupation', 'wife'),
                ]
            for mtype, nf, df, vf, of, side in gp_fields:
                name = request.POST.get(nf, '').strip()
                if not name:
                    continue
                dob_str = request.POST.get(df, '')
                dob_val = None
                if dob_str:
                    try:
                        from datetime import datetime
                        dob_val = datetime.strptime(dob_str, '%Y-%m-%d').date()
                    except Exception:
                        pass
                FamilyMember.objects.create(
                    creator=request.user, member_type=mtype, side=side, name=name,
                    dob=dob_val, village=request.POST.get(vf,'').strip(),
                    occupation=request.POST.get(of,'').strip(),
                )

            setup.setup_done = True
            setup.save()
            return redirect('/community/family/?setup_done=1')

    # Existing members for pre-fill
    children = FamilyMember.objects.filter(
        creator=request.user, member_type__in=['son', 'daughter']
    ).order_by('created_at')
    pets = FamilyMember.objects.filter(
        creator=request.user, member_type='pet'
    ).order_by('created_at')
    grandparents = FamilyMember.objects.filter(
        creator=request.user, member_type__in=['grandfather', 'grandmother']
    ).order_by('side', 'member_type')
    my_father   = FamilyMember.objects.filter(creator=request.user, member_type='father',  side='husband').first()
    my_mother   = FamilyMember.objects.filter(creator=request.user, member_type='mother',  side='husband').first()
    my_siblings = FamilyMember.objects.filter(creator=request.user, member_type__in=['brother','sister'], side='husband').order_by('created_at')
    p_father    = FamilyMember.objects.filter(creator=request.user, member_type='father',  side='wife').first()
    p_mother    = FamilyMember.objects.filter(creator=request.user, member_type='mother',  side='wife').first()
    p_siblings  = FamilyMember.objects.filter(creator=request.user, member_type__in=['brother','sister'], side='wife').order_by('created_at')

    step_int = int(step) if str(step).isdigit() else 1
    steps_list = [
        {'num': '1', 'lbl': 'Account'},
        {'num': '2', 'lbl': 'Gender'},
        {'num': '3', 'lbl': 'Status'},
        {'num': '4', 'lbl': 'You & Family'},
        {'num': '5', 'lbl': 'Partner'},
        {'num': '6', 'lbl': 'Children'},
        {'num': '7', 'lbl': 'Pets'},
    ]
    back_step = '5' if (setup and setup.marital_status == 'married') else '4'
    return render(request, 'community/family_setup_wizard.html', {
        'setup': setup, 'step': step, 'step_int': step_int,
        'errors': errors, 'steps_list': steps_list,
        'children': children, 'pets': pets, 'grandparents': grandparents,
        'my_father': my_father, 'my_mother': my_mother, 'my_siblings': my_siblings,
        'p_father': p_father, 'p_mother': p_mother, 'p_siblings': p_siblings,
        'back_step': back_step,
    })


def family_hub(request):
    setup = None
    if request.user.is_authenticated:
        # Child 18+ account — resolve to parent's FamilySetup
        if getattr(request.user, 'user_type', '') == 'family_child':
            child_member = FamilyMember.objects.filter(
                child_linked_user=request.user
            ).select_related('creator__family_setup').first()
            if child_member and hasattr(child_member.creator, 'family_setup'):
                setup = child_member.creator.family_setup
            else:
                setup = None
        else:
            setup, _ = FamilySetup.objects.get_or_create(user=request.user)
            # redirect to wizard if not done
            if not setup.setup_done and request.method == 'GET':
                return redirect('/community/family/setup/?step=1')

    ROWS = [
        ('👴', 'Grandfather', 'grandfather_count'),
        ('👵', 'Grandmother', 'grandmother_count'),
        ('👨', 'Father',      'father_count'),
        ('👩', 'Mother',      'mother_count'),
        ('👦', 'Son',         'son_count'),
        ('👧', 'Daughter',    'daughter_count'),
        ('🧔', 'Uncle',       'uncle_count'),
        ('👩‍🦳', 'Aunt',      'aunt_count'),
        ('🧑', 'Cousin',      'cousin_count'),
        ('👱', 'Brother',     'brother_count'),
        ('👱‍♀️', 'Sister',  'sister_count'),
        ('🐾', 'Pet',         'pet_count'),
    ]
    TYPE_ICON = {
        'grandfather':'👴','grandmother':'👵','father':'👨','mother':'👩',
        'son':'👦','daughter':'👧','uncle':'🧔','aunt':'👩‍🦳','cousin':'🧑',
        'brother':'👱','sister':'👱‍♀️','pet':'🐾',
    }
    FIELD_TO_TYPE = {
        'grandfather_count':'grandfather','grandmother_count':'grandmother',
        'father_count':'father','mother_count':'mother','son_count':'son',
        'daughter_count':'daughter','uncle_count':'uncle','aunt_count':'aunt',
        'cousin_count':'cousin','brother_count':'brother','sister_count':'sister',
        'pet_count':'pet',
    }
    setup_rows = [(icon, label, field, getattr(setup, field, 0) if setup else 0)
                  for icon, label, field in ROWS]
    active_tabs = []
    if setup:
        for icon, label, field in ROWS:
            cnt = getattr(setup, field, 0)
            if cnt > 0:
                mtype = FIELD_TO_TYPE[field]
                active_tabs.append((mtype, label, icon, cnt))

    # Build husband sections (with actual members)
    HUSBAND_TYPES = [
        ('grandfather','Grandfather','👴','grandfather_count'),
        ('grandmother','Grandmother','👵','grandmother_count'),
        ('father',     'Father',     '👨','father_count'),
        ('mother',     'Mother',     '👩','mother_count'),
        ('brother',    'Brother',    '👱','brother_count'),
        ('sister',     'Sister',     '👱‍♀️','sister_count'),
        ('uncle',      'Uncle',      '🧔','uncle_count'),
        ('aunt',       'Aunt',       '👩‍🦳','aunt_count'),
        ('cousin',     'Cousin',     '🧑','cousin_count'),
        ('son',        'Son',        '👦','son_count'),
        ('daughter',   'Daughter',   '👧','daughter_count'),
        ('pet',        'Pet',        '🐾','pet_count'),
    ]
    WIFE_TYPES = [
        ('grandfather','Grandfather','👴','w_grandfather_count'),
        ('grandmother','Grandmother','👵','w_grandmother_count'),
        ('father',     'Father',     '👨','w_father_count'),
        ('mother',     'Mother',     '👩','w_mother_count'),
        ('brother',    'Brother',    '👱','w_brother_count'),
        ('sister',     'Sister',     '👱‍♀️','w_sister_count'),
        ('uncle',      'Uncle',      '🧔','w_uncle_count'),
        ('aunt',       'Aunt',       '👩‍🦳','w_aunt_count'),
        ('cousin',     'Cousin',     '🧑','w_cousin_count'),
    ]

    # Build combined row-aligned sections for split view
    is_married = setup and setup.marital_status == 'married'
    combined_rows = []
    if setup and request.user.is_authenticated:
        all_members = list(FamilyMember.objects.filter(creator=request.user))
        h_map = {}
        w_map = {}
        for m in all_members:
            if m.side == 'wife':
                w_map.setdefault(m.member_type, []).append(m)
            else:
                h_map.setdefault(m.member_type, []).append(m)
        # Build one row per type — use actual member records (not count fields)
        seen = []
        for mtype, label, icon, field in HUSBAND_TYPES:
            h_members = h_map.get(mtype, [])
            w_members = w_map.get(mtype, []) if is_married else []
            if h_members or w_members:
                combined_rows.append((mtype, label, icon, len(h_members), h_members, len(w_members), w_members))
                seen.append(mtype)
        # Wife-only types not covered above
        if is_married:
            for mtype, label, icon, field in WIFE_TYPES:
                if mtype not in seen:
                    w_members = w_map.get(mtype, [])
                    if w_members:
                        combined_rows.append((mtype, label, icon, 0, [], len(w_members), w_members))

    # Family count
    core_count = 0
    total_count = 0
    if setup and setup.setup_done:
        core_count = 1  # me
        if is_married:
            core_count += 1  # partner
        total_count = core_count + FamilyMember.objects.filter(creator=request.user).count()

    my_father = FamilyMember.objects.filter(creator=request.user, member_type='father', side='husband').first() if request.user.is_authenticated else None
    my_mother = FamilyMember.objects.filter(creator=request.user, member_type='mother', side='husband').first() if request.user.is_authenticated else None
    p_father  = FamilyMember.objects.filter(creator=request.user, member_type='father', side='wife').first()  if request.user.is_authenticated else None
    p_mother  = FamilyMember.objects.filter(creator=request.user, member_type='mother', side='wife').first()  if request.user.is_authenticated else None
    friends   = []
    # Family directory — all members ordered by type
    directory_members = []
    if request.user.is_authenticated and setup and setup.setup_done:
        directory_members = list(FamilyMember.objects.filter(creator=request.user).order_by('member_type', 'name'))
    # Determine the family owner (child accounts resolve to parent)
    _family_owner = request.user
    if request.user.is_authenticated and getattr(request.user, 'user_type', '') == 'family_child':
        _cm = FamilyMember.objects.filter(child_linked_user=request.user).first()
        if _cm:
            _family_owner = _cm.creator
    _MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
    flick_groups = []
    if request.user.is_authenticated:
        raw_flicks = FamilyFlick.objects.filter(creator=_family_owner).order_by('-event_date', '-created_at')
        current_ym = None
        current_group = None
        last_year = None
        for f in raw_flicks:
            d = f.event_date or f.created_at.date()
            ym = (d.year, d.month)
            if ym != current_ym:
                if current_group:
                    flick_groups.append(current_group)
                current_group = {
                    'year': d.year,
                    'show_year': d.year != last_year,
                    'month_name': _MONTHS[d.month - 1],
                    'count': 0,
                    'items': [],
                }
                last_year = d.year
                current_ym = ym
            current_group['items'].append(f)
            current_group['count'] += 1
        if current_group:
            flick_groups.append(current_group)

    posts     = FamilyPost.objects.filter(creator=_family_owner) if request.user.is_authenticated else []

    relatives_exist = FamilyMember.objects.filter(
        creator=request.user,
        member_type__in=['uncle','aunt','cousin','brother','sister','friend','colleague']
    ).exists() if request.user.is_authenticated else False

    # ── BIRTHDAY CARDS ────────────────────────────────────────────────────────
    birthday_cards = []
    if request.user.is_authenticated and setup:
        from datetime import date as _date, timedelta
        import calendar as _cal

        def _bday_match(dob, target):
            if dob.month == 2 and dob.day == 29:
                if not _cal.isleap(target.year):
                    return target.month == 2 and target.day == 28
            return dob.month == target.month and dob.day == target.day

        _today   = _date.today()
        _in_two  = _today + timedelta(days=2)

        def _days_until(dob):
            this_year = _date(year=_today.year, month=dob.month if not (dob.month == 2 and dob.day == 29 and not _cal.isleap(_today.year)) else 2,
                              day=dob.day if not (dob.month == 2 and dob.day == 29 and not _cal.isleap(_today.year)) else 28)
            if this_year < _today:
                this_year = this_year.replace(year=_today.year + 1)
            return (this_year - _today).days

        # self_dob
        if setup.self_dob:
            days = _days_until(setup.self_dob)
            if days in (0, 2):
                birthday_cards.append({
                    'name': setup.self_full_name or request.user.get_full_name() or 'You',
                    'relation': 'You',
                    'days': days,
                    'is_today': days == 0,
                    'member_pk': None,
                    'photo': setup.self_photo.url if setup.self_photo else None,
                })

        # partner_dob
        if setup.partner_dob and setup.partner_full_name:
            days = _days_until(setup.partner_dob)
            if days in (0, 2):
                birthday_cards.append({
                    'name': setup.partner_full_name,
                    'relation': setup.partner_gender.title() if setup.partner_gender else 'Partner',
                    'days': days,
                    'is_today': days == 0,
                    'member_pk': None,
                    'photo': setup.partner_photo.url if setup.partner_photo else None,
                })

        # FamilyMember DOBs
        for _m in FamilyMember.objects.filter(creator=request.user, status='living', dob__isnull=False).only('pk', 'name', 'dob', 'member_type', 'photo'):
            days = _days_until(_m.dob)
            if days in (0, 2):
                birthday_cards.append({
                    'name': _m.name,
                    'relation': _m.get_member_type_display(),
                    'days': days,
                    'is_today': days == 0,
                    'member_pk': _m.pk,
                    'photo': _m.photo.url if _m.photo else None,
                })

    return render(request, 'community/family_hub.html', {
        'setup':           setup,
        'setup_rows':      setup_rows,
        'active_tabs':     active_tabs,
        'combined_rows':   combined_rows,
        'is_married':      is_married,
        'core_count':      core_count,
        'total_count':     total_count,
        'my_father':       my_father,
        'my_mother':       my_mother,
        'p_father':        p_father,
        'p_mother':        p_mother,
        'friends':         friends,
        'flick_groups':    flick_groups,
        'posts':           posts,
        'relatives_exist': relatives_exist,
        'birthday_cards':  birthday_cards,
        'directory_members': directory_members,
    })


@login_required
def family_delete(request):
    if request.method == 'POST':
        try:
            setup = FamilySetup.objects.get(user=request.user)
            # Delete child linked users created for 18+ children
            for member in FamilyMember.objects.filter(creator=request.user, child_linked_user__isnull=False):
                member.child_linked_user.delete()
            FamilyMember.objects.filter(creator=request.user).delete()
            setup.delete()
            messages.success(request, 'Family account deleted successfully.')
        except FamilySetup.DoesNotExist:
            pass
        return redirect('/community/family/')
    return render(request, 'community/family_delete_confirm.html')


def family_login(request):
    """Separate login page for family accounts."""
    from django.contrib.auth import authenticate, login as auth_login
    if request.method == 'POST':
        email    = request.POST.get('family_email', '').strip()
        password = request.POST.get('family_password', '').strip()
        user = authenticate(request, username=email, password=password,
                            backend='jobs.backends.FamilyAccountBackend')
        if user:
            auth_login(request, user, backend='jobs.backends.FamilyAccountBackend')
            return redirect('/community/family/')
        messages.error(request, 'Invalid family email or password.')
    return render(request, 'community/family_login.html')


@login_required
def family_member_create(request):
    if request.method == 'POST':
        m = FamilyMember(
            creator     = request.user,
            member_type = request.POST.get('member_type', 'other'),
            side        = request.POST.get('side', 'husband'),
            name        = request.POST.get('name', '').strip(),
            why         = request.POST.get('why', '').strip(),
            description = request.POST.get('description', '').strip(),
            about       = request.POST.get('about', '').strip(),
            village     = request.POST.get('village', '').strip(),
            house_name  = request.POST.get('house_name', '').strip(),
            occupation  = request.POST.get('occupation', '').strip(),
            education   = request.POST.get('education', '').strip(),
            gender      = request.POST.get('gender', '').strip(),
            phone       = request.POST.get('phone', '').strip(),
            status      = request.POST.get('status', 'living'),
            species     = request.POST.get('species', '').strip(),
            breed       = request.POST.get('breed', '').strip(),
        )
        if request.POST.get('age'):
            try:
                _age = int(request.POST['age'])
                if 0 <= _age <= 150:
                    m.age = _age
            except ValueError:
                pass
        if request.POST.get('dob'):
            from datetime import date
            try:
                parts = request.POST['dob'].split('-')
                m.dob = date(int(parts[0]), int(parts[1]), int(parts[2]))
            except Exception: pass
        if request.POST.get('death_date') and m.status == 'passed':
            from datetime import date
            try:
                parts = request.POST['death_date'].split('-')
                m.death_date = date(int(parts[0]), int(parts[1]), int(parts[2]))
            except Exception: pass
        if request.FILES.get('photo'):
            m.photo = request.FILES['photo']
        if m.name:
            m.save()
            return redirect(f'/community/family/member/{m.pk}/')
    return render(request, 'community/family_member_create.html', {
        'type_choices': FamilyMember.TYPE_CHOICES,
    })


@login_required
@require_POST
def family_quick_add(request):
    name = request.POST.get('name', '').strip()
    member_type = request.POST.get('member_type', 'other')
    side = request.POST.get('side', 'husband')
    VALID_TYPES = ['grandfather', 'grandmother', 'uncle', 'aunt', 'brother', 'sister', 'cousin', 'friend', 'colleague', 'other']
    if not name:
        return JsonResponse({'ok': False, 'error': 'Name required'})
    if member_type not in VALID_TYPES:
        member_type = 'other'
    status = request.POST.get('status', 'living')
    if status not in ('living', 'passed'):
        status = 'living'
    occupation = request.POST.get('occupation', '').strip()
    village = request.POST.get('village', '').strip()
    phone = request.POST.get('phone', '').strip()
    m = FamilyMember(
        creator=request.user, member_type=member_type, side=side, name=name,
        status=status, occupation=occupation, village=village, phone=phone,
    )
    if request.POST.get('dob'):
        from datetime import date
        try:
            parts = request.POST['dob'].split('-')
            m.dob = date(int(parts[0]), int(parts[1]), int(parts[2]))
        except Exception: pass
    if status == 'passed' and request.POST.get('death_date'):
        from datetime import date
        try:
            parts = request.POST['death_date'].split('-')
            m.death_date = date(int(parts[0]), int(parts[1]), int(parts[2]))
        except Exception: pass
    if request.FILES.get('photo'):
        m.photo = request.FILES['photo']
    m.save()
    return JsonResponse({'ok': True, 'pk': m.pk, 'name': name, 'member_type': member_type, 'side': side, 'occupation': occupation, 'village': village})


@login_required
def family_member_detail(request, pk):
    member = get_object_or_404(FamilyMember, pk=pk)
    setup = get_object_or_404(FamilySetup, user=member.creator)
    if not _can_view_family(request.user, setup):
        raise Http404
    return render(request, 'community/family_member_detail.html', {'member': member})


def _can_view_family(user, setup):
    return setup.is_public or (user.is_authenticated and (
        user.pk == setup.user_id or FamilyMember.objects.filter(
            creator_id=setup.user_id, child_linked_user=user).exists()))


@login_required
@require_POST
def family_visibility(request):
    setup = get_object_or_404(FamilySetup, user=request.user)
    visibility = request.POST.get('visibility')
    if visibility not in ('public', 'private'):
        return JsonResponse({'error': 'Invalid visibility'}, status=400)
    setup.is_public = visibility == 'public'
    setup.save(update_fields=['is_public'])
    messages.success(request, 'Family profile visibility saved.')
    return redirect('family_hub')


@login_required
def family_profile(request, user_id):
    setup = get_object_or_404(FamilySetup, user_id=user_id, setup_done=True)
    if not _can_view_family(request.user, setup):
        raise Http404
    return render(request, 'community/family_profile.html', {
        'setup': setup, 'members': FamilyMember.objects.filter(creator_id=user_id),
    })


@login_required
def family_member_edit(request, pk):
    member = get_object_or_404(FamilyMember, pk=pk, creator=request.user)
    if request.method == 'POST':
        member.member_type = request.POST.get('member_type', member.member_type)
        member.name        = request.POST.get('name', '').strip() or member.name
        member.about       = request.POST.get('about', '').strip()
        member.village     = request.POST.get('village', '').strip()
        member.house_name  = request.POST.get('house_name', '').strip()
        member.gender      = request.POST.get('gender', '').strip()
        member.occupation  = request.POST.get('occupation', '').strip()
        member.education   = request.POST.get('education', '').strip()
        member.phone       = request.POST.get('phone', '').strip()
        member.status      = request.POST.get('status', 'living')
        member.species     = request.POST.get('species', '').strip()
        member.breed       = request.POST.get('breed', '').strip()
        if request.POST.get('age'):
            try:
                _age = int(request.POST['age'])
                if 0 <= _age <= 150:
                    member.age = _age
            except ValueError:
                pass
        if request.POST.get('dob'):
            from datetime import date
            try:
                parts = request.POST['dob'].split('-')
                member.dob = date(int(parts[0]), int(parts[1]), int(parts[2]))
            except Exception: pass
        if request.POST.get('death_date') and member.status == 'passed':
            from datetime import date
            try:
                parts = request.POST['death_date'].split('-')
                member.death_date = date(int(parts[0]), int(parts[1]), int(parts[2]))
            except Exception: pass
        if request.FILES.get('photo'):
            member.photo = request.FILES['photo']
        member.save()
        return redirect(f'/community/family/member/{member.pk}/')
    return render(request, 'community/family_member_create.html', {
        'type_choices': FamilyMember.TYPE_CHOICES,
        'member': member,
        'editing': True,
    })


def family_member_verify(request, pk):
    """Public page — no login needed. Shows 'Are you X's Uncle?' confirmation."""
    member = get_object_or_404(FamilyMember, pk=pk)
    setup  = getattr(member.creator, 'familysetup', None)
    self_name    = (setup.self_full_name    if setup and setup.self_full_name    else member.creator.get_full_name() or member.creator.username)
    partner_name = (setup.partner_full_name if setup and setup.partner_full_name else 'Partner')
    # side='husband' means my (self) side; side='wife' means partner's side
    owner_name = partner_name if member.side == 'wife' else self_name
    return render(request, 'community/family_member_verify.html', {
        'member':       member,
        'owner_name':   owner_name,
        'self_name':    self_name,
        'partner_name': partner_name,
    })


@login_required
@require_POST
def family_flick_add(request):
    from datetime import date as _date
    photo = request.FILES.get('photo')
    video = request.FILES.get('video')
    if not photo and not video:
        return JsonResponse({'ok': False, 'error': 'Choose a photo or video'})
    caption = request.POST.get('caption', '').strip()
    event_date = None
    raw_date = request.POST.get('event_date', '').strip()
    if raw_date:
        try:
            event_date = _date.fromisoformat(raw_date)
        except ValueError:
            pass
    flick = FamilyFlick(creator=request.user, caption=caption, event_date=event_date)
    if photo:
        flick.photo = photo
    if video:
        flick.video = video
    flick.save()
    media_url = flick.photo.url if flick.photo else flick.video.url
    display_date = (event_date or flick.created_at.date()).isoformat()
    return JsonResponse({'ok': True, 'pk': flick.pk, 'url': media_url,
                         'is_video': bool(video), 'caption': caption,
                         'event_date': display_date})


@login_required
@require_POST
def family_post_add(request):
    text = request.POST.get('text', '').strip()
    if not text:
        return JsonResponse({'ok': False, 'error': 'Text required'})
    post = FamilyPost(creator=request.user, text=text)
    if request.FILES.get('photo'):
        post.photo = request.FILES['photo']
    post.save()
    return JsonResponse({'ok': True, 'pk': post.pk, 'text': text,
                         'photo_url': post.photo.url if post.photo else ''})


# ── SCHOOL & KIDS HUB ──────────────────────────────────────────────────────────
def school_kids_hub(request):
    tab = request.GET.get('tab', 'school')

    # School Corner
    schools = School.objects.all().order_by('-created_at')

    # Student Success
    ss_stories = StudentSuccess.objects.filter(is_active=True).select_related('user')
    ss_liked   = set()
    if request.user.is_authenticated:
        ss_liked = set(StudentSuccessLike.objects.filter(
            user=request.user).values_list('success_id', flat=True))

    # Kids Corner
    kids_posts = KidsPost.objects.filter(is_active=True).select_related('posted_by')
    kids_liked = set()
    if request.user.is_authenticated:
        kids_liked = set(KidsPostLike.objects.filter(
            user=request.user).values_list('post_id', flat=True))

    return render(request, 'community/school_kids_hub.html', {
        'tab':          tab,
        'schools':      schools,
        'ss_stories':   ss_stories,
        'ss_liked':     ss_liked,
        'ss_cat_icons': SS_CAT_ICONS,
        'kids_posts':   kids_posts,
        'kids_liked':   kids_liked,
        'kids_type_icons': KIDS_TYPE_ICONS,
        'kids_types':   KidsPost.TYPE_CHOICES,
    })


# ── FAMILY STORIES ─────────────────────────────────────────────────────────────
def family_stories_feed(request):
    cat = request.GET.get('cat', '')
    stories = FamilyStory.objects.filter(is_active=True).select_related('user')
    if cat:
        stories = stories.filter(category=cat)

    liked_ids = set()
    if request.user.is_authenticated:
        liked_ids = set(FamilyStoryLike.objects.filter(user=request.user).values_list('story_id', flat=True))

    return render(request, 'community/family_stories.html', {
        'stories':   stories,
        'liked_ids': liked_ids,
        'active_cat': cat,
        'cat_icons': CAT_ICONS,
        'cat_labels': CAT_LABELS,
    })


@login_required
def family_story_post(request):
    if request.method == 'POST':
        title    = request.POST.get('title', '').strip()
        content  = request.POST.get('content', '').strip()
        category = request.POST.get('category', 'other')
        image    = request.FILES.get('image')
        pincode  = getattr(request.user, 'pincode', '') or ''

        if title and content:
            FamilyStory.objects.create(
                user=request.user,
                title=title,
                content=content,
                category=category,
                image=image,
                pincode=pincode,
            )
            messages.success(request, 'Your story has been shared!')
            return redirect('/community/family-stories/')

    return render(request, 'community/family_story_post.html', {
        'cat_icons':  CAT_ICONS,
        'cat_labels': CAT_LABELS,
    })


def family_story_detail(request, pk):
    story = get_object_or_404(FamilyStory, pk=pk, is_active=True)
    comments = story.comments.select_related('user').all()
    liked = (
        request.user.is_authenticated and
        FamilyStoryLike.objects.filter(user=request.user, story=story).exists()
    )
    if request.method == 'POST' and request.user.is_authenticated:
        text = request.POST.get('comment', '').strip()
        if text:
            FamilyStoryComment.objects.create(user=request.user, story=story, text=text)
        return redirect(f'/community/family-stories/{pk}/')

    return render(request, 'community/family_story_detail.html', {
        'story':    story,
        'comments': comments,
        'liked':    liked,
        'cat_icons': CAT_ICONS,
    })


@login_required
def family_story_like(request, pk):
    story = get_object_or_404(FamilyStory, pk=pk)
    like, created = FamilyStoryLike.objects.get_or_create(user=request.user, story=story)
    if not created:
        like.delete()
        liked = False
    else:
        liked = True
    return JsonResponse({'liked': liked, 'count': story.like_count()})


@login_required
def family_story_delete(request, pk):
    story = get_object_or_404(FamilyStory, pk=pk, user=request.user)
    story.delete()
    return redirect('/community/family-stories/')


# ── SCHOOL CORNER ──────────────────────────────────────────────────────────────
from .models import School, SchoolPost, SchoolPostLike, SchoolPostComment, SchoolFollow, SchoolAdmin

POST_TYPE_ICONS = {
    'annual_day':   '🎭',
    'sports_day':   '⚽',
    'science_fair': '🔬',
    'admission':    '📋',
    'achievement':  '🏆',
    'event':        '📅',
    'announcement': '📢',
    'other':        '📌',
}


def school_list(request):
    q       = request.GET.get('q', '').strip()
    pincode = request.GET.get('pin', '').strip()
    schools = School.objects.all()
    if q:
        schools = schools.filter(name__icontains=q)
    if pincode:
        schools = schools.filter(pincode=pincode)
    return render(request, 'community/school_list.html', {
        'schools': schools, 'q': q, 'pincode': pincode,
    })


def school_detail(request, pk):
    school   = get_object_or_404(School, pk=pk)
    posts    = school.posts.filter(is_active=True)
    post_type = request.GET.get('type', '')
    if post_type:
        posts = posts.filter(post_type=post_type)

    following = (
        request.user.is_authenticated and
        SchoolFollow.objects.filter(user=request.user, school=school).exists()
    )
    liked_ids = set()
    if request.user.is_authenticated:
        liked_ids = set(SchoolPostLike.objects.filter(
            user=request.user, post__school=school
        ).values_list('post_id', flat=True))

    is_admin = (request.user.is_authenticated and
                SchoolAdmin.objects.filter(school=school, user=request.user).exists())

    return render(request, 'community/school_detail.html', {
        'school':      school,
        'posts':       posts,
        'following':   following,
        'liked_ids':   liked_ids,
        'post_type':   post_type,
        'type_icons':  POST_TYPE_ICONS,
        'post_types':  SchoolPost.POST_TYPE_CHOICES,
        'is_admin':    is_admin,
    })


@login_required
def school_register(request):
    if request.method == 'POST':
        name  = request.POST.get('name', '').strip()
        stype = request.POST.get('school_type', 'secondary')
        addr  = request.POST.get('address', '').strip()
        pin   = request.POST.get('pincode', '').strip()
        about = request.POST.get('about', '').strip()
        phone     = request.POST.get('phone', '').strip()
        principal = request.POST.get('principal_name', '').strip()
        vice_prin = request.POST.get('vice_principal', '').strip()
        logo  = request.FILES.get('logo')
        cover = request.FILES.get('cover')
        if name:
            school = School.objects.create(
                name=name, school_type=stype, address=addr,
                pincode=pin, about=about, phone=phone,
                principal_name=principal, vice_principal=vice_prin,
                logo=logo, cover=cover, created_by=request.user,
            )
            SchoolAdmin.objects.create(school=school, user=request.user, role='owner', added_by=request.user)
            messages.success(request, f'{name} has been registered! You are the owner.')
            return redirect(f'/community/school-corner/{school.pk}/dashboard/')
    return render(request, 'community/school_register.html', {
        'type_choices': School.TYPE_CHOICES,
    })


@login_required
def school_post_create(request, pk):
    school = get_object_or_404(School, pk=pk)
    if not SchoolAdmin.objects.filter(school=school, user=request.user).exists():
        messages.error(request, 'Only school admins can post.')
        return redirect(f'/community/school-corner/{pk}/')
    if request.method == 'POST':
        title     = request.POST.get('title', '').strip()
        content   = request.POST.get('content', '').strip()
        post_type = request.POST.get('post_type', 'other')
        image     = request.FILES.get('image')
        if title and content:
            SchoolPost.objects.create(
                school=school, posted_by=request.user,
                title=title, content=content,
                post_type=post_type, image=image,
            )
            messages.success(request, 'Post published!')
        return redirect(f'/community/school-corner/{pk}/dashboard/')
    return render(request, 'community/school_post_form.html', {
        'school':      school,
        'post_types':  SchoolPost.POST_TYPE_CHOICES,
        'type_icons':  POST_TYPE_ICONS,
    })


def teacher_register(request):
    from django.contrib.auth import get_user_model, login as auth_login
    import random, string
    User2 = get_user_model()
    schools = School.objects.all().order_by('name')
    error = None
    generated = None  # show password to teacher after registration
    if request.method == 'POST':
        full_name = request.POST.get('full_name', '').strip()
        phone     = request.POST.get('phone', '').strip()
        school_id = request.POST.get('school_id', '').strip()
        if not all([full_name, phone, school_id]):
            error = 'All fields are required.'
        elif User2.objects.filter(username=phone).exists():
            error = 'This phone number is already registered.'
        else:
            try:
                school   = School.objects.get(pk=school_id)
                password = ''.join(random.choices(string.digits, k=6))  # 6-digit auto password
                parts    = full_name.split(' ', 1)
                user     = User2.objects.create_user(
                    username=phone,
                    password=password,
                    first_name=parts[0],
                    last_name=parts[1] if len(parts) > 1 else '',
                    phone=phone,
                )
                SchoolAdmin.objects.create(
                    school=school, user=user, role='teacher',
                    added_by=None, phone=phone,
                )
                generated = {'name': full_name, 'phone': phone, 'password': password, 'school': school}
            except Exception as e:
                from django.db import IntegrityError as _IntegrityError
                import logging as _logging
                _logging.getLogger('community.views').exception(
                    'teacher_register: failed for phone=%s', phone
                )
                if isinstance(e, _IntegrityError):
                    error = 'This phone may already be in use.'
                else:
                    error = 'Registration failed. Please try again.'
    return render(request, 'community/teacher_register.html', {
        'schools':   schools,
        'error':     error,
        'generated': generated,
    })


def teacher_login(request):
    from django.contrib.auth import authenticate, login as auth_login
    error = None
    if request.method == 'POST':
        phone    = request.POST.get('phone', '').strip()
        password = request.POST.get('password', '').strip()
        if not phone or not password:
            error = 'Please enter your phone number and password.'
        else:
            user = authenticate(request, username=phone, password=password)
            if user is None:
                error = 'Invalid phone number or password.'
            else:
                sa = SchoolAdmin.objects.filter(user=user, role='teacher').select_related('school').first()
                if sa is None:
                    error = 'No teacher account found for this phone number.'
                else:
                    auth_login(request, user)
                    return redirect(f'/community/school-corner/{sa.school.pk}/')
    return render(request, 'community/teacher_login.html', {'error': error})


@login_required
def school_dashboard(request, pk):
    school = get_object_or_404(School, pk=pk)
    admin_rec = SchoolAdmin.objects.filter(school=school, user=request.user).first()
    if not admin_rec:
        messages.error(request, 'Access denied.')
        return redirect(f'/community/school-corner/{pk}/')

    admins   = SchoolAdmin.objects.filter(school=school, role='admin').select_related('user', 'added_by')
    teachers = SchoolAdmin.objects.filter(school=school, role='teacher').select_related('user', 'added_by')
    posts    = school.posts.filter(is_active=True).select_related('posted_by')
    error  = None

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'add_teacher' and admin_rec.role in ('owner', 'admin'):
            import random, string as _str
            from django.contrib.auth import get_user_model
            User2 = get_user_model()
            full_name = request.POST.get('full_name', '').strip()
            phone     = request.POST.get('phone', '').strip()
            if not full_name or not phone:
                error = 'Name and phone are required.'
            elif User2.objects.filter(username=phone).exists():
                # phone already registered — just link existing user
                try:
                    new_user = User2.objects.get(username=phone)
                    obj, created = SchoolAdmin.objects.get_or_create(
                        school=school, user=new_user,
                        defaults={'role': 'teacher', 'added_by': request.user, 'phone': phone}
                    )
                    if not created:
                        error = f'This phone is already linked to this school.'
                    else:
                        messages.success(request, f'{full_name} added as teacher (existing account).')
                except Exception as e:
                    error = str(e)
            else:
                try:
                    password = ''.join(random.choices(_str.digits, k=6))
                    parts    = full_name.split(' ', 1)
                    new_user = User2.objects.create_user(
                        username=phone, password=password,
                        first_name=parts[0],
                        last_name=parts[1] if len(parts) > 1 else '',
                        phone=phone,
                    )
                    SchoolAdmin.objects.create(
                        school=school, user=new_user,
                        role='teacher', added_by=request.user, phone=phone,
                    )
                    messages.success(request, f'TEACHER_ADDED:{full_name}:{phone}:{password}')
                except Exception as e:
                    error = f'Failed: {e}'

        elif action == 'add_admin' and admin_rec.role in ('owner', 'admin'):
            username = request.POST.get('username', '').strip()
            if admin_rec.role != 'owner':
                error = 'Only owners can add admins.'
            else:
                try:
                    from django.contrib.auth import get_user_model
                    User2 = get_user_model()
                    new_user = User2.objects.get(username=username)
                    obj, created = SchoolAdmin.objects.get_or_create(
                        school=school, user=new_user,
                        defaults={'role': 'admin', 'added_by': request.user}
                    )
                    if not created:
                        error = f'"{username}" already has a role in this school.'
                    else:
                        messages.success(request, f'{username} added as admin.')
                except Exception:
                    error = f'User "{username}" not found.'

        elif action == 'remove_admin' and admin_rec.role in ('owner', 'admin'):
            uid = request.POST.get('user_id')
            qs = SchoolAdmin.objects.filter(school=school, user_id=uid).exclude(role='owner')
            if admin_rec.role == 'admin':
                qs = qs.filter(role='teacher')
            qs.delete()

        elif action == 'delete_post':
            post_id = request.POST.get('post_id')
            SchoolPost.objects.filter(pk=post_id, school=school).update(is_active=False)

        # pass teacher credentials via session instead of redirect loss
        from django.contrib.messages import get_messages
        for m in get_messages(request):
            if str(m).startswith('TEACHER_ADDED:'):
                parts = str(m).split(':')
                request.session['teacher_added'] = {'name': parts[1], 'phone': parts[2], 'password': parts[3]}
                break
        return redirect(f'/community/school-corner/{pk}/dashboard/')

    teacher_added = request.session.pop('teacher_added', None)
    return render(request, 'community/school_dashboard.html', {
        'school':        school,
        'admin_rec':     admin_rec,
        'admins':        admins,
        'teachers':      teachers,
        'posts':         posts,
        'error':         error,
        'post_types':    SchoolPost.POST_TYPE_CHOICES,
        'teacher_added': teacher_added,
    })


@login_required
def school_follow(request, pk):
    school = get_object_or_404(School, pk=pk)
    follow, created = SchoolFollow.objects.get_or_create(user=request.user, school=school)
    if not created:
        follow.delete()
        following = False
    else:
        following = True
    return JsonResponse({'following': following, 'count': school.follower_count()})


def _require_super_admin(request):
    from django.http import HttpResponseForbidden
    if not request.user.is_authenticated or getattr(request.user, 'admin_role', None) != 'super_admin':
        return HttpResponseForbidden('Super admin only.')
    return None


def school_admin_list(request):
    deny = _require_super_admin(request)
    if deny:
        return deny
    schools = School.objects.all().order_by('-created_at')
    return render(request, 'community/school_admin_list.html', {'schools': schools})


@require_POST
def school_delete(request, pk):
    deny = _require_super_admin(request)
    if deny:
        return deny
    school = get_object_or_404(School, pk=pk)
    school.delete()
    messages.success(request, f'School "{school.name}" deleted.')
    return redirect('school_admin_list')


@login_required
def school_post_like(request, pk):
    post = get_object_or_404(SchoolPost, pk=pk)
    like, created = SchoolPostLike.objects.get_or_create(user=request.user, post=post)
    if not created:
        like.delete()
        liked = False
    else:
        liked = True
    return JsonResponse({'liked': liked, 'count': post.like_count()})


# ── STUDENT SUCCESS ────────────────────────────────────────────────────────────
SS_CAT_ICONS = {
    'academics':   '📚',
    'sports':      '⚽',
    'arts':        '🎨',
    'music':       '🎵',
    'scholarship': '🏅',
    'competition': '🏆',
    'other':       '🎓',
}

SS_CAT_LABELS = {
    'academics':   'Academics',
    'sports':      'Sports',
    'arts':        'Arts',
    'music':       'Music',
    'scholarship': 'Scholarship',
    'competition': 'Competition',
    'other':       'Other',
}


def student_success_feed(request):
    cat = request.GET.get('cat', '')
    stories = StudentSuccess.objects.filter(is_active=True).select_related('user')
    if cat:
        stories = stories.filter(category=cat)

    liked_ids = set()
    if request.user.is_authenticated:
        liked_ids = set(StudentSuccessLike.objects.filter(
            user=request.user).values_list('success_id', flat=True))

    return render(request, 'community/student_success.html', {
        'stories':    stories,
        'liked_ids':  liked_ids,
        'active_cat': cat,
        'cat_icons':  SS_CAT_ICONS,
        'cat_labels': SS_CAT_LABELS,
    })


@login_required
def student_success_post(request):
    if request.method == 'POST':
        title        = request.POST.get('title', '').strip()
        content      = request.POST.get('content', '').strip()
        category     = request.POST.get('category', 'other')
        student_name = request.POST.get('student_name', '').strip()
        school_name  = request.POST.get('school_name', '').strip()
        grade        = request.POST.get('grade', '').strip()
        image        = request.FILES.get('image')
        pincode      = getattr(request.user, 'pincode', '') or ''
        if title and content and student_name:
            StudentSuccess.objects.create(
                user=request.user, title=title, content=content,
                category=category, student_name=student_name,
                school_name=school_name, grade=grade,
                image=image, pincode=pincode,
            )
            messages.success(request, 'Success story shared!')
            return redirect('/community/student-success/')
    return render(request, 'community/student_success_post.html', {
        'cat_icons':  SS_CAT_ICONS,
        'cat_labels': SS_CAT_LABELS,
    })


def student_success_detail(request, pk):
    story    = get_object_or_404(StudentSuccess, pk=pk, is_active=True)
    comments = story.comments.select_related('user').all()
    liked    = (request.user.is_authenticated and
                StudentSuccessLike.objects.filter(user=request.user, success=story).exists())
    if request.method == 'POST' and request.user.is_authenticated:
        text = request.POST.get('comment', '').strip()
        if text:
            StudentSuccessComment.objects.create(user=request.user, success=story, text=text)
        return redirect(f'/community/student-success/{pk}/')
    return render(request, 'community/student_success_detail.html', {
        'story':     story,
        'comments':  comments,
        'liked':     liked,
        'cat_icons': SS_CAT_ICONS,
    })


@login_required
def student_success_like(request, pk):
    story = get_object_or_404(StudentSuccess, pk=pk)
    like, created = StudentSuccessLike.objects.get_or_create(user=request.user, success=story)
    if not created:
        like.delete()
        liked = False
    else:
        liked = True
    return JsonResponse({'liked': liked, 'count': story.like_count()})


@login_required
def student_success_delete(request, pk):
    story = get_object_or_404(StudentSuccess, pk=pk, user=request.user)
    story.delete()
    return redirect('/community/student-success/')


# ── KIDS CORNER ────────────────────────────────────────────────────────────────
KIDS_TYPE_ICONS = {
    'story':    '📖',
    'drawing':  '🎨',
    'craft':    '✂️',
    'poem':     '✍️',
    'joke':     '😄',
    'activity': '🎯',
    'other':    '🧒',
}


def kids_corner_feed(request):
    post_type = request.GET.get('type', '')
    posts = KidsPost.objects.filter(is_active=True).select_related('posted_by')
    if post_type:
        posts = posts.filter(post_type=post_type)

    liked_ids = set()
    if request.user.is_authenticated:
        liked_ids = set(KidsPostLike.objects.filter(
            user=request.user).values_list('post_id', flat=True))

    return render(request, 'community/kids_corner.html', {
        'posts':      posts,
        'liked_ids':  liked_ids,
        'active_type': post_type,
        'type_icons': KIDS_TYPE_ICONS,
        'post_types': KidsPost.TYPE_CHOICES,
    })


@login_required
def kids_corner_post(request):
    if request.method == 'POST':
        title     = request.POST.get('title', '').strip()
        content   = request.POST.get('content', '').strip()
        post_type = request.POST.get('post_type', 'other')
        kid_name  = request.POST.get('kid_name', '').strip()
        age       = request.POST.get('age', '').strip()
        image     = request.FILES.get('image')
        pincode   = getattr(request.user, 'pincode', '') or ''
        if title and content and kid_name:
            KidsPost.objects.create(
                posted_by=request.user, title=title, content=content,
                post_type=post_type, kid_name=kid_name,
                age=max(0, min(150, int(age))) if age.isdigit() else None,
                image=image, pincode=pincode,
            )
            messages.success(request, 'Posted to Kids Corner!')
            return redirect('/community/kids-corner/')
    return render(request, 'community/kids_corner_post.html', {
        'type_icons': KIDS_TYPE_ICONS,
        'post_types': KidsPost.TYPE_CHOICES,
    })


def kids_corner_detail(request, pk):
    post     = get_object_or_404(KidsPost, pk=pk, is_active=True)
    comments = post.comments.select_related('user').all()
    liked    = (request.user.is_authenticated and
                KidsPostLike.objects.filter(user=request.user, post=post).exists())
    if request.method == 'POST' and request.user.is_authenticated:
        text = request.POST.get('comment', '').strip()
        if text:
            KidsPostComment.objects.create(user=request.user, post=post, text=text)
        return redirect(f'/community/kids-corner/{pk}/')
    return render(request, 'community/kids_corner_detail.html', {
        'post':       post,
        'comments':   comments,
        'liked':      liked,
        'type_icons': KIDS_TYPE_ICONS,
    })


@login_required
def kids_corner_like(request, pk):
    post = get_object_or_404(KidsPost, pk=pk)
    like, created = KidsPostLike.objects.get_or_create(user=request.user, post=post)
    if not created:
        like.delete()
        liked = False
    else:
        liked = True
    return JsonResponse({'liked': liked, 'count': post.like_count()})


@login_required
def kids_corner_delete(request, pk):
    post = get_object_or_404(KidsPost, pk=pk, posted_by=request.user)
    post.delete()
    return redirect('/community/kids-corner/')


# ── PARENTING ──────────────────────────────────────────────────────────────────
PT_CAT_ICONS = {
    'tips':      '💡',
    'activity':  '🎯',
    'health':    '🏥',
    'education': '📚',
    'food':      '🥗',
    'emotion':   '💛',
    'other':     '👨‍👩‍👧',
}


def parenting_feed(request):
    cat   = request.GET.get('cat', '')
    posts = ParentingPost.objects.filter(is_active=True).select_related('user')
    if cat:
        posts = posts.filter(category=cat)
    liked_ids = set()
    if request.user.is_authenticated:
        liked_ids = set(ParentingLike.objects.filter(
            user=request.user).values_list('post_id', flat=True))
    return render(request, 'community/parenting.html', {
        'posts':      posts,
        'liked_ids':  liked_ids,
        'active_cat': cat,
        'cat_icons':  PT_CAT_ICONS,
        'categories': ParentingPost.CAT_CHOICES,
    })


@login_required
def parenting_post(request):
    if request.method == 'POST':
        title    = request.POST.get('title', '').strip()
        content  = request.POST.get('content', '').strip()
        category = request.POST.get('category', 'other')
        image    = request.FILES.get('image')
        pincode  = getattr(request.user, 'pincode', '') or ''
        if title and content:
            ParentingPost.objects.create(
                user=request.user, title=title, content=content,
                category=category, image=image, pincode=pincode,
            )
            messages.success(request, 'Your parenting tip has been shared!')
            return redirect('/community/parenting/')
    return render(request, 'community/parenting_post.html', {
        'cat_icons':  PT_CAT_ICONS,
        'categories': ParentingPost.CAT_CHOICES,
    })


def parenting_detail(request, pk):
    post     = get_object_or_404(ParentingPost, pk=pk, is_active=True)
    comments = post.comments.select_related('user').all()
    liked    = (request.user.is_authenticated and
                ParentingLike.objects.filter(user=request.user, post=post).exists())
    if request.method == 'POST' and request.user.is_authenticated:
        text = request.POST.get('comment', '').strip()
        if text:
            ParentingComment.objects.create(user=request.user, post=post, text=text)
        return redirect(f'/community/parenting/{pk}/')
    return render(request, 'community/parenting_detail.html', {
        'post':      post,
        'comments':  comments,
        'liked':     liked,
        'cat_icons': PT_CAT_ICONS,
    })


@login_required
def parenting_like(request, pk):
    post = get_object_or_404(ParentingPost, pk=pk)
    like, created = ParentingLike.objects.get_or_create(user=request.user, post=post)
    if not created:
        like.delete()
        liked = False
    else:
        liked = True
    return JsonResponse({'liked': liked, 'count': post.like_count()})


@login_required
def parenting_delete(request, pk):
    post = get_object_or_404(ParentingPost, pk=pk, user=request.user)
    post.delete()
    return redirect('/community/parenting/')


# ── GRANDPARENTS ARCHIVE ───────────────────────────────────────────────────────
GP_CAT_ICONS = {
    'memory':    '🕰️',
    'wisdom':    '📜',
    'recipe':    '🍲',
    'tradition': '🎎',
    'history':   '🏛️',
    'other':     '👴',
}


def grandparents_feed(request):
    cat    = request.GET.get('cat', '')
    stories = GrandparentStory.objects.filter(is_active=True).select_related('user')
    if cat:
        stories = stories.filter(category=cat)
    liked_ids = set()
    if request.user.is_authenticated:
        liked_ids = set(GrandparentLike.objects.filter(
            user=request.user).values_list('story_id', flat=True))
    return render(request, 'community/grandparents.html', {
        'stories':    stories,
        'liked_ids':  liked_ids,
        'active_cat': cat,
        'cat_icons':  GP_CAT_ICONS,
        'categories': GrandparentStory.CAT_CHOICES,
    })


@login_required
def grandparents_post(request):
    if request.method == 'POST':
        title      = request.POST.get('title', '').strip()
        content    = request.POST.get('content', '').strip()
        category   = request.POST.get('category', 'memory')
        elder_name = request.POST.get('elder_name', '').strip()
        age        = request.POST.get('age', '').strip()
        era        = request.POST.get('era', '').strip()
        image      = request.FILES.get('image')
        pincode    = getattr(request.user, 'pincode', '') or ''
        if title and content and elder_name:
            GrandparentStory.objects.create(
                user=request.user, title=title, content=content,
                category=category, elder_name=elder_name,
                age=max(0, min(200, int(age))) if age.isdigit() else None,
                era=era, image=image, pincode=pincode,
            )
            messages.success(request, 'Story preserved in the archive!')
            return redirect('/community/grandparents-archive/')
    return render(request, 'community/grandparents_post.html', {
        'cat_icons':  GP_CAT_ICONS,
        'categories': GrandparentStory.CAT_CHOICES,
    })


def grandparents_detail(request, pk):
    story    = get_object_or_404(GrandparentStory, pk=pk, is_active=True)
    comments = story.comments.select_related('user').all()
    liked    = (request.user.is_authenticated and
                GrandparentLike.objects.filter(user=request.user, story=story).exists())
    if request.method == 'POST' and request.user.is_authenticated:
        text = request.POST.get('comment', '').strip()
        if text:
            GrandparentComment.objects.create(user=request.user, story=story, text=text)
        return redirect(f'/community/grandparents-archive/{pk}/')
    return render(request, 'community/grandparents_detail.html', {
        'story':     story,
        'comments':  comments,
        'liked':     liked,
        'cat_icons': GP_CAT_ICONS,
    })


@login_required
def grandparents_like(request, pk):
    story = get_object_or_404(GrandparentStory, pk=pk)
    like, created = GrandparentLike.objects.get_or_create(user=request.user, story=story)
    if not created:
        like.delete()
        liked = False
    else:
        liked = True
    return JsonResponse({'liked': liked, 'count': story.like_count()})


@login_required
def grandparents_delete(request, pk):
    story = get_object_or_404(GrandparentStory, pk=pk, user=request.user)
    story.delete()
    return redirect('/community/grandparents-archive/')


# ── LOCAL HEROES ───────────────────────────────────────────────────────────────
LH_CAT_ICONS = {
    'social':      '🤝',
    'environment': '🌿',
    'education':   '📚',
    'health':      '🏥',
    'sports':      '🏅',
    'arts':        '🎨',
    'other':       '🦸',
}


def local_heroes_feed(request):
    cat   = request.GET.get('cat', '')
    heroes = LocalHero.objects.filter(is_active=True).select_related('posted_by')
    if cat:
        heroes = heroes.filter(category=cat)
    liked_ids = set()
    if request.user.is_authenticated:
        liked_ids = set(LocalHeroLike.objects.filter(
            user=request.user).values_list('hero_id', flat=True))
    return render(request, 'community/local_heroes.html', {
        'heroes':     heroes,
        'liked_ids':  liked_ids,
        'active_cat': cat,
        'cat_icons':  LH_CAT_ICONS,
        'categories': LocalHero.CAT_CHOICES,
    })


@login_required
def local_hero_post(request):
    if request.method == 'POST':
        title     = request.POST.get('title', '').strip()
        content   = request.POST.get('content', '').strip()
        category  = request.POST.get('category', 'social')
        hero_name = request.POST.get('hero_name', '').strip()
        image     = request.FILES.get('image')
        pincode   = getattr(request.user, 'pincode', '') or ''
        if title and content and hero_name:
            LocalHero.objects.create(
                posted_by=request.user, title=title, content=content,
                category=category, hero_name=hero_name,
                image=image, pincode=pincode,
            )
            messages.success(request, 'Hero story published!')
            return redirect('/community/local-heroes/')
    return render(request, 'community/local_hero_post.html', {
        'cat_icons':  LH_CAT_ICONS,
        'categories': LocalHero.CAT_CHOICES,
    })


def local_hero_detail(request, pk):
    hero     = get_object_or_404(LocalHero, pk=pk, is_active=True)
    comments = hero.comments.select_related('user').all()
    liked    = (request.user.is_authenticated and
                LocalHeroLike.objects.filter(user=request.user, hero=hero).exists())
    if request.method == 'POST' and request.user.is_authenticated:
        text = request.POST.get('comment', '').strip()
        if text:
            LocalHeroComment.objects.create(user=request.user, hero=hero, text=text)
        return redirect(f'/community/local-heroes/{pk}/')
    return render(request, 'community/local_hero_detail.html', {
        'hero':      hero,
        'comments':  comments,
        'liked':     liked,
        'cat_icons': LH_CAT_ICONS,
    })


@login_required
def local_hero_like(request, pk):
    hero = get_object_or_404(LocalHero, pk=pk)
    like, created = LocalHeroLike.objects.get_or_create(user=request.user, hero=hero)
    if not created:
        like.delete()
        liked = False
    else:
        liked = True
    return JsonResponse({'liked': liked, 'count': hero.like_count()})


@login_required
def local_hero_delete(request, pk):
    hero = get_object_or_404(LocalHero, pk=pk, posted_by=request.user)
    hero.delete()
    return redirect('/community/local-heroes/')


# ── COMMUNITY EVENTS ───────────────────────────────────────────────────────────
import datetime

EV_CAT_ICONS = {
    'festival':  '🎉',
    'sports':    '⚽',
    'cultural':  '🎭',
    'health':    '🏥',
    'education': '📚',
    'religious': '🕌',
    'cleanup':   '🧹',
    'other':     '📅',
}


def events_feed(request):
    cat    = request.GET.get('cat', '')
    today  = datetime.date.today()
    events = CommunityEvent.objects.filter(is_active=True, event_date__gte=today)
    if cat:
        events = events.filter(category=cat)

    my_rsvps = {}
    if request.user.is_authenticated:
        for r in EventRSVP.objects.filter(user=request.user, event__in=events):
            my_rsvps[r.event_id] = r.status

    return render(request, 'community/events.html', {
        'events':     events,
        'my_rsvps':   my_rsvps,
        'active_cat': cat,
        'cat_icons':  EV_CAT_ICONS,
        'categories': CommunityEvent.CAT_CHOICES,
        'today':      today,
    })


@login_required
def event_post(request):
    if request.method == 'POST':
        title       = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        category    = request.POST.get('category', 'other')
        event_date  = request.POST.get('event_date', '')
        event_time  = request.POST.get('event_time', '') or None
        venue       = request.POST.get('venue', '').strip()
        image       = request.FILES.get('image')
        pincode     = getattr(request.user, 'pincode', '') or ''
        if title and description and event_date and venue:
            CommunityEvent.objects.create(
                posted_by=request.user, title=title, description=description,
                category=category, event_date=event_date, event_time=event_time,
                venue=venue, image=image, pincode=pincode,
            )
            messages.success(request, 'Event posted!')
            return redirect('/community/events/')
    return render(request, 'community/event_post.html', {
        'cat_icons':  EV_CAT_ICONS,
        'categories': CommunityEvent.CAT_CHOICES,
        'today':      datetime.date.today().isoformat(),
    })


def event_detail(request, pk):
    event    = get_object_or_404(CommunityEvent, pk=pk, is_active=True)
    comments = event.comments.select_related('user').all()
    my_rsvp  = None
    has_photo = False
    if request.user.is_authenticated:
        r = EventRSVP.objects.filter(user=request.user, event=event).first()
        my_rsvp = r.status if r else None
        try:
            has_photo = bool(request.user.seeker.photo)
        except Exception:
            has_photo = False
    if request.method == 'POST' and request.user.is_authenticated:
        text = request.POST.get('comment', '').strip()
        if text:
            EventComment.objects.create(user=request.user, event=event, text=text)
        return redirect(f'/community/events/{pk}/')
    going_users = list(event.rsvps.filter(status='going').select_related('user'))
    # Load user-to-user ratings for this event
    from .models import CommunityEventUserRating
    ratings_by_ratee = {}
    my_given_ratings = {}
    if request.user.is_authenticated:
        for ur in CommunityEventUserRating.objects.filter(event=event):
            ratings_by_ratee.setdefault(ur.ratee_id, []).append(ur.rating)
            if ur.rater_id == request.user.pk:
                my_given_ratings[ur.ratee_id] = ur.rating
    already_rated = False
    going_user_data = []
    going_user_ids = {r.user_id for r in going_users}
    if request.user.is_authenticated and request.user.pk in going_user_ids:
        already_rated = CommunityEventUserRating.objects.filter(event=event, rater=request.user).exists()
    for r in going_users:
        u = r.user
        ratings = ratings_by_ratee.get(u.pk, [])
        avg = round(sum(ratings) / len(ratings), 1) if ratings else None
        going_user_data.append({
            'user': u,
            'avg': avg,
            'count': len(ratings),
            'my_rating': my_given_ratings.get(u.pk),
        })
    return render(request, 'community/event_detail.html', {
        'event':     event,
        'comments':  comments,
        'my_rsvp':   my_rsvp,
        'has_photo': has_photo,
        'cat_icons': EV_CAT_ICONS,
        'going_user_data': going_user_data,
        'going_user_ids': going_user_ids,
        'already_rated': already_rated,
    })


@login_required
def event_rsvp(request, pk):
    event  = get_object_or_404(CommunityEvent, pk=pk)
    status = request.POST.get('status', 'going')

    # Require profile photo before going RSVP
    if status == 'going':
        try:
            has_photo = bool(request.user.seeker.photo)
        except Exception:
            has_photo = False
        if not has_photo:
            return JsonResponse({'error': 'photo_required', 'status': None,
                                 'going': event.going_count(), 'interested': event.interested_count()})

    rsvp, created = EventRSVP.objects.get_or_create(user=request.user, event=event,
                                                    defaults={'status': status})
    if not created:
        if rsvp.status == status:
            rsvp.delete()
            status = None
        else:
            rsvp.status = status
            rsvp.save()
    return JsonResponse({
        'status':      status,
        'going':       event.going_count(),
        'interested':  event.interested_count(),
    })


@login_required
@transaction.atomic
def event_rate_user(request, pk):
    """Submit user-to-user ratings for a community event."""
    from .models import CommunityEventUserRating
    event = get_object_or_404(CommunityEvent, pk=pk)
    going_user_ids = set(event.rsvps.filter(status='going').values_list('user_id', flat=True))
    if request.user.pk not in going_user_ids:
        messages.error(request, 'Only attendees can rate others.')
        return redirect(f'/community/events/{pk}/')
    # One-time only — block re-submission
    if CommunityEventUserRating.objects.filter(event=event, rater=request.user).exists():
        messages.info(request, 'You have already submitted your ratings for this event.')
        return redirect(f'/community/events/{pk}/')
    from django.contrib.auth import get_user_model
    AuthUser = get_user_model()
    from portal.models import Community, MemberPoints
    from portal.views import award_points

    # Find a shared community for points awarding
    rater_community_ids = set(
        Community.objects.filter(memberships__user=request.user, memberships__status='approved').values_list('id', flat=True)
    )

    for key, val in request.POST.items():
        if key.startswith('rating_'):
            try:
                uid = int(key[7:])
                rating_val = int(val)
            except (ValueError, TypeError):
                continue
            if 1 <= rating_val <= 5 and uid in going_user_ids and uid != request.user.pk:
                try:
                    ratee = AuthUser.objects.get(pk=uid)
                except AuthUser.DoesNotExist:
                    continue
                obj, created = CommunityEventUserRating.objects.get_or_create(
                    event=event, rater=request.user, ratee=ratee,
                    defaults={'rating': rating_val},
                )
                if created:
                    # Award points in shared community if any
                    ratee_community_ids = set(
                        Community.objects.filter(memberships__user=ratee, memberships__status='approved').values_list('id', flat=True)
                    )
                    shared = rater_community_ids & ratee_community_ids
                    if shared:
                        community = Community.objects.get(pk=next(iter(shared)))
                        award_points(ratee, community, rating_val,
                                     f'Peer rating at event: {event.title} ({rating_val}⭐ from {request.user.get_full_name() or request.user.username})')
    messages.success(request, 'Your ratings have been submitted! ⭐')
    return redirect(f'/community/events/{pk}/')


@login_required
def event_delete(request, pk):
    from django.utils import timezone
    event = get_object_or_404(CommunityEvent, pk=pk, posted_by=request.user)
    event.is_active = False
    event.deleted_at = timezone.now()
    event.save()
    return redirect('/community/events/')

def event_deleted_history(request):
    if not request.user.is_authenticated:
        return redirect('/login/')
    deleted_events = CommunityEvent.objects.filter(
        posted_by=request.user, is_active=False
    ).order_by('-deleted_at')
    return render(request, 'community/event_deleted_history.html', {
        'deleted_events': deleted_events,
    })


# ── VOLUNTEER ACTIVITIES ───────────────────────────────────────────────────────
VOL_CAT_ICONS = {
    'blood':     '🩸',
    'tree':      '🌳',
    'health':    '🏥',
    'education': '📚',
    'cleanup':   '🧹',
    'food':      '🍱',
    'other':     '🤝',
}


def volunteer_feed(request):
    cat        = request.GET.get('cat', '')
    today      = datetime.date.today()
    activities = VolunteerActivity.objects.filter(is_active=True, activity_date__gte=today)
    if cat:
        activities = activities.filter(category=cat)
    my_signups = set()
    if request.user.is_authenticated:
        my_signups = set(VolunteerSignup.objects.filter(
            user=request.user).values_list('activity_id', flat=True))
    return render(request, 'community/volunteer.html', {
        'activities': activities,
        'my_signups': my_signups,
        'active_cat': cat,
        'cat_icons':  VOL_CAT_ICONS,
        'categories': VolunteerActivity.CAT_CHOICES,
        'today':      today,
    })


@login_required
def volunteer_post(request):
    if request.method == 'POST':
        title    = request.POST.get('title', '').strip()
        desc     = request.POST.get('description', '').strip()
        category = request.POST.get('category', 'other')
        act_date = request.POST.get('activity_date', '')
        act_time = request.POST.get('activity_time', '') or None
        venue    = request.POST.get('venue', '').strip()
        needed   = request.POST.get('volunteers_needed', '0')
        contact  = request.POST.get('contact', '').strip()
        image    = request.FILES.get('image')
        pincode  = getattr(request.user, 'pincode', '') or ''
        if title and desc and act_date and venue:
            VolunteerActivity.objects.create(
                posted_by=request.user, title=title, description=desc,
                category=category, activity_date=act_date, activity_time=act_time,
                venue=venue, volunteers_needed=int(needed) if needed.isdigit() else 0,
                contact=contact, image=image, pincode=pincode,
            )
            messages.success(request, 'Volunteer activity posted!')
            return redirect('/community/volunteer/')
    return render(request, 'community/volunteer_post.html', {
        'cat_icons':  VOL_CAT_ICONS,
        'categories': VolunteerActivity.CAT_CHOICES,
        'today':      datetime.date.today().isoformat(),
    })


def volunteer_detail(request, pk):
    activity = get_object_or_404(VolunteerActivity, pk=pk, is_active=True)
    comments = activity.comments.select_related('user').all()
    signed_up = (request.user.is_authenticated and
                 VolunteerSignup.objects.filter(user=request.user, activity=activity).exists())
    if request.method == 'POST' and request.user.is_authenticated:
        text = request.POST.get('comment', '').strip()
        if text:
            VolunteerComment.objects.create(user=request.user, activity=activity, text=text)
        return redirect(f'/community/volunteer/{pk}/')
    return render(request, 'community/volunteer_detail.html', {
        'activity':  activity,
        'comments':  comments,
        'signed_up': signed_up,
        'cat_icons': VOL_CAT_ICONS,
    })


@login_required
def volunteer_signup(request, pk):
    activity = get_object_or_404(VolunteerActivity, pk=pk)
    signup, created = VolunteerSignup.objects.get_or_create(user=request.user, activity=activity)
    if not created:
        signup.delete()
        signed_up = False
    else:
        signed_up = True
    return JsonResponse({'signed_up': signed_up, 'count': activity.volunteer_count()})


@login_required
def volunteer_delete(request, pk):
    activity = get_object_or_404(VolunteerActivity, pk=pk, posted_by=request.user)
    activity.delete()
    return redirect('/community/volunteer/')


# ── BUSINESS STORIES ───────────────────────────────────────────────────────────
BS_CAT_ICONS = {
    'startup':   '🚀',
    'family':    '🏠',
    'comeback':  '💪',
    'milestone': '🏆',
    'lesson':    '📖',
    'other':     '🏪',
}


def business_stories_feed(request):
    cat    = request.GET.get('cat', '')
    stories = BusinessStory.objects.filter(is_active=True).select_related('user')
    if cat:
        stories = stories.filter(category=cat)
    liked_ids = set()
    if request.user.is_authenticated:
        liked_ids = set(BusinessStoryLike.objects.filter(
            user=request.user).values_list('story_id', flat=True))
    return render(request, 'community/business_stories.html', {
        'stories':    stories,
        'liked_ids':  liked_ids,
        'active_cat': cat,
        'cat_icons':  BS_CAT_ICONS,
        'categories': BusinessStory.CAT_CHOICES,
    })


@login_required
def business_story_post(request):
    if request.method == 'POST':
        title         = request.POST.get('title', '').strip()
        content       = request.POST.get('content', '').strip()
        category      = request.POST.get('category', 'other')
        business_name = request.POST.get('business_name', '').strip()
        years         = request.POST.get('years', '').strip()
        image         = request.FILES.get('image')
        pincode       = getattr(request.user, 'pincode', '') or ''
        if title and content and business_name:
            BusinessStory.objects.create(
                user=request.user, title=title, content=content,
                category=category, business_name=business_name,
                years=int(years) if years.isdigit() else None,
                image=image, pincode=pincode,
            )
            messages.success(request, 'Business story shared!')
            return redirect('/community/business-stories/')
    return render(request, 'community/business_story_post.html', {
        'cat_icons':  BS_CAT_ICONS,
        'categories': BusinessStory.CAT_CHOICES,
    })


def business_story_detail(request, pk):
    story    = get_object_or_404(BusinessStory, pk=pk, is_active=True)
    comments = story.comments.select_related('user').all()
    liked    = (request.user.is_authenticated and
                BusinessStoryLike.objects.filter(user=request.user, story=story).exists())
    if request.method == 'POST' and request.user.is_authenticated:
        text = request.POST.get('comment', '').strip()
        if text:
            BusinessStoryComment.objects.create(user=request.user, story=story, text=text)
        return redirect(f'/community/business-stories/{pk}/')
    return render(request, 'community/business_story_detail.html', {
        'story':     story,
        'comments':  comments,
        'liked':     liked,
        'cat_icons': BS_CAT_ICONS,
    })


@login_required
def business_story_like(request, pk):
    story = get_object_or_404(BusinessStory, pk=pk)
    like, created = BusinessStoryLike.objects.get_or_create(user=request.user, story=story)
    if not created:
        like.delete()
        liked = False
    else:
        liked = True
    return JsonResponse({'liked': liked, 'count': story.like_count()})


@login_required
def business_story_delete(request, pk):
    story = get_object_or_404(BusinessStory, pk=pk, user=request.user)
    story.delete()
    return redirect('/community/business-stories/')


# ── HALL OF FAME ───────────────────────────────────────────────────────────────
import datetime as _dt

HOF_CAT_ICONS = {
    'academics': '📚',
    'sports':    '⚽',
    'arts':      '🎨',
    'social':    '🤝',
    'business':  '🏪',
    'other':     '🏆',
}


def hall_of_fame_feed(request):
    cat    = request.GET.get('cat', '')
    year   = request.GET.get('year', '')
    entries = HallOfFameEntry.objects.filter(is_active=True)
    if cat:
        entries = entries.filter(category=cat)
    if year:
        entries = entries.filter(year=year)

    voted_ids = set()
    if request.user.is_authenticated:
        voted_ids = set(HallOfFameVote.objects.filter(
            user=request.user).values_list('entry_id', flat=True))

    current_year = _dt.date.today().year
    years = list(range(current_year, current_year - 6, -1))

    return render(request, 'community/hall_of_fame.html', {
        'entries':      entries,
        'voted_ids':    voted_ids,
        'active_cat':   cat,
        'active_year':  year,
        'cat_icons':    HOF_CAT_ICONS,
        'categories':   HallOfFameEntry.CAT_CHOICES,
        'years':        years,
        'current_year': current_year,
    })


@login_required
def hall_of_fame_nominate(request):
    if request.method == 'POST':
        nominee_name = request.POST.get('nominee_name', '').strip()
        category     = request.POST.get('category', 'other')
        achievement  = request.POST.get('achievement', '').strip()
        description  = request.POST.get('description', '').strip()
        year         = request.POST.get('year', str(_dt.date.today().year))
        image        = request.FILES.get('image')
        pincode      = getattr(request.user, 'pincode', '') or ''
        if nominee_name and achievement and description:
            HallOfFameEntry.objects.create(
                nominated_by=request.user, nominee_name=nominee_name,
                category=category, achievement=achievement,
                description=description, year=int(year),
                image=image, pincode=pincode,
            )
            messages.success(request, f'{nominee_name} has been nominated!')
            return redirect('/community/hall-of-fame/')
    current_year = _dt.date.today().year
    return render(request, 'community/hall_of_fame_nominate.html', {
        'cat_icons':    HOF_CAT_ICONS,
        'categories':   HallOfFameEntry.CAT_CHOICES,
        'current_year': current_year,
        'years':        list(range(current_year, current_year - 4, -1)),
    })


def hall_of_fame_detail(request, pk):
    entry    = get_object_or_404(HallOfFameEntry, pk=pk, is_active=True)
    comments = entry.comments.select_related('user').all()
    voted    = (request.user.is_authenticated and
                HallOfFameVote.objects.filter(user=request.user, entry=entry).exists())
    if request.method == 'POST' and request.user.is_authenticated:
        text = request.POST.get('comment', '').strip()
        if text:
            HallOfFameComment.objects.create(user=request.user, entry=entry, text=text)
        return redirect(f'/community/hall-of-fame/{pk}/')
    return render(request, 'community/hall_of_fame_detail.html', {
        'entry':      entry,
        'comments':   comments,
        'voted':      voted,
        'vote_count': entry.vote_count(),
        'cat_icons':  HOF_CAT_ICONS,
    })


@login_required
def hall_of_fame_vote(request, pk):
    entry = get_object_or_404(HallOfFameEntry, pk=pk)
    vote, created = HallOfFameVote.objects.get_or_create(user=request.user, entry=entry)
    if not created:
        vote.delete()
        voted = False
    else:
        voted = True
    return JsonResponse({'voted': voted, 'count': entry.vote_count()})


# ── MARKETPLACE ────────────────────────────────────────────────────────────────
MP_CAT_ICONS = {
    'electronics': '📱', 'furniture': '🛋️', 'clothing': '👗', 'books': '📚',
    'vehicles': '🚗', 'appliances': '🏠', 'sports': '⚽', 'toys': '🧸',
    'food': '🥗', 'services': '🔧', 'other': '🛒',
}
MP_TYPE_ICONS = {
    'sell': '🏷️', 'rent': '🔑', 'free': '🎁', 'wanted': '🔍',
}


def marketplace_feed(request):
    cat  = request.GET.get('cat', '')
    ltype = request.GET.get('type', '')
    listings = MarketplaceListing.objects.filter(is_active=True)
    if cat:
        listings = listings.filter(category=cat)
    if ltype:
        listings = listings.filter(listing_type=ltype)
    interest_ids = set()
    if request.user.is_authenticated:
        interest_ids = set(ListingInterest.objects.filter(
            user=request.user).values_list('listing_id', flat=True))
    return render(request, 'community/marketplace.html', {
        'listings':     listings,
        'interest_ids': interest_ids,
        'active_cat':   cat,
        'active_type':  ltype,
        'cat_icons':    MP_CAT_ICONS,
        'type_icons':   MP_TYPE_ICONS,
        'categories':   MarketplaceListing.CAT_CHOICES,
        'types':        MarketplaceListing.TYPE_CHOICES,
    })


@login_required
def marketplace_post(request):
    if request.method == 'POST':
        listing_type = request.POST.get('listing_type', 'sell')
        price_raw    = request.POST.get('price', '').strip()
        price        = float(price_raw) if price_raw else None
        listing = MarketplaceListing.objects.create(
            user         = request.user,
            title        = request.POST['title'],
            category     = request.POST['category'],
            listing_type = listing_type,
            condition    = request.POST.get('condition', 'good') if listing_type != 'wanted' else '',
            price        = price,
            description  = request.POST['description'],
            pincode      = request.POST.get('pincode', ''),
            contact      = request.POST.get('contact', ''),
            image        = request.FILES.get('image'),
        )
        return redirect(f'/community/marketplace/{listing.pk}/')
    return render(request, 'community/marketplace_post.html', {
        'cat_icons':  MP_CAT_ICONS,
        'type_icons': MP_TYPE_ICONS,
        'categories': MarketplaceListing.CAT_CHOICES,
        'types':      MarketplaceListing.TYPE_CHOICES,
        'conditions': MarketplaceListing.CONDITION_CHOICES,
    })


def marketplace_detail(request, pk):
    listing  = get_object_or_404(MarketplaceListing, pk=pk, is_active=True)
    comments = listing.mp_comments.select_related('user').all()
    interested = (request.user.is_authenticated and
                  ListingInterest.objects.filter(user=request.user, listing=listing).exists())
    if request.method == 'POST' and request.user.is_authenticated:
        text = request.POST.get('comment', '').strip()
        if text:
            ListingComment.objects.create(user=request.user, listing=listing, text=text)
        return redirect(f'/community/marketplace/{pk}/')
    return render(request, 'community/marketplace_detail.html', {
        'listing':    listing,
        'comments':   comments,
        'interested': interested,
        'interest_count': listing.interest_count(),
        'cat_icons':  MP_CAT_ICONS,
        'type_icons': MP_TYPE_ICONS,
    })


@login_required
def marketplace_interest(request, pk):
    listing = get_object_or_404(MarketplaceListing, pk=pk)
    obj, created = ListingInterest.objects.get_or_create(user=request.user, listing=listing)
    if not created:
        obj.delete()
        interested = False
    else:
        interested = True
    return JsonResponse({'interested': interested, 'count': listing.interest_count()})


@login_required
def marketplace_sold(request, pk):
    listing = get_object_or_404(MarketplaceListing, pk=pk, user=request.user)
    listing.is_sold = not listing.is_sold
    listing.save()
    return JsonResponse({'sold': listing.is_sold})


@login_required
def marketplace_delete(request, pk):
    listing = get_object_or_404(MarketplaceListing, pk=pk, user=request.user)
    listing.is_active = False
    listing.save()
    return redirect('/community/marketplace/')


# ── COMMUNITY WATCH ────────────────────────────────────────────────────────────
WATCH_CAT_ICONS = {
    'theft':      '🚨', 'suspicious': '👁️', 'hazard': '⚠️',
    'lost_found': '🔍', 'noise':      '📢', 'stray':  '🐕',
    'infra':      '🏗️', 'other':      '📋',
}
SEVERITY_COLORS = {
    'low':    '#16a34a',
    'medium': '#d97706',
    'high':   '#dc2626',
}


def watch_feed(request):
    cat      = request.GET.get('cat', '')
    severity = request.GET.get('sev', '')
    reports  = WatchReport.objects.filter(is_active=True)
    if cat:
        reports = reports.filter(category=cat)
    if severity:
        reports = reports.filter(severity=severity)
    confirm_ids = set()
    if request.user.is_authenticated:
        confirm_ids = set(WatchConfirm.objects.filter(
            user=request.user).values_list('report_id', flat=True))
    return render(request, 'community/community_watch.html', {
        'reports':      reports,
        'confirm_ids':  confirm_ids,
        'active_cat':   cat,
        'active_sev':   severity,
        'cat_icons':    WATCH_CAT_ICONS,
        'sev_colors':   SEVERITY_COLORS,
        'categories':   WatchReport.CAT_CHOICES,
        'severities':   WatchReport.SEVERITY_CHOICES,
    })


@login_required
def watch_post(request):
    if request.method == 'POST':
        report = WatchReport.objects.create(
            user        = request.user,
            category    = request.POST['category'],
            severity    = request.POST.get('severity', 'medium'),
            title       = request.POST['title'],
            description = request.POST['description'],
            location    = request.POST.get('location', ''),
            pincode     = request.POST.get('pincode', ''),
            image       = request.FILES.get('image'),
        )
        return redirect(f'/community/community-watch/{report.pk}/')
    return render(request, 'community/watch_post.html', {
        'cat_icons':  WATCH_CAT_ICONS,
        'categories': WatchReport.CAT_CHOICES,
        'severities': WatchReport.SEVERITY_CHOICES,
        'sev_colors': SEVERITY_COLORS,
    })


def watch_detail(request, pk):
    report   = get_object_or_404(WatchReport, pk=pk, is_active=True)
    comments = report.watch_comments.select_related('user').all()
    confirmed = (request.user.is_authenticated and
                 WatchConfirm.objects.filter(user=request.user, report=report).exists())
    if request.method == 'POST' and request.user.is_authenticated:
        text = request.POST.get('comment', '').strip()
        if text:
            WatchComment.objects.create(user=request.user, report=report, text=text)
        return redirect(f'/community/community-watch/{pk}/')
    return render(request, 'community/watch_detail.html', {
        'report':         report,
        'comments':       comments,
        'confirmed':      confirmed,
        'confirm_count':  report.confirm_count(),
        'cat_icons':      WATCH_CAT_ICONS,
        'sev_colors':     SEVERITY_COLORS,
    })


@login_required
def watch_confirm(request, pk):
    report = get_object_or_404(WatchReport, pk=pk)
    obj, created = WatchConfirm.objects.get_or_create(user=request.user, report=report)
    if not created:
        obj.delete()
        confirmed = False
    else:
        confirmed = True
    return JsonResponse({'confirmed': confirmed, 'count': report.confirm_count()})


@login_required
def watch_resolve(request, pk):
    report = get_object_or_404(WatchReport, pk=pk, user=request.user)
    report.is_resolved = not report.is_resolved
    report.save()
    return JsonResponse({'resolved': report.is_resolved})


@login_required
def watch_delete(request, pk):
    report = get_object_or_404(WatchReport, pk=pk, user=request.user)
    report.is_active = False
    report.save()
    return redirect('/community/community-watch/')


# ── NOTIFICATIONS & SEARCH ─────────────────────────────────────────────────────
NOTIF_ICONS = {
    'like':     '❤️',  'comment':  '💬', 'confirm':  '🚨',
    'rsvp':     '📅',  'signup':   '🤝', 'vote':     '⭐',
    'interest': '🛒',  'follow':   '🏫', 'system':   '🔔',
}


@login_required
def notifications_page(request):
    notifs = Notification.objects.filter(user=request.user)
    unread_count = notifs.filter(is_read=False).count()
    notifs.filter(is_read=False).update(is_read=True)
    return render(request, 'community/notifications.html', {
        'notifs':       notifs[:50],
        'unread_count': unread_count,
        'notif_icons':  NOTIF_ICONS,
    })


@login_required
def notif_mark_all_read(request):
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return JsonResponse({'ok': True})


def community_search(request):
    q       = request.GET.get('q', '').strip()
    pincode = request.GET.get('pincode', '').strip()
    results = []

    if q or pincode:
        from django.db.models import Q

        def _filter(qs, title_field, desc_field='description', pin_field='pincode'):
            f = Q()
            if q:
                f &= (Q(**{f'{title_field}__icontains': q}) |
                      Q(**{f'{desc_field}__icontains': q}))
            if pincode and pin_field:
                try:
                    f &= Q(**{f'{pin_field}__icontains': pincode})
                except Exception:
                    pass
            return qs.filter(f) if f else qs.none()

        # Family Stories
        for s in _filter(FamilyStory.objects.filter(is_active=True), 'title')[:5]:
            results.append({'type': 'Family Story', 'icon': '📸', 'title': s.title,
                            'desc': s.content[:80], 'url': f'/community/family-stories/{s.pk}/',
                            'time': s.created_at})
        # Student Success
        for s in _filter(StudentSuccess.objects.filter(is_active=True), 'title')[:5]:
            results.append({'type': 'Student Success', 'icon': '🎓', 'title': s.title,
                            'desc': s.story[:80], 'url': f'/community/student-success/{s.pk}/',
                            'time': s.created_at})
        # Kids Corner
        for s in _filter(KidsPost.objects.filter(is_active=True), 'title', 'content')[:5]:
            results.append({'type': 'Kids Corner', 'icon': '🧒', 'title': s.title,
                            'desc': s.content[:80], 'url': f'/community/kids-corner/{s.pk}/',
                            'time': s.created_at})
        # Parenting
        for s in _filter(ParentingPost.objects.filter(is_active=True), 'title', 'content')[:5]:
            results.append({'type': 'Parenting', 'icon': '👨‍👩‍👧', 'title': s.title,
                            'desc': s.content[:80], 'url': f'/community/parenting/{s.pk}/',
                            'time': s.created_at})
        # Grandparents
        for s in _filter(GrandparentStory.objects.filter(is_active=True), 'title', 'story')[:5]:
            results.append({'type': 'Grandparents', 'icon': '👴', 'title': s.title,
                            'desc': s.story[:80], 'url': f'/community/grandparents-archive/{s.pk}/',
                            'time': s.created_at})
        # Local Heroes
        for s in _filter(LocalHero.objects.filter(is_active=True), 'name', 'story')[:5]:
            results.append({'type': 'Local Hero', 'icon': '🦸', 'title': s.name,
                            'desc': s.story[:80], 'url': f'/community/local-heroes/{s.pk}/',
                            'time': s.created_at})
        # Events
        for s in _filter(CommunityEvent.objects.filter(is_active=True), 'title')[:5]:
            results.append({'type': 'Community Event', 'icon': '📅', 'title': s.title,
                            'desc': s.description[:80], 'url': f'/community/events/{s.pk}/',
                            'time': s.created_at})
        # Volunteer
        for s in _filter(VolunteerActivity.objects.filter(is_active=True), 'title')[:5]:
            results.append({'type': 'Volunteer', 'icon': '🤝', 'title': s.title,
                            'desc': s.description[:80], 'url': f'/community/volunteer/{s.pk}/',
                            'time': s.created_at})
        # Business Stories
        for s in _filter(BusinessStory.objects.filter(is_active=True), 'title', 'content')[:5]:
            results.append({'type': 'Business Story', 'icon': '🏪', 'title': s.title,
                            'desc': s.content[:80], 'url': f'/community/business-stories/{s.pk}/',
                            'time': s.created_at})
        # Hall of Fame
        for s in _filter(HallOfFameEntry.objects.filter(is_active=True), 'nominee_name', 'description')[:5]:
            results.append({'type': 'Hall of Fame', 'icon': '🏆', 'title': s.nominee_name,
                            'desc': s.description[:80], 'url': f'/community/hall-of-fame/{s.pk}/',
                            'time': s.created_at})
        # Marketplace
        for s in _filter(MarketplaceListing.objects.filter(is_active=True), 'title')[:5]:
            results.append({'type': 'Marketplace', 'icon': '🛒', 'title': s.title,
                            'desc': s.description[:80], 'url': f'/community/marketplace/{s.pk}/',
                            'time': s.created_at})
        # Watch
        for s in _filter(WatchReport.objects.filter(is_active=True), 'title', 'description', 'pincode')[:5]:
            results.append({'type': 'Community Watch', 'icon': '👁️', 'title': s.title,
                            'desc': s.description[:80], 'url': f'/community/community-watch/{s.pk}/',
                            'time': s.created_at})

        results.sort(key=lambda x: x['time'], reverse=True)

    return render(request, 'community/search.html', {
        'results': results,
        'q':       q,
        'pincode': pincode,
        'count':   len(results),
    })


# ── BIRTHDAY GIFT REDIRECT ─────────────────────────────────────────────────────
@login_required
def birthday_gift_redirect(request, member_pk):
    """
    Security-checked redirect to the voucher marketplace pre-filled for a
    birthday family member. Returns 403 if the member does not belong to this user.
    """
    from django.http import HttpResponseForbidden
    member = get_object_or_404(FamilyMember, pk=member_pk)
    if member.creator_id != request.user.pk:
        return HttpResponseForbidden('You are not allowed to gift this family member.')
    from urllib.parse import urlencode
    params = urlencode({'gift_for': member.pk, 'gift_name': member.name})
    return redirect(f'/vouchers/marketplace/?{params}')
