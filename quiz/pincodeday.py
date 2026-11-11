"""PincodeDay promotion: event-scoped, auditable daily quiz scores."""
from datetime import datetime, date
from zoneinfo import ZoneInfo

from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import PromotionAdmin, PincodeDay, DayQuestion, DayParticipant, DayAnswer, DayGift


def manager(user):
    return user.is_authenticated and user.is_active and (
        user.admin_role == 'super_admin' or PromotionAdmin.objects.filter(user=user, is_active=True).exists())


def today():
    return timezone.localdate(timezone=ZoneInfo('Asia/Kolkata'))


def ranking(event):
    # Stable, published tie-break: earliest participant registration, then account ID.
    return event.participants.filter(points__gt=0).select_related('user').order_by('-points', 'registered_at', 'user_id')


class EventForm(forms.ModelForm):
    class Meta:
        model = PincodeDay
        fields = ['title', 'description', 'agenda', 'venue', 'starts_at', 'ends_at', 'quiz_opens_on', 'quiz_closes_on', 'published']
        widgets = {key: forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={'type': 'datetime-local'}) for key in ['starts_at', 'ends_at']}
        widgets.update({key: forms.DateInput(attrs={'type': 'date'}) for key in ['quiz_opens_on', 'quiz_closes_on']})

    def clean(self):
        data = super().clean()
        if data.get('starts_at') and data.get('ends_at') and data['ends_at'] <= data['starts_at']:
            self.add_error('ends_at', 'The event must end after it starts.')
        if data.get('quiz_opens_on') and data.get('quiz_closes_on'):
            closes_on = data['quiz_closes_on']
            if closes_on < data['quiz_opens_on']:
                self.add_error('quiz_closes_on', 'Closing date must follow the opening date.')
            if data.get('starts_at') and closes_on > data['starts_at'].date():
                self.add_error('quiz_closes_on', 'Close the quiz by the event date.')
        if data.get('published') and (not self.instance.pk or self.instance.questions.count() < 3):
            self.add_error('published', 'Save a draft and add at least three questions before publishing.')
        return data


class QuestionForm(forms.ModelForm):
    class Meta:
        model = DayQuestion
        fields = ['text', 'option_a', 'option_b', 'option_c', 'option_d', 'correct_answer']

    def clean_text(self):
        value = self.cleaned_data['text']
        if DayQuestion.objects.filter(event=self.instance.event, text__iexact=value).exists():
            raise ValidationError('This question already exists in the event.')
        return value


class GiftForm(forms.ModelForm):
    class Meta:
        model = DayGift
        fields = ['name', 'description', 'rank', 'minimum_points']

    def clean_rank(self):
        value = self.cleaned_data['rank']
        if value < 1:
            raise ValidationError('Rank starts at 1.')
        if DayGift.objects.filter(event=self.instance.event, rank=value).exclude(pk=self.instance.pk).exists():
            raise ValidationError('This rank already has a gift. Edit its existing rule instead.')
        return value


@transaction.atomic
def allocate(event, user):
    event = PincodeDay.objects.select_for_update().get(pk=event.pk)
    participant, _ = DayParticipant.objects.get_or_create(event=event, user=user)
    participant = DayParticipant.objects.select_for_update().get(pk=participant.pk)
    day = today()
    existing = list(participant.answers.filter(day=day).select_related('question').order_by('slot'))
    # Once a daily set has been issued, refreshing never changes its questions.
    if not existing:
        questions = list(event.questions.exclude(pk__in=participant.answers.values('question_id')).order_by('?')[:3])
        if len(questions) == 3:
            for slot, question in enumerate(questions, 1):
                existing.append(DayAnswer.objects.create(participant=participant, question=question, day=day, slot=slot))
    return participant, existing


@transaction.atomic
def record_answer(event_id, user, answer_id, choice):
    # Event lock serializes answers against winner finalization and event closure.
    event = PincodeDay.objects.select_for_update().get(pk=event_id)
    if not event.published or event.finalized_at or not event.quiz_opens_on <= today() <= event.quiz_closes_on:
        raise ValidationError('This daily quiz is closed.')
    if choice not in 'ABCD' or len(choice) != 1:
        raise ValidationError('Choose one of the four answers.')
    participant = DayParticipant.objects.select_for_update().get(event=event, user=user)
    answer = get_object_or_404(DayAnswer.objects.select_related('question'), pk=answer_id, participant=participant, day=today())
    if answer.answered_at:
        return answer
    answer.answer = choice
    answer.points = 5 if choice == answer.question.correct_answer else 1
    answer.answered_at = timezone.now()
    answer.save(update_fields=['answer', 'points', 'answered_at'])
    participant.points += answer.points
    participant.save(update_fields=['points'])
    return answer


@login_required
def landing(request):
    event = PincodeDay.objects.filter(published=True, finalized_at__isnull=True,
        quiz_opens_on__lte=today(), quiz_closes_on__gte=today()).order_by('-quiz_opens_on', '-pk').first()
    if event:
        return redirect('day_daily', pk=event.pk)
    participant = DayParticipant.objects.filter(user=request.user).order_by('-event__starts_at', '-pk').first()
    return render(request, 'quiz/day_landing.html', {'points': participant.points if participant else 0})


@login_required
def event_page(request, pk):
    if not manager(request.user):
        raise PermissionDenied
    event = get_object_or_404(PincodeDay, pk=pk)
    participant = event.participants.filter(user=request.user).first() if request.user.is_authenticated else None
    leaders = list(ranking(event)[:50])
    return render(request, 'quiz/day_event.html', {'event': event, 'participant': participant, 'leaders': leaders,
        'gifts': event.gifts.select_related('winner__user'), 'can_play': not event.finalized_at and event.quiz_opens_on <= today() <= event.quiz_closes_on})


