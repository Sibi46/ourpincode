from django.contrib import admin
from .models import NetworkPost, NetworkConnection


@admin.register(NetworkPost)
class NetworkPostAdmin(admin.ModelAdmin):
    list_display = ['id', 'author', 'pincode', 'activity', 'is_open', 'created_at']
    list_filter = ['is_open', 'activity', 'pincode']
    search_fields = ['text', 'pincode', 'author__first_name', 'author__last_name']
    readonly_fields = ['author', 'pincode', 'activity', 'created_at', 'closed_at']

    def has_add_permission(self, request):
        return False


@admin.register(NetworkConnection)
class NetworkConnectionAdmin(admin.ModelAdmin):
    list_display = ['post', 'user', 'created_at']
    readonly_fields = ['post', 'user', 'conversation', 'created_at']

    def has_add_permission(self, request):
        return False
from .models import (
    Category, Community, CommunityLeader, CommunityMember,
    Cause, CauseSupport, Event, EventParticipant,
    VolunteerRequest, Activity, ActivityPhoto,
    Post, PostLike, PostComment, ShortVideo, PortalNotification,
)

admin.site.register(Category)
admin.site.register(Community)
admin.site.register(CommunityLeader)
admin.site.register(CommunityMember)
admin.site.register(Cause)
admin.site.register(CauseSupport)
admin.site.register(Event)
admin.site.register(EventParticipant)
admin.site.register(VolunteerRequest)
admin.site.register(Activity)
admin.site.register(ActivityPhoto)
admin.site.register(Post)
admin.site.register(ShortVideo)
admin.site.register(PortalNotification)
