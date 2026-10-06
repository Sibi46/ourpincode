from django.urls import path
from . import views

app_name = 'newsdesk'
urlpatterns = [
    path('', views.feed, name='feed'),
    path('stories/<int:pk>/', views.detail, name='detail'),
    path('stories/<int:pk>/comment/', views.comment, name='comment'),
    path('stories/<int:pk>/rate/', views.rate, name='rate'),
    path('comments/<int:pk>/report/', views.report, name='report'),
    path('media/<int:pk>/<str:kind>/', views.media, name='media'),
    path('desk/', views.manage, name='manage'),
    path('desk/new/', views.edit, name='create'),
    path('desk/<int:pk>/edit/', views.edit, name='edit'),
    path('desk/comments/<int:pk>/', views.moderate, name='moderate'),
    path('desk/agents/', views.agents, name='agents'),
    path('desk/agents/<int:pk>/', views.agents, name='agent_edit'),
    path('birthday/', views.birthday, name='birthday'),
    path('birthday/<uuid:pk>/', views.card, name='card'),
    path('birthday/<uuid:pk>/remove/', views.remove_card, name='remove_card'),
    path('api/stories/', views.feed, name='api_feed'),
    path('api/pincodes/', views.pincodes, name='api_pincodes'),
    path('api/stories/<int:pk>/', views.detail, name='api_detail'),
    path('api/stories/<int:pk>/comments/', views.comment, name='api_comment'),
    path('api/stories/<int:pk>/rating/', views.rate, name='api_rate'),
    path('api/comments/<int:pk>/report/', views.report, name='api_report'),
    path('api/desk/', views.manage, name='api_manage'),
    path('api/desk/new/', views.edit, name='api_create'),
    path('api/desk/<int:pk>/', views.edit, name='api_edit'),
    path('api/desk/comments/<int:pk>/', views.moderate, name='api_moderate'),
    path('api/agents/', views.agents, name='api_agents'),
    path('api/agents/<int:pk>/', views.agents, name='api_agent_edit'),
    path('api/birthday/', views.birthday, name='api_birthday'),
]
