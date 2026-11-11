from jobs.person_names import valid_person_name
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, get_user_model
from django.contrib import messages
from django.utils import timezone
from django.db.models import Count, Q
from django.db import transaction
from django.http import JsonResponse

from .models import (
    Institution, PlacementOfficer, Department, HOD, Student,
    CampusCompany, Opportunity, OpportunityPincode, OpportunityShare,
    OpportunityDocument, OpportunityQuestion,
    Application, ApplicationStatusHistory, ApplicationDocument, ApplicationAnswer,
    Interview, OfferLetter,
    CampusNotification, AuditLog,
)


# ── HELPERS ──────────────────────────────────────────────────────────────────

def get_po(user):
    try:
        return user.placement_officer
    except PlacementOfficer.DoesNotExist:
        return None

def get_hod(user):
    try:
        return user.hod_profile
    except HOD.DoesNotExist:
        return None

def get_student(user):
    try:
        return user.student_profile
    except Student.DoesNotExist:
        return None

def get_company(user):
    try:
        return user.campus_company
    except CampusCompany.DoesNotExist:
        return None

def notify(user, notif_type, title, message='', link=''):
    CampusNotification.objects.create(
        user=user, notif_type=notif_type,
        title=title, message=message, link=link,
    )

def audit(user, action, model_name='', object_id=None, detail='', request=None):
    ip = None
    if request:
        ip = request.META.get('REMOTE_ADDR')
    AuditLog.objects.create(
        user=user, action=action,
        model_name=model_name, object_id=object_id,
        detail=detail, ip=ip,
    )

def set_app_status(application, new_status, changed_by, note=''):
    application.status = new_status
    application.save(update_fields=['status', 'updated_at'])
    ApplicationStatusHistory.objects.create(
        application=application, status=new_status,
        changed_by=changed_by, note=note,
    )
    # notify student
    notify(
        application.student.user,
        'status_change',
        f'Application status updated: {application.get_status_display()}',
        note,
        f'/campus/student/application/{application.pk}/',
    )


# ── PUBLIC ────────────────────────────────────────────────────────────────────

def campus_home(request):
    total_institutions = Institution.objects.filter(status='verified').count()
    total_companies    = CampusCompany.objects.filter(status='verified').count()
    total_opportunities = Opportunity.objects.filter(status='published').count()
    total_applications = Application.objects.count()
    recent_opportunities = Opportunity.objects.filter(status='published').select_related('company')[:6]

    role = None
    if request.user.is_authenticated:
        if get_po(request.user):
            role = 'po'
        elif get_hod(request.user):
            role = 'hod'
        elif get_student(request.user):
            role = 'student'
        elif get_company(request.user):
            role = 'company'

    return render(request, 'campus/home.html', {
        'total_institutions':    total_institutions,
        'total_companies':       total_companies,
        'total_opportunities':   total_opportunities,
        'total_applications':    total_applications,
        'recent_opportunities':  recent_opportunities,
        'role':                  role,
    })


def institution_detail(request, pk):
    inst = get_object_or_404(Institution, pk=pk, status='verified')
    departments = inst.departments.filter(is_active=True)
    return render(request, 'campus/institution_detail.html', {
        'institution': inst,
        'departments': departments,
    })


def opportunity_detail(request, pk):
    opp = get_object_or_404(Opportunity, pk=pk, status='published')
    already_applied = False
    if request.user.is_authenticated:
        student = get_student(request.user)
        if student:
            already_applied = Application.objects.filter(student=student, opportunity=opp).exists()
    return render(request, 'campus/opportunity_detail.html', {
        'opportunity':     opp,
        'already_applied': already_applied,
        'pincodes':        opp.target_pincodes.all(),
    })


# ── INSTITUTION REGISTRATION ─────────────────────────────────────────────────

@login_required
def campus_send_otp(request):
    if request.method != 'POST':
        return JsonResponse({'success': False})
    import json, random, requests as _req
    try:
        data = json.loads(request.body)
        phone = data.get('phone', '').strip()
    except Exception:
        phone = request.POST.get('phone', '').strip()
    if not phone or len(phone) != 10 or not phone.isdigit():
        return JsonResponse({'success': False, 'error': 'Enter a valid 10-digit number.'})
    otp = str(random.randint(100000, 999999))
    from django.conf import settings as _s
    api_key  = getattr(_s, 'TWO_FACTOR_API_KEY', '')
    template = getattr(_s, 'TWO_FACTOR_OTP_TEMPLATE', '')
    if not api_key:
        print(f'\n[CAMPUS OTP] Phone: {phone}  OTP: {otp}\n', flush=True)
    else:
        url = f'https://2factor.in/API/V1/{api_key}/SMS/{phone}/{otp}/{template}'
        try:
            resp   = _req.get(url, timeout=10)
            result = resp.json()
            if result.get('Status') != 'Success':
                return JsonResponse({'success': False, 'error': result.get('Details', 'SMS failed.')})
        except Exception:
            return JsonResponse({'success': False, 'error': 'SMS service unavailable.'})
    request.session['campus_otp']          = otp
    request.session['campus_otp_phone']    = phone
    request.session['campus_otp_verified'] = False
    request.session.modified = True
    return JsonResponse({'success': True})


def campus_verify_otp(request):
    if request.method != 'POST':
        return JsonResponse({'success': False})
    import json
    data    = json.loads(request.body)
    entered = data.get('otp', '').strip()
    stored  = request.session.get('campus_otp', '')
    if not stored:
        return JsonResponse({'success': False, 'error': 'OTP expired. Resend.'})
    if entered == stored:
        request.session['campus_otp_verified'] = True
        request.session.pop('campus_otp', None)
        request.session.modified = True
        return JsonResponse({'success': True})
    return JsonResponse({'success': False, 'error': 'Wrong OTP. Try again.'})


