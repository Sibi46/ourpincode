from django.urls import path
from . import views

urlpatterns = [
    path('family/profile/<int:user_id>/', views.family_profile, name='family_profile'),
    path('family/visibility/', views.family_visibility, name='family_visibility'),
    path('',                               views.hub,                   name='community_hub'),

    # Grouped hubs
    path('family/',                        views.family_hub,            name='family_hub'),
    path('family/login/',                  views.family_login,          name='family_login'),
    path('family/delete/',                 views.family_delete,         name='family_delete'),
    path('family/setup/',                  views.family_setup_wizard,   name='family_setup_wizard'),
    path('family/create/',                 views.family_member_create,  name='family_member_create'),
    path('family/quick-add/',              views.family_quick_add,      name='family_quick_add'),
    path('family/flick/add/',              views.family_flick_add,      name='family_flick_add'),
    path('family/post/add/',               views.family_post_add,       name='family_post_add'),
    path('family/member/<int:pk>/',        views.family_member_detail,  name='family_member_detail'),
    path('family/member/<int:pk>/edit/',   views.family_member_edit,    name='family_member_edit'),
    path('family/member/<int:pk>/verify/', views.family_member_verify,  name='family_member_verify'),
    path('family/birthday-gift/<int:member_pk>/', views.birthday_gift_redirect, name='birthday_gift_redirect'),
    path('school-kids/',                   views.school_kids_hub,       name='school_kids_hub'),

    # Family Stories
    path('family-stories/',                views.family_stories_feed,   name='family_stories'),
    path('family-stories/post/',           views.family_story_post,     name='family_story_post'),
    path('family-stories/<int:pk>/',       views.family_story_detail,   name='family_story_detail'),
    path('family-stories/<int:pk>/like/',  views.family_story_like,     name='family_story_like'),
    path('family-stories/<int:pk>/delete/', views.family_story_delete,  name='family_story_delete'),

    # School Corner
    path('school-corner/',                          views.school_list,          name='school_list'),
    path('school-corner/register/',                 views.school_register,      name='school_register'),
    path('school-corner/teacher/register/',         views.teacher_register,     name='teacher_register'),
    path('school-corner/teacher/login/',            views.teacher_login,        name='teacher_login'),
    path('school-corner/<int:pk>/',                 views.school_detail,        name='school_detail'),
    path('school-corner/<int:pk>/post/',            views.school_post_create,   name='school_post_create'),
    path('school-corner/<int:pk>/dashboard/',       views.school_dashboard,     name='school_dashboard'),
    path('school-corner/<int:pk>/follow/',          views.school_follow,        name='school_follow'),
    path('school-corner/<int:pk>/delete/',          views.school_delete,        name='school_delete'),
    path('school-corner/admin/list/',               views.school_admin_list,    name='school_admin_list'),
    path('school-corner/post/<int:pk>/like/',       views.school_post_like,     name='school_post_like'),

    # Student Success
    path('student-success/',                          views.student_success_feed,   name='student_success'),
    path('student-success/post/',                     views.student_success_post,   name='student_success_post'),
    path('student-success/<int:pk>/',                 views.student_success_detail, name='student_success_detail'),
    path('student-success/<int:pk>/like/',            views.student_success_like,   name='student_success_like'),
    path('student-success/<int:pk>/delete/',          views.student_success_delete, name='student_success_delete'),

    # Kids Corner
    path('kids-corner/',                    views.kids_corner_feed,   name='kids_corner'),
    path('kids-corner/post/',               views.kids_corner_post,   name='kids_corner_post'),
    path('kids-corner/<int:pk>/',           views.kids_corner_detail, name='kids_corner_detail'),
    path('kids-corner/<int:pk>/like/',      views.kids_corner_like,   name='kids_corner_like'),
    path('kids-corner/<int:pk>/delete/',    views.kids_corner_delete, name='kids_corner_delete'),

    # Parenting
    path('parenting/',                  views.parenting_feed,   name='parenting'),
    path('parenting/post/',             views.parenting_post,   name='parenting_post'),
    path('parenting/<int:pk>/',         views.parenting_detail, name='parenting_detail'),
    path('parenting/<int:pk>/like/',    views.parenting_like,   name='parenting_like'),
    path('parenting/<int:pk>/delete/',  views.parenting_delete, name='parenting_delete'),

    # Grandparents Archive
    path('grandparents-archive/',                 views.grandparents_feed,   name='grandparents'),
    path('grandparents-archive/post/',            views.grandparents_post,   name='grandparents_post'),
    path('grandparents-archive/<int:pk>/',        views.grandparents_detail, name='grandparents_detail'),
    path('grandparents-archive/<int:pk>/like/',   views.grandparents_like,   name='grandparents_like'),
    path('grandparents-archive/<int:pk>/delete/', views.grandparents_delete, name='grandparents_delete'),

    # Local Heroes
    path('local-heroes/',                 views.local_heroes_feed,  name='local_heroes'),
    path('local-heroes/post/',            views.local_hero_post,    name='local_hero_post'),
    path('local-heroes/<int:pk>/',        views.local_hero_detail,  name='local_hero_detail'),
    path('local-heroes/<int:pk>/like/',   views.local_hero_like,    name='local_hero_like'),
    path('local-heroes/<int:pk>/delete/', views.local_hero_delete,  name='local_hero_delete'),

    # Community Events
    path('events/',                   views.events_feed,    name='events'),
    path('events/post/',              views.event_post,     name='event_post'),
    path('events/<int:pk>/',          views.event_detail,   name='event_detail'),
    path('events/<int:pk>/rsvp/',     views.event_rsvp,     name='event_rsvp'),
    path('events/<int:pk>/rate-user/', views.event_rate_user,      name='event_rate_user'),
    path('events/<int:pk>/delete/',   views.event_delete,         name='event_delete'),
    path('events/deleted-history/',   views.event_deleted_history, name='event_deleted_history'),

    # Volunteer Activities
    path('volunteer/',                    views.volunteer_feed,    name='volunteer'),
    path('volunteer/post/',               views.volunteer_post,    name='volunteer_post'),
    path('volunteer/<int:pk>/',           views.volunteer_detail,  name='volunteer_detail'),
    path('volunteer/<int:pk>/signup/',    views.volunteer_signup,  name='volunteer_signup'),
    path('volunteer/<int:pk>/delete/',    views.volunteer_delete,  name='volunteer_delete'),

    # Business Stories
    path('business-stories/',                   views.business_stories_feed,  name='business_stories'),
    path('business-stories/post/',              views.business_story_post,    name='business_story_post'),
    path('business-stories/<int:pk>/',          views.business_story_detail,  name='business_story_detail'),
    path('business-stories/<int:pk>/like/',     views.business_story_like,    name='business_story_like'),
    path('business-stories/<int:pk>/delete/',   views.business_story_delete,  name='business_story_delete'),

    # Hall of Fame
    path('hall-of-fame/',                   views.hall_of_fame_feed,     name='hall_of_fame'),
    path('hall-of-fame/nominate/',           views.hall_of_fame_nominate, name='hall_of_fame_nominate'),
    path('hall-of-fame/<int:pk>/',           views.hall_of_fame_detail,   name='hall_of_fame_detail'),
    path('hall-of-fame/<int:pk>/vote/',      views.hall_of_fame_vote,     name='hall_of_fame_vote'),

    # Marketplace
    path('marketplace/',                        views.marketplace_feed,     name='marketplace'),
    path('marketplace/post/',                   views.marketplace_post,     name='marketplace_post'),
    path('marketplace/<int:pk>/',               views.marketplace_detail,   name='marketplace_detail'),
    path('marketplace/<int:pk>/interest/',      views.marketplace_interest, name='marketplace_interest'),
    path('marketplace/<int:pk>/sold/',          views.marketplace_sold,     name='marketplace_sold'),
    path('marketplace/<int:pk>/delete/',        views.marketplace_delete,   name='marketplace_delete'),

    # Community Watch
    path('community-watch/',                        views.watch_feed,     name='community_watch'),
    path('community-watch/post/',                   views.watch_post,     name='watch_post'),
    path('community-watch/<int:pk>/',               views.watch_detail,   name='watch_detail'),
    path('community-watch/<int:pk>/confirm/',       views.watch_confirm,  name='watch_confirm'),
    path('community-watch/<int:pk>/resolve/',       views.watch_resolve,  name='watch_resolve'),
    path('community-watch/<int:pk>/delete/',        views.watch_delete,   name='watch_delete'),

    # Notifications & Search
    path('notifications/',              views.notifications_page,    name='community_notifications'),
    path('notifications/mark-read/',    views.notif_mark_all_read,   name='notif_mark_all_read'),
    path('search/',                     views.community_search,      name='community_search'),

    # Module catch-all (coming soon)
    path('<slug:slug>/',                   views.module_page,           name='community_module'),
]
