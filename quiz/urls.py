from django.urls import path
from . import views
from . import pincodeday as day

urlpatterns = [
    path('pincodeday/', day.landing, name='day_landing'),
    path('promotion-admin/', day.administration, name='day_admin'),
    path('promotion-admin/<int:pk>/', day.administration, name='day_admin_event'),
    path('pincodeday/<int:pk>/', day.event_page, name='day_event'),
    path('pincodeday/<int:pk>/daily/', day.daily, name='day_daily'),
    path('pincodeday/<int:pk>/attend/', day.attend, name='day_attend'),
    path('play/', views.quiz_play, name='quiz_play'),
    # Employer
    path('', views.employer_quiz_list, name='quiz_list'),
    path('create/', views.employer_quiz_create, name='quiz_create'),
    path('<int:pk>/', views.employer_quiz_manage, name='quiz_manage'),
    path('<int:pk>/toggle/', views.employer_quiz_toggle, name='quiz_toggle'),
    path('<int:quiz_pk>/questions/add/', views.employer_question_add, name='quiz_question_add'),
    path('<int:quiz_pk>/questions/<int:q_pk>/edit/', views.employer_question_edit, name='quiz_question_edit'),

    # User AJAX
    path('api/next/', views.quiz_next_question, name='quiz_api_next'),
    path('api/answer/', views.quiz_submit_answer, name='quiz_api_answer'),
]