def institution_register(request):
    if request.method == 'POST':
        phone = request.POST.get('phone', '').strip()
        otp_verified = request.session.get('campus_otp_verified') and request.session.get('campus_otp_phone') == phone
        if not otp_verified:
            messages.error(request, 'Please verify the institution phone number with OTP before submitting.')
            return render(request, 'campus/institution_register.html', {'type_choices': Institution.TYPE_CHOICES, 'otp_error': True})
        inst = Institution.objects.create(
            name             = request.POST.get('name', '').strip(),
            institution_type = ','.join(request.POST.getlist('institution_type')) or 'other',
            affiliation      = request.POST.get('affiliation', '').strip(),
            address          = request.POST.get('address', '').strip(),
            pincode          = request.POST.get('pincode', '').strip(),
            city             = request.POST.get('city', '').strip(),
            district         = request.POST.get('district', '').strip(),
            state            = request.POST.get('state', '').strip(),
            phone            = phone,
            phone_verified   = True,
            email            = request.POST.get('email', '').strip(),
            website          = request.POST.get('website', '').strip(),
            status           = 'pending',
        )
        if 'logo' in request.FILES:
            inst.logo = request.FILES['logo']
            inst.save()
        PlacementOfficer.objects.create(
            user        = request.user,
            institution = inst,
            designation = request.POST.get('po_designation', '').strip(),
            phone       = request.POST.get('po_phone', '').strip(),
            phone2      = request.POST.get('po_phone2', '').strip(),
            email       = request.POST.get('po_email', '').strip(),
        )
        request.session.pop('campus_otp_verified', None)
        request.session.pop('campus_otp_phone', None)
        audit(request.user, 'institution_register', 'Institution', inst.pk, inst.name, request)
        messages.success(request, f'"{inst.name}" registered successfully! Awaiting admin verification.')
        return redirect('campus_po_dashboard')
    return render(request, 'campus/institution_register.html', {
        'type_choices': Institution.TYPE_CHOICES,
    })


# ── PLACEMENT OFFICER ─────────────────────────────────────────────────────────

@login_required
def po_dashboard(request):
    po = get_po(request.user)
    if not po:
        return redirect('campus_institution_register')
    inst = po.institution
    departments  = inst.departments.filter(is_active=True).annotate(student_count=Count('students'))
    new_opps     = Opportunity.objects.filter(
        status='published',
        target_pincodes__pincode=inst.pincode,
    ).exclude(shares__institution=inst).distinct()[:10]
    shared_opps  = OpportunityShare.objects.filter(institution=inst).select_related('opportunity', 'department').order_by('-shared_at')[:10]
    applications = Application.objects.filter(
        student__institution=inst
    ).select_related('student__user', 'opportunity').order_by('-applied_at')[:20]
    stats = {
        'students':     inst.students.filter(is_active=True).count(),
        'departments':  departments.count(),
        'new_opps':     new_opps.count(),
        'applied':      applications.count(),
        'selected':     Application.objects.filter(student__institution=inst, status='selected').count(),
        'placed':       Application.objects.filter(student__institution=inst, status='placed').count(),
    }
    notifs = CampusNotification.objects.filter(user=request.user, is_read=False)[:5]
    return render(request, 'campus/po_dashboard.html', {
        'po': po, 'institution': inst,
        'departments': departments, 'new_opps': new_opps,
        'shared_opps': shared_opps, 'applications': applications,
        'stats': stats, 'notifs': notifs,
    })


@login_required
def po_departments(request):
    po = get_po(request.user)
    if not po:
        return redirect('campus_institution_register')
    departments = po.institution.departments.filter(is_active=True).annotate(
        hod_count=Count('hods'),
        student_count=Count('students'),
    )
    return render(request, 'campus/po_departments.html', {
        'po': po, 'institution': po.institution, 'departments': departments,
    })


@login_required
def po_department_add(request):
    po = get_po(request.user)
    if not po:
        return redirect('campus_institution_register')
    if request.method == 'POST':
        Department.objects.create(
            institution    = po.institution,
            name           = request.POST.get('name', '').strip(),
            code           = request.POST.get('code', '').strip(),
            courses        = request.POST.get('courses', '').strip(),
            year_structure = request.POST.get('year_structure', '').strip(),
        )
        messages.success(request, 'Department added.')
        return redirect('campus_po_departments')
    return render(request, 'campus/po_department_add.html', {'po': po})


@login_required
def po_hod_add(request):
    from django.contrib.auth import get_user_model
    import random, string
    po = get_po(request.user)
    if not po:
        return redirect('campus_institution_register')
    departments = po.institution.departments.filter(is_active=True)
    error = None
    if request.method == 'POST':
        UserModel = get_user_model()
        full_name  = request.POST.get('full_name', '').strip()
        phone      = request.POST.get('phone', '').strip()
        dept_id    = request.POST.get('department_id', '').strip()
        designation = request.POST.get('designation', 'HOD').strip()
        if not all([full_name, phone, dept_id]):
            error = 'All fields required.'
        elif UserModel.objects.filter(phone=phone).exists():
            error = 'This phone is already registered.'
        else:
            dept     = get_object_or_404(Department, pk=dept_id, institution=po.institution)
            password = ''.join(random.choices(string.digits, k=6))
            parts    = full_name.split(' ', 1)
            user     = UserModel.objects.create_user(
                username   = phone,
                password   = password,
                first_name = parts[0],
                last_name  = parts[1] if len(parts) > 1 else '',
                phone      = phone,
            )
            HOD.objects.create(user=user, department=dept, phone=phone)
            audit(request.user, 'hod_added', 'HOD', user.pk, full_name, request)
            messages.success(request, f'HOD {full_name} added. Login: {phone} / Password: {password}')
            return redirect('campus_po_departments')
    return render(request, 'campus/po_hod_add.html', {
        'po': po, 'departments': departments, 'error': error,
    })


@login_required
def po_students(request):
    po = get_po(request.user)
    if not po:
        return redirect('campus_institution_register')
    dept_id = request.GET.get('dept')
    students = Student.objects.filter(institution=po.institution, is_active=True).select_related('user', 'department')
    if dept_id:
        students = students.filter(department_id=dept_id)
    departments = po.institution.departments.filter(is_active=True)
    return render(request, 'campus/po_students.html', {
        'po': po, 'students': students, 'departments': departments, 'dept_id': dept_id,
    })


@login_required
def po_student_add(request):
    from django.contrib.auth import get_user_model
    import random, string
    po = get_po(request.user)
    if not po:
        return redirect('campus_institution_register')
    departments = po.institution.departments.filter(is_active=True)
    error = None
    if request.method == 'POST':
        UserModel  = get_user_model()
        full_name  = request.POST.get('full_name', '').strip()
        phone      = request.POST.get('phone', '').strip()
        dept_id    = request.POST.get('department_id', '').strip()
        roll       = request.POST.get('roll_number', '').strip()
        course     = request.POST.get('course', '').strip()
        year       = request.POST.get('year', '1')
        if not all([full_name, phone, dept_id]):
            error = 'Name, phone and department are required.'
        elif UserModel.objects.filter(phone=phone).exists():
            error = 'This phone is already registered.'
        else:
            dept     = get_object_or_404(Department, pk=dept_id, institution=po.institution)
            password = ''.join(random.choices(string.digits, k=6))
            parts    = full_name.split(' ', 1)
            user     = UserModel.objects.create_user(
                username   = phone,
                password   = password,
                first_name = parts[0],
                last_name  = parts[1] if len(parts) > 1 else '',
                phone      = phone,
            )
            Student.objects.create(
                user=user, institution=po.institution, department=dept,
                roll_number=roll, course=course, year=year,
            )
            audit(request.user, 'student_added', 'Student', user.pk, full_name, request)
            messages.success(request, f'Student {full_name} added. Login: {phone} / Password: {password}')
            return redirect('campus_po_students')
    return render(request, 'campus/po_student_add.html', {
        'po': po, 'departments': departments, 'error': error,
        'year_choices': Student.YEAR_CHOICES,
    })