@login_required
def daily(request, pk):
    event = get_object_or_404(PincodeDay, pk=pk, published=True)
    if event.finalized_at or not event.quiz_opens_on <= today() <= event.quiz_closes_on:
        messages.info(request, 'This quiz is closed. Your earned points are saved.')
        return redirect('day_landing')
    if request.method == 'POST':
        try:
            answer_id = int(request.POST.get('answer_id', '0'))
            answer = record_answer(pk, request.user, answer_id, request.POST.get('choice', ''))
            messages.success(request, f'{"Correct" if answer.points == 5 else "Wrong answer"}: +{answer.points} points.')
        except (ValueError, ValidationError, DayParticipant.DoesNotExist) as exc:
            messages.error(request, str(exc))
        return redirect('day_daily', pk=pk)
    participant, answers = allocate(event, request.user)
    question = next((answer for answer in answers if not answer.answered_at), None)
    options = [(key, getattr(question.question, 'option_' + key.lower())) for key in 'ABCD'] if question else []
    return render(request, 'quiz/day_daily.html', {'event': event, 'participant': participant, 'question': question,
        'options': options, 'answers': answers, 'completed': sum(bool(a.answered_at) for a in answers)})


@login_required
@require_POST
def attend(request, pk):
    event = get_object_or_404(PincodeDay, pk=pk, published=True)
    if timezone.now() > event.ends_at:
        messages.error(request, 'Attendance registration has closed.')
    else:
        participant, _ = DayParticipant.objects.get_or_create(event=event, user=request.user)
        participant.attending = True
        participant.save(update_fields=['attending'])
        messages.success(request, 'You are registered to attend PincodeDay.')
    return redirect('day_event', pk=pk)


@login_required
def administration(request, pk=None):
    if not manager(request.user):
        raise PermissionDenied
    event = get_object_or_404(PincodeDay, pk=pk) if pk else None
    action = request.POST.get('action') if request.method == 'POST' else None
    event_form = EventForm(instance=event, initial={'starts_at': datetime(2026, 12, 20, 10), 'ends_at': datetime(2026, 12, 20, 18),
        'quiz_opens_on': today(), 'quiz_closes_on': date(2026, 12, 19)} if event is None else None)
    question_form, gift_form = QuestionForm(), GiftForm()
    if action:
        with transaction.atomic():
            if event:
                event = PincodeDay.objects.select_for_update().get(pk=event.pk)
            if action == 'grant':
                if request.user.admin_role != 'super_admin':
                    raise PermissionDenied
                user = get_user_model().objects.filter(username=request.POST.get('username', '').strip(), is_active=True).first()
                if user:
                    PromotionAdmin.objects.update_or_create(user=user, defaults={'is_active': True})
                    messages.success(request, 'Promotion admin access granted.')
                else:
                    messages.error(request, 'Enter an existing active account username.')
            elif action == 'revoke':
                if request.user.admin_role != 'super_admin':
                    raise PermissionDenied
                PromotionAdmin.objects.filter(pk=request.POST.get('admin_id')).update(is_active=False)
            elif event and event.finalized_at and action not in ('delivered', 'present'):
                messages.error(request, 'Winner results are final. This event is locked.')
            elif action == 'event':
                event_form = EventForm(request.POST, instance=event)
                if event_form.is_valid():
                    event = event_form.save()
                    messages.success(request, 'Event saved.')
                    return redirect('day_admin_event', pk=event.pk)
            elif event and action == 'question':
                question_form = QuestionForm(request.POST, instance=DayQuestion(event=event))
                if question_form.is_valid():
                    question_form.save()
                    messages.success(request, 'New question added. Issued questions stay unchanged.')
                    return redirect('day_admin_event', pk=event.pk)
            elif event and action == 'gift':
                gift = get_object_or_404(DayGift, pk=request.POST['gift_id'], event=event) if request.POST.get('gift_id') else DayGift(event=event)
                gift_form = GiftForm(request.POST, instance=gift)
                if gift_form.is_valid():
                    gift_form.save()
                    messages.success(request, 'Gift added.')
                    return redirect('day_admin_event', pk=event.pk)
            elif event and action == 'delete_gift':
                event.gifts.filter(pk=request.POST.get('gift_id')).delete()
            elif event and action == 'present':
                event.participants.filter(pk=request.POST.get('participant_id'), attending=True).update(present=request.POST.get('present') == 'yes')
            elif event and action == 'finalize':
                if today() <= event.quiz_closes_on or timezone.now() < event.starts_at:
                    messages.error(request, 'Finalize on the event day, after quiz scoring closes.')
                elif not event.gifts.exists():
                    messages.error(request, 'Add gifts before finalizing winners.')
                else:
                    leaders = list(ranking(event))
                    for gift in event.gifts.all():
                        winner = leaders[gift.rank - 1] if gift.rank <= len(leaders) else None
                        gift.winner = winner if winner and winner.points >= gift.minimum_points else None
                        gift.save(update_fields=['winner'])
                    event.finalized_at = timezone.now()
                    event.save(update_fields=['finalized_at'])
                    messages.success(request, 'Winners finalized from the leaderboard.')
            elif event and event.finalized_at and action == 'delivered':
                event.gifts.filter(pk=request.POST.get('gift_id'), winner__isnull=False).update(delivered=True)
    return render(request, 'quiz/day_admin.html', {'event': event, 'events': PincodeDay.objects.all(),
        'event_form': event_form, 'question_form': question_form, 'gift_form': gift_form,
        'admins': PromotionAdmin.objects.select_related('user'), 'super_admin': request.user.admin_role == 'super_admin',
        'participants': event.participants.select_related('user').order_by('-points', 'registered_at') if event else [],
        'gifts': event.gifts.select_related('winner__user') if event else []})
