import re

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, OuterRef, Subquery
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from jobs.models import Conversation, Message, User, UserNotification
from .models import NetworkConnection, NetworkPost
from .network_activities import ACTIVITIES, detect_activity, network_name
from .network_forms import NetworkPostForm


def registered_pincode(user):
    pin = user.pincode or ''
    return pin if re.fullmatch(r'[1-9][0-9]{5}', pin) else None


def local_posts(user):
    pin = registered_pincode(user)
    if not pin:
        return NetworkPost.objects.none()
    return NetworkPost.objects.filter(pincode=pin, author__pincode=pin, author__is_active=True)


@login_required
@require_http_methods(['GET', 'POST'])
def network_feed(request):
    pin = registered_pincode(request.user)
    form = NetworkPostForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST':
        if not pin:
            return HttpResponseForbidden('Add a valid pincode to your profile before posting.')
        if form.is_valid():
            with transaction.atomic():
                user = User.objects.select_for_update().get(pk=request.user.pk)
                pin = registered_pincode(user)
                if not pin:
                    return HttpResponseForbidden('Add a valid pincode to your profile before posting.')
                text = form.cleaned_data['text']
                NetworkPost.objects.create(author=user, pincode=pin, text=text, activity=detect_activity(text))
            messages.success(request, 'Your invitation is visible to people in your pincode.')
            return redirect('network_feed')
    tab = 'mine' if request.GET.get('tab') == 'mine' else 'nearby'
    posts = local_posts(request.user).filter(is_open=True)
    if tab == 'mine':
        posts = NetworkPost.objects.filter(author=request.user) if pin else NetworkPost.objects.none()
    own_connection = NetworkConnection.objects.filter(post=OuterRef('pk'), user=request.user)
    posts = posts.select_related('author').annotate(
        connection_count=Count('connections'),
        my_conversation=Subquery(own_connection.values('conversation_id')[:1]),
    ).order_by('-created_at', '-pk')
    page = Paginator(posts, 20).get_page(request.GET.get('page'))
    own_posts = {post.pk: post for post in page if post.author_id == request.user.pk}
    for post in own_posts.values():
        post.responders = []
    for connection in NetworkConnection.objects.filter(post_id__in=own_posts).select_related('user'):
        own_posts[connection.post_id].responders.append(connection)
    return render(request, 'network/feed.html', {
        'form': form, 'page': page, 'pincode': pin, 'tab': tab, 'activities': ACTIVITIES,
    }, status=400 if request.method == 'POST' else 200)


@login_required
@require_POST
@transaction.atomic
def network_connect(request, pk):
    post = get_object_or_404(local_posts(request.user), pk=pk, is_open=True)
    if post.author_id == request.user.pk:
        return HttpResponseForbidden('This is your own invitation.')
    # Lock the pair in a consistent order, also serializing connections on different posts.
    people = list(User.objects.select_for_update().filter(
        pk__in=[request.user.pk, post.author_id]).order_by('pk'))
    if len(people) != 2 or any(not p.is_active or registered_pincode(p) != post.pincode for p in people):
        return HttpResponseForbidden('You can connect only within your registered pincode.')
    post = get_object_or_404(NetworkPost.objects.select_for_update(), pk=pk, is_open=True,
                             pincode=post.pincode)
    connection = NetworkConnection.objects.filter(post=post, user=request.user).first()
    if connection and connection.conversation_id:
        return redirect('chat_room', conv_id=connection.conversation_id)
    conversation = Conversation.objects.filter(user_a=people[0], user_b=people[1], job__isnull=True).first()
    if not conversation:
        conversation = Conversation.objects.create(user_a=people[0], user_b=people[1], conv_type='general')
    if connection:
        connection.conversation = conversation
        connection.save(update_fields=['conversation'])
    else:
        NetworkConnection.objects.create(post=post, user=request.user, conversation=conversation)
        Message.objects.create(
            conversation=conversation, sender=request.user, receiver_id=post.author_id,
            content=f"I'd like to connect about your Network invitation: {post.emoji} {post.text}",
        )
        conversation.save(update_fields=['updated_at'])
        UserNotification.objects.create(
            user_id=post.author_id, title=f'{network_name(request.user)[:100]} wants to connect',
            message=f'{post.emoji} Someone in your pincode responded to your Network invitation.',
            notif_type='info', link=reverse('chat_room', args=[conversation.pk]),
        )
    return redirect('chat_room', conv_id=conversation.pk)


@login_required
@require_POST
@transaction.atomic
def network_close(request, pk):
    post = get_object_or_404(NetworkPost.objects.select_for_update(), pk=pk, author=request.user)
    if post.is_open:
        post.is_open = False
        post.closed_at = timezone.now()
        post.save(update_fields=['is_open', 'closed_at'])
    messages.success(request, 'Invitation closed. Your existing chats are still available in Messages.')
    return redirect(reverse('network_feed') + '?tab=mine')