@login_required
def po_opportunities(request):
    po = get_po(request.user)
    if not po:
        return redirect('campus_institution_register')
    new_opps = Opportunity.objects.filter(
        status='published',
        target_pincodes__pincode=po.institution.pincode,
    ).exclude(shares__institution=po.institution).distinct()
    shared_opps = OpportunityShare.objects.filter(
        institution=po.institution
    ).select_related('opportunity__company', 'department').order_by('-shared_at')
    return render(request, 'campus/po_opportunities.html', {
        'po': po, 'new_opps': new_opps, 'shared_opps': shared_opps,
    })


@login_required
def po_share_opportunity(request, pk):
    po = get_po(request.user)
    if not po:
        return redirect('campus_institution_register')
    opp  = get_object_or_404(Opportunity, pk=pk, status='published')
    departments = po.institution.departments.filter(is_active=True)
    if request.method == 'POST':
        dept_ids = request.POST.getlist('department_ids')
        note     = request.POST.get('note', '').strip()
        if not dept_ids:
            # share to all
            dept_ids = list(departments.values_list('pk', flat=True))
        for dept_id in dept_ids:
            dept = departments.filter(pk=dept_id).first()
            if dept:
                OpportunityShare.objects.get_or_create(
                    opportunity=opp, institution=po.institution, department=dept,
                    defaults={'shared_by': request.user, 'note': note},
                )
                # notify HODs in this dept
                for hod in dept.hods.filter(is_active=True):
                    notify(hod.user, 'opportunity_shared',
                           f'New opportunity: {opp.title}',
                           f'Shared by Placement Officer. {note}',
                           f'/campus/student/opportunities/{opp.pk}/')
        audit(request.user, 'opportunity_shared', 'Opportunity', opp.pk, opp.title, request)
        messages.success(request, f'Opportunity shared with selected departments.')
        return redirect('campus_po_opportunities')
    return render(request, 'campus/po_share.html', {
        'po': po, 'opportunity': opp, 'departments': departments,
    })


@login_required
def po_applications(request):
    po = get_po(request.user)
    if not po:
        return redirect('campus_institution_register')
    applications = Application.objects.filter(
        student__institution=po.institution
    ).select_related('student__user', 'student__department', 'opportunity__company').order_by('-applied_at')
    status_filter = request.GET.get('status', '')
    if status_filter:
        applications = applications.filter(status=status_filter)
    return render(request, 'campus/po_applications.html', {
        'po': po, 'applications': applications,
        'status_choices': Application.STATUS_CHOICES,
        'status_filter':  status_filter,
    })


# ── HOD ───────────────────────────────────────────────────────────────────────

@login_required
def hod_dashboard(request):
    hod = get_hod(request.user)
    if not hod:
        messages.error(request, 'No HOD profile found.')
        return redirect('campus_home')
    dept = hod.department
    inst = dept.institution
    shared_opps = OpportunityShare.objects.filter(
        institution=inst, department=dept
    ).select_related('opportunity__company').order_by('-shared_at')
    students = Student.objects.filter(department=dept, is_active=True).select_related('user')
    applications = Application.objects.filter(
        student__department=dept
    ).select_related('student__user', 'opportunity').order_by('-applied_at')[:20]
    stats = {
        'students':   students.count(),
        'shared':     shared_opps.count(),
        'applied':    Application.objects.filter(student__department=dept).count(),
        'selected':   Application.objects.filter(student__department=dept, status='selected').count(),
    }
    return render(request, 'campus/hod_dashboard.html', {
        'hod': hod, 'department': dept, 'institution': inst,
        'shared_opps': shared_opps, 'students': students,
        'applications': applications, 'stats': stats,
    })


@login_required
def hod_share_students(request, pk):
    hod = get_hod(request.user)
    if not hod:
        return redirect('campus_home')
    opp = get_object_or_404(Opportunity, pk=pk, status='published')
    students = Student.objects.filter(department=hod.department, is_active=True, is_available=True).select_related('user')
    if request.method == 'POST':
        student_ids = request.POST.getlist('student_ids')
        if not student_ids:
            student_ids = list(students.values_list('pk', flat=True))
        for sid in student_ids:
            st = students.filter(pk=sid).first()
            if st:
                notify(st.user, 'opportunity_shared',
                       f'New opportunity: {opp.title}',
                       f'Shared by HOD. Apply before {opp.apply_end or "deadline"}.',
                       f'/campus/student/opportunities/{opp.pk}/')
        messages.success(request, f'Opportunity notified to {len(student_ids)} student(s).')
        return redirect('campus_hod_dashboard')
    return render(request, 'campus/hod_share.html', {
        'hod': hod, 'opportunity': opp, 'students': students,
    })


# ── STUDENT ───────────────────────────────────────────────────────────────────

@login_required
def student_register(request):
    error = None
    institutions = Institution.objects.filter(status='verified').order_by('name')
    if request.method == 'POST':
        inst_id  = (request.POST.get('institution_id') or request.POST.get('institution', '')).strip()
        dept_id  = (request.POST.get('department_id') or request.POST.get('department', '')).strip()
        roll     = request.POST.get('roll_number', '').strip()
        course   = request.POST.get('course', '').strip()
        year     = request.POST.get('year', '1')
        skills   = request.POST.get('skills', '').strip()
        if not all([inst_id, dept_id]):
            error = 'Please select institution and department.'
        elif hasattr(request.user, 'student_profile'):
            error = 'You are already registered as a student.'
        else:
            inst = get_object_or_404(Institution, pk=inst_id, status='verified')
            dept = get_object_or_404(Department, pk=dept_id, institution=inst)
            Student.objects.create(
                user=request.user, institution=inst, department=dept,
                roll_number=roll, course=course, year=year, skills=skills,
            )
            if 'resume' in request.FILES:
                st = request.user.student_profile
                st.resume = request.FILES['resume']
                st.save()
            messages.success(request, 'Student profile created!')
            return redirect('campus_student_dashboard')
    preset_inst_id = request.session.get('campus_signup_inst_id', '')
    from .models import Department as Dept
    departments = Dept.objects.filter(institution__status='verified', is_active=True).select_related('institution')
    return render(request, 'campus/student_register.html', {
        'institutions': institutions, 'departments': departments, 'error': error,
        'year_choices': Student.YEAR_CHOICES,
        'preset_inst_id': preset_inst_id,
    })


