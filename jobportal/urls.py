from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from jobs import views

urlpatterns = [
    path('admin/',                  admin.site.urls),
    path('',                        views.home,               name='home'),
    path('favicon.ico',             views.favicon,            name='favicon'),
    path('api/pincode/<str:pin>/',  views.api_pincode_lookup, name='api_pincode_lookup'),

    # Auth
    path('register/',               views.register,           name='register'),
    path('register/process/',       views.register_process,   name='register_process'),
    path('login/',                  views.login_view,         name='login'),
    path('forgot-password/',        views.forgot_password,    name='forgot_password'),
    path('api/reset-password/',     views.reset_password,     name='reset_password'),
    path('logout/',                 views.logout_view,        name='logout'),
    path('dashboard/',              views.dashboard,          name='dashboard'),

    # OTP
    path('api/send-otp/',           views.send_otp,           name='send_otp'),
    path('api/verify-otp/',         views.verify_otp,         name='verify_otp'),
    path('api/quick-register/',     views.quick_register,     name='quick_register'),
    path('api/send-register-otp/',  views.send_register_otp,  name='send_register_otp'),
    path('api/verify-register-otp/',views.verify_register_otp,name='verify_register_otp'),
    path('api/check-phone/',        views.check_phone,        name='check_phone'),
    path('api/phone-login/',        views.phone_login,        name='phone_login'),

    # Business Public Profile
    path('business/<str:company_id>/', views.business_profile, name='business_profile'),

    # Jobs
    path('jobs/',                   views.job_list,           name='job_list'),
    path('jobs/<int:pk>/',          views.job_detail,         name='job_detail'),
    path('jobs/<int:pk>/apply/',    views.apply_job,          name='apply_job'),
    path('post-job/',               views.post_job,           name='post_job'),
    path('jobs/<int:pk>/edit/',     views.edit_job,           name='edit_job'),

    # Dashboards
    path('employer/dashboard/',        views.employer_dashboard,       name='employer_dashboard'),
    path('employer/profile/save/',     views.employer_profile_save,    name='employer_profile_save'),
    path('employer/gallery/upload/',   views.gallery_upload,           name='gallery_upload'),
    path('employer/gallery/<int:pk>/delete/', views.gallery_delete,    name='gallery_delete'),
    path('jobseeker/dashboard/',       views.jobseeker_dashboard, name='jobseeker_dashboard'),
    path('jobseeker/profile/',                views.seeker_profile,        name='seeker_profile'),
    path('jobseeker/profile/<int:pk>/',       views.view_applicant_profile, name='view_applicant_profile'),
    path('jobseeker/certificate/<int:cert_id>/delete/', views.seeker_cert_delete, name='seeker_cert_delete'),


    # Job Seeker Actions
    path('jobs/<int:pk>/save/',              views.save_job,              name='save_job'),
    path('jobs/saved/',                      views.saved_jobs,            name='saved_jobs'),
    path('jobs/<int:pk>/withdraw/',          views.withdraw_application,    name='withdraw_application'),
    path('jobs/<int:pk>/close/',             views.close_job,               name='close_job'),
    path('applications/<int:pk>/shortlist/', views.shortlist_application,   name='shortlist_application'),
    path('applications/<int:pk>/reject/',    views.reject_application,      name='reject_application'),

    # Messaging
    path('messages/',                            views.chat_list,          name='chat_list'),
    path('messages/<int:conv_id>/',              views.chat_room,          name='chat_room'),
    path('messages/start/<int:user_id>/',        views.start_conversation, name='start_conversation'),
    path('messages/start/<int:user_id>/<int:job_id>/', views.start_conversation, name='start_conversation_job'),
    path('messages/send/',                       views.send_message,       name='send_message'),
    path('messages/poll/<int:conv_id>/',         views.poll_messages,      name='poll_messages'),
    path('messages/invite/<int:msg_id>/respond/', views.respond_invite,    name='respond_invite'),
    # Legacy chat redirect
    path('chat/<int:user_id>/<int:job_id>/', views.chat_messages_api, name='chat_api'),

    # Interview
    path('interview/schedule/<int:app_id>/', views.schedule_interview,    name='schedule_interview'),
    path('interview/accept/<int:app_id>/',   views.accept_interview,      name='accept_interview'),
    path('interview/reject/<int:app_id>/',   views.reject_interview,      name='reject_interview'),

    # Offer Letter
    path('offer/send/<int:app_id>/',         views.send_offer_letter,     name='send_offer_letter'),
    path('offer/download/<int:app_id>/',     views.download_offer_letter, name='download_offer_letter'),

    # Advertiser — Public
    path('smart-marketing/',                  views.smart_marketing_story,    name='smart_marketing_story'),
    path('advertise/',                        views.ads_gallery,              name='ads_gallery'),
    path('advertise/register/',               views.advertiser_register,      name='advertiser_register'),
    path('advertise/success/',                views.advertiser_register_success, name='advertiser_register_success'),
    path('offers/post/',                      views.offer_post,               name='offer_post'),
    path('offers/post/success/',              views.offer_post_success,       name='offer_post_success'),

    # Advertiser — Logged-in
    path('advertiser/dashboard/',             views.advertiser_dashboard,     name='advertiser_dashboard'),
    path('advertiser/create-ad/',             views.create_advertisement,     name='create_advertisement'),
    path('advertiser/payment/<int:ad_id>/',   views.ad_payment,               name='ad_payment'),
    path('advertiser/payment/<int:ad_id>/success/', views.ad_payment_success, name='ad_payment_success'),
    path('advertiser/performance/<int:ad_id>/', views.ad_performance,         name='ad_performance'),
    path('advertiser/renew/<int:ad_id>/',     views.advertiser_renew_ad,      name='advertiser_renew_ad'),
    path('ads/click/<int:ad_id>/',            views.ad_click_track,           name='ad_click_track'),
    path('ads/adpost-click/<int:ad_id>/',     views.adpost_click_track,       name='adpost_click_track'),

    # Advertiser — Ad Panel (old admin)
    path('admin-panel/advertisers/',          views.admin_advertisers,          name='admin_advertisers'),
    path('admin-panel/advertisers/<int:adv_id>/approve/',        views.admin_approve_advertiser,         name='admin_approve_advertiser'),
    path('admin-panel/advertisers/<int:adv_id>/reject/',         views.admin_reject_advertiser,          name='admin_reject_advertiser'),
    path('admin-panel/advertisers/<int:adv_id>/remove/',         views.admin_remove_advertiser,          name='admin_remove_advertiser'),
    path('admin-panel/advertisers/<int:adv_id>/upload-banner/',  views.admin_upload_advertiser_banner,   name='admin_upload_advertiser_banner'),
    path('admin-panel/ads/',                  views.admin_ad_list,              name='admin_ad_list'),
    path('admin-panel/ads/<int:ad_id>/activate/', views.admin_activate_ad,      name='admin_activate_ad'),
    path('admin-panel/ads/<int:ad_id>/reject/',   views.admin_reject_ad,        name='admin_reject_ad'),
    path('admin-panel/ads/<int:ad_id>/delete/',   views.admin_delete_ad,        name='admin_delete_ad'),
    path('api/ai-job-description/',               views.ai_generate_description, name='ai_generate_description'),
    path('api/nearby-jobs/',                      views.nearby_jobs_api,         name='nearby_jobs_api'),
    path('admin-panel/login/',                    views.admin_panel_login,       name='admin_panel_login'),
    path('admin-panel/ads/<int:ad_id>/image/',    views.admin_set_ad_image,     name='admin_set_ad_image'),
    path('admin-panel/users/',                    views.admin_users,             name='admin_users'),

    # ── SUPER ADMIN ─────────────────────────────────────────
    path('super-admin/users/',                          views.super_admin_users,     name='super_admin_users'),
    path('super-admin/users/<int:user_id>/delete/',     views.super_admin_delete_user, name='super_admin_delete_user'),
    path('super-admin/',                               views.super_admin_dashboard, name='super_admin_dashboard'),
    path('super-admin/badges/',                        views.super_admin_badges, name='super_admin_badges'),
    path('super-admin/states/',                        views.manage_states,         name='manage_states'),
    path('super-admin/states/<int:pk>/toggle/',        views.toggle_state,          name='toggle_state'),
    path('super-admin/states/<int:state_id>/districts/', views.manage_districts,    name='manage_districts'),
    path('super-admin/state-admins/',                  views.manage_state_admins,   name='manage_state_admins'),
    path('super-admin/state-admins/create/',           views.create_state_admin,    name='create_state_admin'),
    path('super-admin/admins/<int:pk>/toggle/',        views.toggle_admin,          name='toggle_admin'),
    path('super-admin/industries/',                    views.manage_industries,     name='manage_industries'),
    path('super-admin/job-roles/',                     views.manage_job_roles,      name='manage_job_roles'),
    path('super-admin/job-roles/<int:industry_id>/',   views.manage_job_roles,      name='manage_job_roles_industry'),
    path('super-admin/payment-plans/',                 views.manage_payment_plans,  name='manage_payment_plans'),
    path('super-admin/ad-packages/',                   views.manage_ad_packages,    name='manage_ad_packages'),
    path('super-admin/ad-posts/',                      views.admin_ad_posts,        name='admin_ad_posts'),

    # ── SIMPLE ADS ──────────────────────────────────────────────────────────
    path('ads/post/',                                  views.post_simple_ad,        name='post_simple_ad'),
    path('ads/my-ads/',                                views.my_simple_ads,         name='my_simple_ads'),
    path('ads/<int:pk>/renew/',                        views.renew_ad,              name='renew_ad'),
    path('super-admin/ad-settings/',                   views.admin_ad_settings,     name='admin_ad_settings'),
    path('super-admin/discounts/',                     views.manage_discounts,      name='manage_discounts'),
    path('super-admin/pincodes/',                      views.manage_pincodes,       name='manage_pincodes'),
    path('super-admin/pincodes/<int:district_id>/',    views.manage_pincodes,       name='manage_pincodes_district'),
    path('super-admin/notifications/',                 views.manage_notifications,  name='manage_notifications'),
    path('super-admin/analytics/',                     views.national_analytics,    name='national_analytics'),
    path('super-admin/flicks/',                        views.admin_flicks,          name='admin_flicks'),
    path('super-admin/feedback/',                      views.admin_feedback,         name='admin_feedback'),

    # ── STATE ADMIN ─────────────────────────────────────────
    path('state-admin/',                               views.state_admin_dashboard, name='state_admin_dashboard'),
    path('state-admin/district-admins/create/',        views.create_district_admin, name='create_district_admin'),
    path('state-admin/employers/',                     views.verify_employers,      name='verify_employers'),
    path('state-admin/users/<int:user_id>/suspend/',   views.suspend_user,          name='suspend_user'),
    path('state-admin/reports/',                       views.state_reports,         name='state_reports'),

    # ── DISTRICT ADMIN ──────────────────────────────────────
    path('district-admin/',                            views.district_admin_dashboard,   name='district_admin_dashboard'),
    path('district-admin/employers/',                  views.approve_employers_district, name='approve_employers_district'),
    path('district-admin/jobs/',                       views.moderate_jobs,              name='moderate_jobs'),
    path('district-admin/complaints/',                 views.handle_complaints,          name='handle_complaints'),
    path('district-admin/complaints/<int:complaint_id>/resolve/', views.resolve_complaint, name='resolve_complaint'),
    path('district-admin/reports/',                    views.district_reports,           name='district_reports'),

    # ── PUBLIC ──────────────────────────────────────────────
    path('complaint/submit/',                          views.submit_complaint,      name='submit_complaint'),

    # ── UTILITY ─────────────────────────────────────────────
    path('profile/',                                   views.profile_redirect,      name='profile_redirect'),
    path('profile/edit/',                              views.profile_edit,           name='profile_edit'),
    path('my-accounts/',                               views.my_accounts,            name='my_accounts'),
    path('candidates/',                                views.candidates,            name='candidates'),
    path('candidates/<int:user_id>/',                  views.candidate_profile,     name='candidate_profile'),
    path('candidates/save/<int:user_id>/',             views.save_candidate,        name='save_candidate'),
    path('notifications/mark-all-read/',               views.mark_all_notifications_read, name='mark_all_notifications_read'),
    path('jobs/<int:pk>/select-plan/',                 views.job_select_plan,             name='job_select_plan'),
    path('referral/',                                  views.referral_dashboard,          name='referral_dashboard'),
    path('api/update-interview-type/',                 views.update_interview_type,        name='update_interview_type'),
    path('api/pincode/<str:pin>/',                     views.api_pincode_lookup,          name='api_pincode_lookup'),
    path('about/',                                     views.about_page,                   name='about'),
    path('terms/',                                     views.terms,                        name='terms'),
    path('privacy/',                                   views.privacy,                      name='privacy'),

    # ── FLICKS ──────────────────────────────────────────────────────────────
    path('flicks/',                                    views.flicks_feed,                  name='flicks_feed'),
    path('flicks/post/',                               views.post_flick,                   name='post_flick'),
    path('flicks/<int:pk>/like/',                      views.like_flick,                   name='like_flick'),
    path('flicks/<int:pk>/comment/',                   views.comment_flick,                name='comment_flick'),
    path('flicks/<int:pk>/delete/',                    views.delete_flick,                 name='delete_flick'),
    path('flicks/<int:pk>/advertise/',                 views.flick_advertise,              name='flick_advertise'),
    path('flicks/<int:pk>/report/',                    views.report_flick,                 name='report_flick'),
    path('super-admin/flick-reports/',                 views.admin_flick_reports,          name='admin_flick_reports'),
    path('api/spin/',                                 views.spin_api,                    name='spin_api'),
    path('super-admin/spin-gifts/',                   views.manage_spin_gifts,            name='manage_spin_gifts'),
    path('super-admin/spin-gifts/<int:pk>/delete/',   views.delete_spin_gift,             name='delete_spin_gift'),
    path('super-admin/spin-gifts/<int:pk>/toggle/',   views.toggle_spin_gift,             name='toggle_spin_gift'),
    path('super-admin/offers/',                       views.manage_offers,                name='manage_offers'),
    path('super-admin/offers/<int:pk>/approve/',      views.offer_approve,                name='offer_approve'),
    path('super-admin/offers/<int:pk>/delete/',       views.offer_delete,                 name='offer_delete'),
    path('health/',     include('health.urls')),
    path('vouchers/',   include('vouchers.urls')),
    path('community/',  include('community.urls')),
    path('campus/',     include('campus.urls')),
    path('portal/',     include('portal.urls')),
    path('coupons/',    include('coupons.urls')),
    path('quiz/',       include('quiz.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
