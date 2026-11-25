from django.urls import path
from . import views

urlpatterns = [
    # Preserve links from older dashboard pages and bookmarks.
    path('po/department/add/', views.po_department_add, name='campus_po_department_add_legacy'),
    path('po/student/add/', views.po_student_add, name='campus_po_student_add_legacy'),
    path('po/hod/add/', views.po_hod_add, name='campus_po_hod_add_legacy'),
    # ── OTP ──────────────────────────────────────────────────
    path('otp/send/',                     views.campus_send_otp,          name='campus_send_otp'),
    path('otp/verify/',                   views.campus_verify_otp,        name='campus_verify_otp'),

    # ── PUBLIC / LANDING ─────────────────────────────────────
    path('',                              views.campus_home,              name='campus_home'),
    path('auth/',                         views.campus_auth_landing,      name='campus_auth_landing'),
    path('student/signup/',               views.campus_student_signup,    name='campus_student_signup'),
    path('student/login/',                views.campus_student_login_view, name='campus_student_login'),
    path('po/signup/',                    views.campus_po_signup,         name='campus_po_signup'),
    path('po/login/',                     views.campus_po_login_view,     name='campus_po_login'),
    path('hr/signup/',                    views.campus_hr_signup,         name='campus_hr_signup'),
    path('hr/login/',                     views.campus_hr_login_view,     name='campus_hr_login'),

    # ── INSTITUTION REGISTRATION ─────────────────────────────
    path('institution/register/',         views.institution_register,     name='campus_institution_register'),
    path('institution/<int:pk>/',         views.institution_detail,       name='campus_institution_detail'),

    # ── PLACEMENT OFFICER DASHBOARD ──────────────────────────
    path('po/dashboard/',                 views.po_dashboard,             name='campus_po_dashboard'),
    path('po/departments/',               views.po_departments,           name='campus_po_departments'),
    path('po/departments/add/',           views.po_department_add,        name='campus_po_department_add'),
    path('po/hods/add/',                  views.po_hod_add,               name='campus_po_hod_add'),
    path('po/students/',                  views.po_students,              name='campus_po_students'),
    path('po/students/add/',              views.po_student_add,           name='campus_po_student_add'),
    path('po/opportunities/',             views.po_opportunities,         name='campus_po_opportunities'),
    path('po/opportunities/<int:pk>/share/', views.po_share_opportunity,  name='campus_po_share'),
    path('po/shares/<int:pk>/respond/',  views.po_respond_opportunity,   name='campus_po_respond'),
    path('po/applications/',              views.po_applications,          name='campus_po_applications'),

    # ── HOD DASHBOARD ────────────────────────────────────────
    path('hod/dashboard/',                views.hod_dashboard,            name='campus_hod_dashboard'),
    path('hod/opportunities/<int:pk>/share/', views.hod_share_students,   name='campus_hod_share'),

    # ── STUDENT DASHBOARD ────────────────────────────────────
    path('student/register/',             views.student_register,         name='campus_student_register'),
    path('student/profile/',              views.student_update_profile,   name='campus_student_profile'),
    path('student/dashboard/',            views.student_dashboard,        name='campus_student_dashboard'),
    path('student/opportunities/',        views.student_opportunities,    name='campus_student_opportunities'),
    path('student/opportunities/<int:pk>/', views.opportunity_detail,     name='campus_opportunity_detail'),
    path('student/apply/<int:pk>/',       views.student_apply,            name='campus_student_apply'),
    path('student/applications/',         views.student_applications,     name='campus_student_applications'),
    path('student/application/<int:pk>/', views.application_detail,       name='campus_application_detail'),

    # ── COMPANY ──────────────────────────────────────────────
    path('company/register/',             views.company_register,         name='campus_company_register'),
    path('company/dashboard/',            views.company_dashboard,        name='campus_company_dashboard'),
    path('company/opportunities/post/',   views.opportunity_post,         name='campus_opportunity_post'),
    path('company/opportunity/post/',     views.opportunity_post,         name='campus_opportunity_post_alt'),
    path('company/opportunities/<int:pk>/edit/', views.opportunity_edit,  name='campus_opportunity_edit'),
    path('company/opportunity/<int:pk>/edit/',   views.opportunity_edit,  name='campus_opportunity_edit_alt'),
    path('company/opportunities/<int:pk>/applications/', views.company_applications, name='campus_company_applications'),
    path('company/applications/<int:pk>/status/', views.update_app_status, name='campus_update_app_status'),
    path('company/applications/<int:pk>/interview/', views.schedule_interview, name='campus_schedule_interview'),
    path('company/applications/<int:app_pk>/offer-letter/', views.generate_offer_letter, name='campus_offer_letter'),
    path('application/<int:app_pk>/offer-letter/view/', views.view_offer_letter, name='campus_view_offer_letter'),

    # ── ADMIN ─────────────────────────────────────────────────
    path('admin/dashboard/',              views.campus_admin_dashboard,   name='campus_admin_dashboard'),
    path('admin/institutions/',           views.admin_institutions,       name='campus_admin_institutions'),
    path('admin/institutions/<int:pk>/verify/', views.admin_verify_institution, name='campus_admin_verify_institution'),
    path('admin/companies/',              views.admin_companies,          name='campus_admin_companies'),
    path('admin/companies/<int:pk>/verify/', views.admin_verify_company,  name='campus_admin_verify_company'),
    path('admin/opportunities/',          views.admin_opportunities,      name='campus_admin_opportunities'),
    path('admin/applications/',           views.admin_applications,       name='campus_admin_applications'),
    path('admin/reports/',                views.admin_reports,            name='campus_admin_reports'),
]