@login_required
def student_dashboard(request):
    student = get_student(request.user)
    if not student:
        return redirect('campus_student_register')
    applications = Application.objects.filter(student=student).select_related('opportunity__company').order_by('-applied_at')
    shared_opps  = Opportunity.objects.filter(
        status='published',
        shares__institution=student.institution,
        shares__department=student.department,
    ).exclude(applications__student=student).distinct()[:10]
    notifs = CampusNotification.objects.filter(user=request.user, is_read=False)[:5]
    stats = {
        'applied':    applications.count(),
        'shortlisted': applications.filter(status='shortlisted').count(),
        'selected':   applications.filter(status__in=['selected','placed','internship']).count(),
        'rejected':   applications.filter(status='rejected').count(),
    }
    return render(request, 'campus/student_dashboard.html', {
        'student': student, 'applications': applications,
        'shared_opps': shared_opps, 'notifs': notifs, 'stats': stats,
    })


@login_required
def student_opportunities(request):
    student = get_student(request.user)
    if not student:
        return redirect('campus_student_register')
    opps = Opportunity.objects.filter(
        status='published',
        shares__institution=student.institution,
    ).distinct().select_related('company')
    type_filter = request.GET.get('type', '')
    if type_filter:
        opps = opps.filter(opp_type=type_filter)
    applied_ids = set(Application.objects.filter(student=student).values_list('opportunity_id', flat=True))
    return render(request, 'campus/student_opportunities.html', {
        'student': student, 'opportunities': opps,
        'type_choices': Opportunity.TYPE_CHOICES,
        'type_filter': type_filter, 'applied_ids': applied_ids,
    })


@login_required
def student_apply(request, pk):
    student = get_student(request.user)
    if not student:
        return redirect('campus_student_register')
    opp = get_object_or_404(Opportunity, pk=pk, status='published')
    if Application.objects.filter(student=student, opportunity=opp).exists():
        messages.info(request, 'You have already applied.')
        return redirect('campus_student_applications')

    eligible, reason = student.is_eligible_for(opp)
    required_docs = opp.required_documents.all()
    questions     = opp.questions.all()

    if request.method == 'POST':
        if not eligible:
            messages.error(request, f'You are not eligible: {reason}')
            return redirect('campus_student_opportunities')
        app = Application.objects.create(student=student, opportunity=opp, status='applied')
        if 'resume' in request.FILES:
            app.resume = request.FILES['resume']
            app.save()
        # Save uploaded documents
        doc_names  = request.POST.getlist('doc_name')
        doc_files  = request.FILES.getlist('doc_file')
        for i, f in enumerate(doc_files):
            name = doc_names[i].strip() if i < len(doc_names) else f.name
            ApplicationDocument.objects.create(application=app, document_name=name, file=f)
        # Save question answers
        for q in questions:
            ans = request.POST.get(f'question_{q.pk}', '').strip()
            if ans:
                ApplicationAnswer.objects.create(application=app, question=q, answer=ans)
        ApplicationStatusHistory.objects.create(
            application=app, status='applied', changed_by=request.user,
        )
        notify(opp.company.user, 'application',
               f'New application: {student.user.get_full_name()}',
               f'Applied for {opp.title}',
               f'/campus/company/opportunities/{opp.pk}/applications/')
        audit(request.user, 'student_applied', 'Application', app.pk, opp.title, request)
        messages.success(request, f'Applied for "{opp.title}" successfully!')
        return redirect('campus_student_applications')
    return render(request, 'campus/student_apply_confirm.html', {
        'student': student, 'opportunity': opp,
        'eligible': eligible, 'reason': reason,
        'required_docs': required_docs, 'questions': questions,
    })


@login_required
def student_applications(request):
    student = get_student(request.user)
    if not student:
        return redirect('campus_student_register')
    applications = Application.objects.filter(student=student).select_related(
        'opportunity__company'
    ).prefetch_related('history', 'interviews').order_by('-applied_at')
    return render(request, 'campus/student_applications.html', {
        'student': student, 'applications': applications,
    })


@login_required
def application_detail(request, pk):
    student = get_student(request.user)
    app = get_object_or_404(Application, pk=pk)
    # access check — reject if user is not a student OR does not own this application
    if student is None or app.student != student:
        messages.error(request, 'Access denied.')
        return redirect('campus_student_applications')
    history   = app.history.all()
    interviews = app.interviews.all()
    return render(request, 'campus/application_detail.html', {
        'application': app, 'history': history, 'interviews': interviews,
    })


# ── COMPANY ───────────────────────────────────────────────────────────────────

@login_required
def company_register(request):
    if hasattr(request.user, 'campus_company'):
        return redirect('campus_company_dashboard')
    error = None
    if request.method == 'POST':
        company = CampusCompany.objects.create(
            user           = request.user,
            company_name   = request.POST.get('company_name', '').strip(),
            industry       = request.POST.get('industry', '').strip(),
            description    = request.POST.get('description', '').strip(),
            contact_person = request.POST.get('contact_person', '').strip(),
            designation    = request.POST.get('designation', '').strip(),
            phone          = request.POST.get('phone', '').strip(),
            email          = request.POST.get('email', '').strip(),
            website        = request.POST.get('website', '').strip(),
            address        = request.POST.get('address', '').strip(),
            pincode        = request.POST.get('pincode', '').strip(),
            status         = 'pending',
        )
        if 'logo' in request.FILES:
            company.logo = request.FILES['logo']
            company.save()
        audit(request.user, 'company_register', 'CampusCompany', company.pk, company.company_name, request)
        messages.success(request, 'Company registered! Awaiting verification.')
        return redirect('campus_company_dashboard')
    return render(request, 'campus/company_register.html', {'error': error})


@login_required
def company_dashboard(request):
    company = get_company(request.user)
    if not company:
        return redirect('campus_company_register')
    opportunities = company.opportunities.all()
    recent_apps   = Application.objects.filter(
        opportunity__company=company
    ).select_related('student__user', 'opportunity').order_by('-applied_at')[:20]
    stats = {
        'opportunities': opportunities.count(),
        'published':     opportunities.filter(status='published').count(),
        'applications':  Application.objects.filter(opportunity__company=company).count(),
        'shortlisted':   Application.objects.filter(opportunity__company=company, status='shortlisted').count(),
        'selected':      Application.objects.filter(opportunity__company=company, status__in=['selected','placed']).count(),
    }
    notifs = CampusNotification.objects.filter(user=request.user, is_read=False)[:5]
    return render(request, 'campus/company_dashboard.html', {
        'company': company, 'opportunities': opportunities,
        'recent_apps': recent_apps, 'stats': stats, 'notifs': notifs,
    })


