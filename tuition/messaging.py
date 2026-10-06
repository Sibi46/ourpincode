from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.urls import reverse
from jobs.models import Conversation, Message
from . import models as m, permissions as p
from .services import audit, notify


def authorize(user, thread):
    p.active(user)
    enrolment = m.Enrolment.objects.select_related('lesson__teacher__owner', 'learner').get(pk=thread.enrolment_id)
    teacher = enrolment.lesson.teacher
    if teacher.status != 'approved' or not teacher.owner.is_active or enrolment.status != 'active' or not thread.adult.is_active:
        raise PermissionDenied
    if not p.adult_authority(thread.adult, enrolment.learner):
        raise PermissionDenied
    if user.pk not in (teacher.owner_id, thread.adult_id):
        raise PermissionDenied


@transaction.atomic
def start(user, enrolment, adult):
    teacher = m.TeacherProfile.objects.select_for_update().get(pk=enrolment.lesson.teacher_id)
    if user.pk != teacher.owner_id and user.pk != adult.pk:
        raise PermissionDenied
    candidate = m.TuitionConversation(enrolment=enrolment, adult=adult)
    authorize(user, candidate)
    thread = m.TuitionConversation.objects.filter(enrolment=enrolment, adult=adult).first()
    if not thread:
        a, b = sorted([teacher.owner_id, adult.pk])
        if a == b:
            raise ValidationError('Choose another conversation participant.')
        # Do not repurpose an existing unrelated jobs conversation.
        conversation = Conversation.objects.create(user_a_id=a, user_b_id=b, job=None)
        thread = m.TuitionConversation.objects.create(conversation=conversation, enrolment=enrolment, adult=adult)
        audit(user, thread, 'conversation_opened')
    return thread


@transaction.atomic
def send(user, thread, text):
    m.TeacherProfile.objects.select_for_update().get(pk=thread.enrolment.lesson.teacher_id)
    authorize(user, thread)
    text = text.strip()
    if not text or len(text) > 5000:
        raise ValidationError('Enter a message between 1 and 5,000 characters.')
    other = thread.conversation.other_user(user)
    message = Message.objects.create(conversation=thread.conversation, sender=user, receiver=other, msg_type='text', content=text)
    thread.conversation.save()
    notify(f'learning-message:{message.pk}', 'New learning message', [other.pk], reverse('tuition:thread', args=[thread.uid]))
    audit(user, thread, 'message_sent')
    return message


class LegacyGuardMiddleware:
    """Legacy routes never expose tuition message/complaint contents outside tuition guards."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        name = request.resolver_match.url_name
        if name in {'chat_room', 'poll_messages', 'send_message', 'respond_invite'}:
            conv_id = view_kwargs.get('conv_id') or request.POST.get('conv_id')
            if name == 'respond_invite':
                conv_id = Message.objects.filter(pk=view_kwargs.get('msg_id')).values_list('conversation_id', flat=True).first()
            if conv_id and str(conv_id).isdigit():
                thread = m.TuitionConversation.objects.filter(conversation_id=conv_id).first()
                if thread:
                    authorize(request.user, thread)
                    if name == 'chat_room':
                        from django.shortcuts import redirect
                        return redirect('tuition:thread', uid=thread.uid)
                    raise PermissionDenied('Use learning messaging for this conversation.')
        if name == 'resolve_complaint' and m.TuitionComplaint.objects.filter(complaint_id=view_kwargs.get('complaint_id')).exists():
            raise PermissionDenied('Use tuition moderation for this complaint.')
