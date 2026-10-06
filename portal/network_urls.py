from django.urls import path
from . import network_views

urlpatterns = [
    path('', network_views.network_feed, name='network_feed'),
    path('<int:pk>/connect/', network_views.network_connect, name='network_connect'),
    path('<int:pk>/close/', network_views.network_close, name='network_close'),
]