@login_required
def opportunity_post(request):
    company = get_company(request.user)
    if not company:
        return redirect('campus_company_register')
    if company.status != 'verified':
        messages.error(request, 'Your company is pending verification. You can post opportunities after approval.')
        return redirect('campus_company_dashboard')
    if request.method == 'POST':
        def _decimal(val):
            try:
                v = val.strip()
                return float(v) if v else None
            except Exception:
                return None

        opp = Opportunity.objects.create(
            company             = company,
            title               = request.POST.get('title', '').strip(),
            opp_type            = request.POST.get('opp_type', 'internship'),
            description         = request.POST.get('description', '').strip(),
            openings            = int(request.POST.get('openings', 1) or 1),
            dept_eligibility    = request.POST.get('dept_eligibility', '').strip(),
            year_eligibility    = request.POST.get('year_eligibility', '').strip(),
            skills_required     = request.POST.get('skills_required', '').strip(),
            qualification       = request.POST.get('qualification', '').strip(),
            experience          = request.POST.get('experience', 'Fresher').strip(),
            salary              = request.POST.get('salary', '').strip(),
            location            = request.POST.get('location', '').strip(),
            work_mode           = request.POST.get('work_mode', 'onsite'),
            apply_start         = request.POST.get('apply_start') or None,
            apply_end           = request.POST.get('apply_end') or None,
            interview_process   = request.POST.get('interview_process', '').strip(),
            contact_person      = request.POST.get('contact_person', '').strip(),
            status              = request.POST.get('status', 'draft'),
            min_cgpa            = _decimal(request.POST.get('min_cgpa', '')),
            no_arrears_required = request.POST.get('no_arrears_required') == '1',
            min_tenth_percent   = _decimal(request.POST.get('min_tenth_percent', '')),
            min_twelfth_percent = _decimal(request.POST.get('min_twelfth_percent', '')),
        )
        if 'attachment' in request.FILES:
            opp.attachment = request.FILES['attachment']
            opp.save()
        # Save job location pincode
        location_pincode = request.POST.get('location_pincode', '').strip()
        if location_pincode and len(location_pincode) == 6 and location_pincode.isdigit():
            OpportunityPincode.objects.get_or_create(opportunity=opp, pincode=location_pincode)
        # Save selected institutions
        selected_ids = request.POST.getlist('target_institutions')
        if selected_ids:
            opp.target_institutions.set(Institution.objects.filter(pk__in=selected_ids, status='verified'))
        # Save required documents
        doc_names = request.POST.getlist('doc_name')
        doc_descs = request.POST.getlist('doc_desc')
        doc_req   = request.POST.getlist('doc_required')
        for i, name in enumerate(doc_names):
            name = name.strip()
            if name:
                OpportunityDocument.objects.create(
                    opportunity=opp,
                    name=name,
                    description=doc_descs[i].strip() if i < len(doc_descs) else '',
                    is_required=str(i) in doc_req,
                    order=i,
                )
        # Save questions
        q_texts = request.POST.getlist('q_text')
        q_types = request.POST.getlist('q_type')
        q_req   = request.POST.getlist('q_required')
        for i, q in enumerate(q_texts):
            q = q.strip()
            if q:
                OpportunityQuestion.objects.create(
                    opportunity=opp,
                    question=q,
                    question_type=q_types[i] if i < len(q_types) else 'yesno',
                    is_required=str(i) in q_req,
                    order=i,
                )
        # Notify POs of selected colleges if published
        if opp.status == 'published':
            _notify_matching_pos(opp)
        audit(request.user, 'opportunity_posted', 'Opportunity', opp.pk, opp.title, request)
        messages.success(request, f'Opportunity "{opp.title}" created.')
        return redirect('campus_company_dashboard')
    institutions = Institution.objects.filter(status='verified').order_by('name')
    return render(request, 'campus/opportunity_post.html', {
        'company': company,
        'type_choices':      Opportunity.TYPE_CHOICES,
        'work_mode_choices': Opportunity.WORK_MODE_CHOICES,
        'institutions':      institutions,
    })


def _notify_matching_pos(opp):
    institutions = opp.target_institutions.filter(status='verified')
    for inst in institutions:
        for po in inst.placement_officers.filter(is_active=True):
            notify(po.user, 'new_opportunity',
                   f'New opportunity: {opp.title}',
                   f'From {opp.company.company_name}. Openings: {opp.openings}',
                   f'/campus/po/opportunities/')


@login_required
def opportunity_edit(request, pk):
    company = get_company(request.user)
    if not company:
        return redirect('campus_company_register')
    opp = get_object_or_404(Opportunity, pk=pk, company=company)
    if request.method == 'POST':
        opp.title            = request.POST.get('title', opp.title).strip()
        opp.description      = request.POST.get('description', opp.description).strip()
        opp.openings         = int(request.POST.get('openings', opp.openings) or opp.openings)
        opp.skills_required  = request.POST.get('skills_required', opp.skills_required).strip()
        opp.salary           = request.POST.get('salary', opp.salary).strip()
        opp.apply_end        = request.POST.get('apply_end') or opp.apply_end
        opp.status           = request.POST.get('status', opp.status)
        opp.save()
        messages.success(request, 'Opportunity updated.')
        return redirect('campus_company_dashboard')
    return render(request, 'campus/opportunity_edit.html', {
        'company': company, 'opportunity': opp,
        'type_choices':      Opportunity.TYPE_CHOICES,
        'work_mode_choices': Opportunity.WORK_MODE_CHOICES,
        'status_choices':    Opportunity.STATUS_CHOICES,
    })


@login_required
def company_applications(request, pk):
    company = get_company(request.user)
    if not company:
        return redirect('campus_company_register')
    opp  = get_object_or_404(Opportunity, pk=pk, company=company)
    apps = opp.applications.select_related(
        'student__user', 'student__department', 'student__institution'
    ).order_by('-applied_at')
    status_filter = request.GET.get('status', '')
    if status_filter:
        apps = apps.filter(status=status_filter)
    return render(request, 'campus/company_applications.html', {
        'company': company, 'opportunity': opp, 'applications': apps,
        'status_choices': Application.STATUS_CHOICES,
        'status_filter':  status_filter,
    })


@login_required
def update_app_status(request, pk):
    company = get_company(request.user)
    if not company or request.method != 'POST':
        return redirect('campus_company_dashboard')
    app        = get_object_or_404(Application, pk=pk, opportunity__company=company)
    new_status = request.POST.get('status', '').strip()
    note       = request.POST.get('note', '').strip()
    valid = [c[0] for c in Application.STATUS_CHOICES]
    if new_status in valid:
        app.company_note = note
        set_app_status(app, new_status, request.user, note)
        audit(request.user, 'app_status_updated', 'Application', app.pk, f'{app.student} → {new_status}', request)
    messages.success(request, 'Status updated.')
    return redirect('campus_company_applications', pk=app.opportunity.pk)


@login_required
def schedule_interview(request, pk):
    company = get_company(request.user)
    if not company or request.method != 'POST':
        return redirect('campus_company_dashboard')
    app = get_object_or_404(Application, pk=pk, opportunity__company=company)
    scheduled_at = request.POST.get('scheduled_at', '').strip()
    mode         = request.POST.get('mode', 'offline')
    location     = request.POST.get('location', '').strip()
    link         = request.POST.get('link', '').strip()
    notes        = request.POST.get('notes', '').strip()
    if scheduled_at:
        Interview.objects.create(
            application=app, scheduled_at=scheduled_at,
            mode=mode, location=location, link=link, notes=notes,
        )
        set_app_status(app, 'interview', request.user, f'Interview scheduled on {scheduled_at}')
        notify(app.student.user, 'interview',
               f'Interview scheduled for {app.opportunity.title}',
               f'Date: {scheduled_at}. Mode: {mode}. {notes}',
               f'/campus/student/application/{app.pk}/')
    messages.success(request, 'Interview scheduled.')
    return redirect('campus_company_applications', pk=app.opportunity.pk)


@login_required
def po_respond_opportunity(request, pk):
    po = get_po(request.user)
    if not po or request.method != 'POST':
        return redirect('campus_po_opportunities')
    share = get_object_or_404(OpportunityShare, pk=pk, institution=po.institution)
    action  = request.POST.get('action', '')
    po_note = request.POST.get('po_note', '').strip()
    if action in ('accept', 'reject'):
        share.status      = 'accepted' if action == 'accept' else 'rejected'
        share.po_note     = po_note
        share.responded_at = timezone.now()
        share.save()
        opp = share.opportunity
        if action == 'accept':
            # notify eligible students in this institution
            dept_filter = Q(institution=po.institution)
            if share.department:
                dept_filter &= Q(department=share.department)
            for st in Student.objects.filter(dept_filter, is_active=True, is_available=True).select_related('user'):
                eligible, _ = st.is_eligible_for(opp)
                if eligible:
                    notify(st.user, 'new_opportunity',
                           f'New opportunity: {opp.title}',
                           f'From {opp.company.company_name}. Apply before {opp.apply_end or "deadline"}.',
                           f'/campus/student/opportunities/{opp.pk}/')
            notify(opp.company.user, 'general',
                   f'{po.institution.name} accepted your opportunity',
                   f'"{opp.title}" was accepted by Placement Officer.',
                   f'/campus/company/opportunities/{opp.pk}/applications/')
            messages.success(request, 'Opportunity accepted and students notified.')
        else:
            messages.info(request, 'Opportunity rejected.')
        audit(request.user, f'po_{action}_opportunity', 'OpportunityShare', share.pk, opp.title, request)
    return redirect('campus_po_opportunities')


@login_required
def student_update_profile(request):
    student = get_student(request.user)
    if not student:
        return redirect('campus_student_register')
    if request.method == 'POST':
        def _dec(val, default=None):
            try:
                v = val.strip()
                return float(v) if v else default
            except Exception:
                return default
        def _int(val, default=None):
            try:
                v = val.strip()
                return int(v) if v else default
            except Exception:
                return default
        student.cgpa            = _dec(request.POST.get('cgpa', ''))
        student.active_arrears  = _int(request.POST.get('active_arrears', ''), 0)
        student.tenth_percent   = _dec(request.POST.get('tenth_percent', ''))
        student.twelfth_percent = _dec(request.POST.get('twelfth_percent', ''))
        student.graduation_year = _int(request.POST.get('graduation_year', ''))
        student.skills          = request.POST.get('skills', '').strip()
        student.course          = request.POST.get('course', student.course).strip()
        student.year            = request.POST.get('year', student.year)
        if 'resume' in request.FILES:
            student.resume = request.FILES['resume']
        student.save()
        messages.success(request, 'Profile updated.')
        return redirect('campus_student_dashboard')
    return render(request, 'campus/student_profile.html', {
        'student': student, 'year_choices': Student.YEAR_CHOICES,
    })


@login_required
def generate_offer_letter(request, app_pk):
    company = get_company(request.user)
    if not company or request.method != 'POST':
        return redirect('campus_company_dashboard')
    app = get_object_or_404(Application, pk=app_pk, opportunity__company=company)
    if hasattr(app, 'offer_letter'):
        messages.info(request, 'Offer letter already issued.')
        return redirect('campus_company_applications', pk=app.opportunity.pk)
    OfferLetter.objects.create(
        application    = app,
        joining_date   = request.POST.get('joining_date') or None,
        valid_until    = request.POST.get('valid_until') or None,
        salary_offered = request.POST.get('salary_offered', '').strip(),
        designation    = request.POST.get('designation', '').strip(),
        message        = request.POST.get('message', '').strip(),
        issued_by      = request.user,
    )
    set_app_status(app, 'selected', request.user, 'Offer letter issued.')
    notify(app.student.user, 'offer_letter',
           f'Offer Letter from {company.company_name}',
           f'You have been selected for {app.opportunity.title}.',
           f'/campus/student/application/{app.pk}/')
    audit(request.user, 'offer_letter_issued', 'OfferLetter', app.pk, app.opportunity.title, request)
    messages.success(request, 'Offer letter issued and student notified.')
    return redirect('campus_company_applications', pk=app.opportunity.pk)


@login_required
def view_offer_letter(request, app_pk):
    app = get_object_or_404(Application, pk=app_pk)
    student = get_student(request.user)
    company = get_company(request.user)
    if student and app.student != student:
        messages.error(request, 'Access denied.')
        return redirect('campus_student_applications')
    if company and app.opportunity.company != company:
        messages.error(request, 'Access denied.')
        return redirect('campus_company_dashboard')
    offer = get_object_or_404(OfferLetter, application=app)
    return render(request, 'campus/offer_letter.html', {
        'application': app, 'offer': offer,
    })


# ── ADMIN ─────────────────────────────────────────────────────────────────────

def _require_super_admin(request):
    return request.user.is_authenticated and request.user.is_super_admin()


def campus_admin_dashboard(request):
    if not _require_super_admin(request):
        return redirect('campus_home')
    stats = {
        'institutions': Institution.objects.count(),
        'pending_inst': Institution.objects.filter(status='pending').count(),
        'companies':    CampusCompany.objects.count(),
        'pending_comp': CampusCompany.objects.filter(status='pending').count(),
        'opportunities': Opportunity.objects.filter(status='published').count(),
        'applications': Application.objects.count(),
        'selected':     Application.objects.filter(status__in=['selected','placed']).count(),
    }
    recent_institutions = Institution.objects.order_by('-created_at')[:5]
    recent_companies    = CampusCompany.objects.order_by('-created_at')[:5]
    return render(request, 'campus/admin_dashboard.html', {
        'stats': stats,
        'recent_institutions': recent_institutions,
        'recent_companies':    recent_companies,
    })


def admin_institutions(request):
    if not _require_super_admin(request):
        return redirect('campus_home')
    status_filter = request.GET.get('status', '')
    institutions  = Institution.objects.order_by('-created_at')
    if status_filter:
        institutions = institutions.filter(status=status_filter)
    return render(request, 'campus/admin_institutions.html', {
        'institutions':   institutions,
        'status_choices': Institution.STATUS_CHOICES,
        'status_filter':  status_filter,
    })


def admin_verify_institution(request, pk):
    if not _require_super_admin(request) or request.method != 'POST':
        return redirect('campus_home')
    inst   = get_object_or_404(Institution, pk=pk)
    action = request.POST.get('action', '')
    if action == 'verify':
        inst.status      = 'verified'
        inst.verified_at = timezone.now()
        inst.verified_by = request.user
        inst.save()
        for po in inst.placement_officers.all():
            notify(po.user, 'general',
                   f'Your institution "{inst.name}" has been verified!',
                   'You can now manage departments, HODs and students.',
                   '/campus/po/dashboard/')
        messages.success(request, f'{inst.name} verified.')
    elif action == 'reject':
        inst.status = 'rejected'
        inst.save()
        messages.warning(request, f'{inst.name} rejected.')
    audit(request.user, f'institution_{action}', 'Institution', inst.pk, inst.name, request)
    return redirect('campus_admin_institutions')


def admin_companies(request):
    if not _require_super_admin(request):
        return redirect('campus_home')
    status_filter = request.GET.get('status', '')
    companies     = CampusCompany.objects.order_by('-created_at')
    if status_filter:
        companies = companies.filter(status=status_filter)
    return render(request, 'campus/admin_companies.html', {
        'companies':      companies,
        'status_choices': CampusCompany.STATUS_CHOICES,
        'status_filter':  status_filter,
    })


def admin_verify_company(request, pk):
    if not _require_super_admin(request) or request.method != 'POST':
        return redirect('campus_home')
    company = get_object_or_404(CampusCompany, pk=pk)
    action  = request.POST.get('action', '')
    if action == 'verify':
        company.status      = 'verified'
        company.verified_at = timezone.now()
        company.save()
        notify(company.user, 'general',
               f'Your company "{company.company_name}" is verified!',
               'You can now post job/internship opportunities.',
               '/campus/company/dashboard/')
        messages.success(request, f'{company.company_name} verified.')
    elif action == 'reject':
        company.status = 'rejected'
        company.save()
        messages.warning(request, f'{company.company_name} rejected.')
    audit(request.user, f'company_{action}', 'CampusCompany', company.pk, company.company_name, request)
    return redirect('campus_admin_companies')


def admin_opportunities(request):
    if not _require_super_admin(request):
        return redirect('campus_home')
    opps = Opportunity.objects.select_related('company').order_by('-created_at')
    return render(request, 'campus/admin_opportunities.html', {'opportunities': opps})


def admin_applications(request):
    if not _require_super_admin(request):
        return redirect('campus_home')
    apps = Application.objects.select_related(
        'student__user', 'opportunity__company'
    ).order_by('-applied_at')
    return render(request, 'campus/admin_applications.html', {'applications': apps})


def admin_reports(request):
    if not _require_super_admin(request):
        return redirect('campus_home')
    from django.db.models.functions import TruncMonth
    stats = {
        'total_institutions': Institution.objects.filter(status='verified').count(),
        'total_companies':    CampusCompany.objects.filter(status='verified').count(),
        'total_opportunities': Opportunity.objects.filter(status='published').count(),
        'total_applications': Application.objects.count(),
        'total_selected':     Application.objects.filter(status='selected').count(),
        'total_placed':       Application.objects.filter(status='placed').count(),
        'total_internship':   Application.objects.filter(status='internship').count(),
        'by_type':            Opportunity.objects.values('opp_type').annotate(count=Count('id')),
        'by_status':          Application.objects.values('status').annotate(count=Count('id')),
        'top_institutions':   Institution.objects.filter(status='verified').annotate(
                                  app_count=Count('students__applications')
                              ).order_by('-app_count')[:10],
        'top_companies':      CampusCompany.objects.filter(status='verified').annotate(
                                  app_count=Count('opportunities__applications')
                              ).order_by('-app_count')[:10],
    }
    return render(request, 'campus/admin_reports.html', {'stats': stats})


# ── DEDICATED CAMPUS AUTH ─────────────────────────────────────────────────────

def campus_auth_landing(request):
    if request.user.is_authenticated:
        if get_po(request.user):
            return redirect('campus_po_dashboard')
        if get_student(request.user):
            return redirect('campus_student_dashboard')
    return render(request, 'campus/auth_landing.html')


@transaction.atomic
def campus_student_signup(request):
    UserModel = get_user_model()
    institutions = Institution.objects.filter(status='verified').order_by('name')
    error = None
    if request.method == 'POST':
        full_name = request.POST.get('full_name', '').strip()
        phone     = request.POST.get('phone', '').strip()
        email     = request.POST.get('email', '').strip()
        pincode   = request.POST.get('pincode', '').strip()
        inst_id   = request.POST.get('institution_id', '').strip()
        password  = request.POST.get('password', '').strip()
        password2 = request.POST.get('password2', '').strip()

        if not all([full_name, phone, email, pincode, inst_id, password]):
            error = 'All fields are required.'
        elif not valid_person_name(full_name):
            error = 'Student name must contain letters and spaces only.'
        elif password != password2:
            error = 'Passwords do not match.'
        elif len(password) < 6:
            error = 'Password must be at least 6 characters.'
        elif UserModel.objects.filter(phone=phone).exists():
            error = 'This phone number is already registered.'
        elif UserModel.objects.filter(email=email).exists():
            error = 'This email is already registered.'
        else:
            inst = get_object_or_404(Institution, pk=inst_id, status='verified')
            parts = full_name.split(' ', 1)
            user = UserModel.objects.create_user(
                username   = phone,
                password   = password,
                first_name = parts[0],
                last_name  = parts[1] if len(parts) > 1 else '',
                phone      = phone,
                email      = email,
            )
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            # store chosen institution in session so student_register can pre-fill it
            request.session['campus_signup_inst_id'] = inst_id
            request.session['campus_signup_pincode']  = pincode
            messages.success(request, f'Welcome {parts[0]}! Complete your student profile below.')
            return redirect('campus_student_register')

    return render(request, 'campus/student_signup.html', {
        'institutions': institutions, 'error': error,
    })


def campus_student_login_view(request):
    error = None
    if request.method == 'POST':
        phone    = request.POST.get('phone', '').strip()
        password = request.POST.get('password', '').strip()
        user = authenticate(request, username=phone, password=password)
        if user is None:
            # try email login
            UserModel = get_user_model()
            try:
                u = UserModel.objects.get(email=phone)
                user = authenticate(request, username=u.username, password=password)
            except UserModel.DoesNotExist:
                pass
        if user:
            if not get_student(user):
                error = 'No student profile found for this account.'
            else:
                login(request, user)
                return redirect('campus_student_dashboard')
        else:
            error = 'Invalid phone / email or password.'

    return render(request, 'campus/student_login.html', {'error': error})


@transaction.atomic
def campus_po_signup(request):
    UserModel = get_user_model()
    institutions = Institution.objects.filter(status='verified').order_by('name')
    error = None
    if request.method == 'POST':
        full_name    = request.POST.get('full_name', '').strip()
        phone        = request.POST.get('phone', '').strip()
        email        = request.POST.get('email', '').strip()
        pincode      = request.POST.get('pincode', '').strip()
        inst_id      = request.POST.get('institution_id', '').strip()
        designation  = request.POST.get('designation', 'Placement Officer').strip()
        password     = request.POST.get('password', '').strip()
        password2    = request.POST.get('password2', '').strip()

        if not all([full_name, phone, email, pincode, inst_id, password]):
            error = 'All fields are required.'
        elif password != password2:
            error = 'Passwords do not match.'
        elif len(password) < 6:
            error = 'Password must be at least 6 characters.'
        elif UserModel.objects.filter(phone=phone).exists():
            error = 'This phone number is already registered.'
        elif UserModel.objects.filter(email=email).exists():
            error = 'This email is already registered.'
        else:
            inst = get_object_or_404(Institution, pk=inst_id, status='verified')
            if PlacementOfficer.objects.filter(institution=inst, is_active=True).exists():
                error = 'A Placement Officer is already registered for this institution.'
            else:
                parts = full_name.split(' ', 1)
                user = UserModel.objects.create_user(
                    username   = phone,
                    password   = password,
                    first_name = parts[0],
                    last_name  = parts[1] if len(parts) > 1 else '',
                    phone      = phone,
                    email      = email,
                )
                PlacementOfficer.objects.create(
                    user        = user,
                    institution = inst,
                    designation = designation,
                    phone       = phone,
                    email       = email,
                )
                login(request, user, backend='django.contrib.auth.backends.ModelBackend')
                messages.success(request, f'Welcome {parts[0]}! Your Placement Officer account is created.')
                return redirect('campus_po_dashboard')

    return render(request, 'campus/po_signup.html', {
        'institutions': institutions, 'error': error,
    })


@transaction.atomic
def campus_hr_signup(request):
    UserModel = get_user_model()
    error = None
    if request.method == 'POST':
        full_name    = request.POST.get('full_name', '').strip()
        email        = request.POST.get('email', '').strip()
        company_name = request.POST.get('company_name', '').strip()
        phone        = request.POST.get('phone', '').strip()
        password     = request.POST.get('password', '').strip()
        password2    = request.POST.get('password2', '').strip()

        if not all([full_name, email, company_name, password]):
            error = 'All fields are required.'
        elif password != password2:
            error = 'Passwords do not match.'
        elif len(password) < 6:
            error = 'Password must be at least 6 characters.'
        elif UserModel.objects.filter(email=email).exists():
            error = 'This email is already registered.'
        elif phone and UserModel.objects.filter(phone=phone).exists():
            error = 'This phone number is already registered.'
        else:
            username = email  # use email as username for HR
            parts = full_name.split(' ', 1)
            user = UserModel.objects.create_user(
                username   = username,
                password   = password,
                first_name = parts[0],
                last_name  = parts[1] if len(parts) > 1 else '',
                email      = email,
                phone      = phone,
            )
            CampusCompany.objects.create(
                user           = user,
                company_name   = company_name,
                contact_person = full_name,
                designation    = 'HR',
                email          = email,
                phone          = phone,
                status         = 'pending',
            )
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            messages.success(request, f'Welcome {parts[0]}! Your HR account is created. Awaiting verification.')
            return redirect('campus_company_dashboard')

    return render(request, 'campus/hr_signup.html', {'error': error})


def campus_hr_login_view(request):
    error = None
    if request.method == 'POST':
        email    = request.POST.get('email', '').strip()
        password = request.POST.get('password', '').strip()
        UserModel = get_user_model()
        # authenticate by email
        user = None
        try:
            u = UserModel.objects.get(email=email)
            user = authenticate(request, username=u.username, password=password)
        except UserModel.DoesNotExist:
            pass
        if user is None:
            # fallback: try username = email directly
            user = authenticate(request, username=email, password=password)
        if user:
            if not get_company(user):
                error = 'No HR / company profile found for this account.'
            else:
                login(request, user)
                return redirect('campus_company_dashboard')
        else:
            error = 'Invalid email or password.'

    return render(request, 'campus/hr_login.html', {'error': error})


def campus_po_login_view(request):
    error = None
    if request.method == 'POST':
        phone    = request.POST.get('phone', '').strip()
        password = request.POST.get('password', '').strip()
        user = authenticate(request, username=phone, password=password)
        if user is None:
            UserModel = get_user_model()
            try:
                u = UserModel.objects.get(email=phone)
                user = authenticate(request, username=u.username, password=password)
            except UserModel.DoesNotExist:
                pass
        if user:
            if not get_po(user):
                error = 'No Placement Officer profile found for this account.'
            else:
                login(request, user)
                return redirect('campus_po_dashboard')
        else:
            error = 'Invalid phone / email or password.'

    return render(request, 'campus/po_login.html', {'error': error})
