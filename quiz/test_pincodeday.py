from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import PincodeDay, DayQuestion, DayAnswer, DayParticipant, DayGift, PromotionAdmin
from .pincodeday import allocate, record_answer, today, EventForm, GiftForm, QuestionForm


class PincodeDayTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='player', password='test-password')
        self.other = User.objects.create_user(username='other', password='test-password')
        self.admin = User.objects.create_user(username='main', admin_role='super_admin', password='test-password')
        self.event = PincodeDay.objects.create(starts_at=timezone.now()+timedelta(days=3), ends_at=timezone.now()+timedelta(days=3, hours=8),
            quiz_opens_on=today()-timedelta(days=1), quiz_closes_on=today()+timedelta(days=2), published=True)
        for i in range(9):
            DayQuestion.objects.create(event=self.event, text=f'Question {i}?', option_a='Yes', option_b='No', option_c='Maybe', option_d='Never', correct_answer='A')

    def test_daily_limit_no_repeats_and_exhaustion(self):
        participant, first = allocate(self.event, self.user)
        self.assertEqual(len(first), 3)
        self.assertEqual([a.pk for a in first], [a.pk for a in allocate(self.event, self.user)[1]])
        issued = {a.question_id for a in first}
        for offset in (1, 2):
            with patch('quiz.pincodeday.today', return_value=today()+timedelta(days=offset)):
                _, answers = allocate(self.event, self.user)
                self.assertEqual(len(answers), 3)
                self.assertFalse(issued & {a.question_id for a in answers})
                issued.update(a.question_id for a in answers)
        with patch('quiz.pincodeday.today', return_value=today()+timedelta(days=3)):
            self.assertEqual(allocate(self.event, self.user)[1], [])

    def test_scoring_retry_and_invalid_choice(self):
        participant, answers = allocate(self.event, self.user)
        record_answer(self.event.pk, self.user, answers[0].pk, 'A')
        record_answer(self.event.pk, self.user, answers[0].pk, 'B')
        record_answer(self.event.pk, self.user, answers[1].pk, 'B')
        with self.assertRaises(ValidationError):
            record_answer(self.event.pk, self.user, answers[2].pk, '')
        participant.refresh_from_db()
        self.assertEqual(participant.points, 6)
        self.assertEqual(participant.answers.filter(answered_at__isnull=False).count(), 2)

    def test_cannot_answer_other_user_or_yesterday(self):
        from django.http import Http404
        _, answers = allocate(self.event, self.user)
        allocate(self.event, self.other)
        with self.assertRaises(Http404):
            record_answer(self.event.pk, self.other, answers[0].pk, 'A')
        with patch('quiz.pincodeday.today', return_value=today()+timedelta(days=1)):
            with self.assertRaises(Http404):
                record_answer(self.event.pk, self.user, answers[0].pk, 'A')

    def test_public_and_private_views_and_templates(self):
        self.assertEqual(self.client.get(reverse('day_landing')).status_code, 302)
        self.assertEqual(self.client.get(reverse('day_event', args=[self.event.pk])).status_code, 302)
        self.assertEqual(self.client.get(reverse('day_daily', args=[self.event.pk])).status_code, 302)
        self.client.force_login(self.user)
        self.assertRedirects(self.client.get(reverse('day_landing')), reverse('day_daily', args=[self.event.pk]))
        self.assertEqual(self.client.get(reverse('day_event', args=[self.event.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse('day_admin'), follow=True).status_code, 403)
        response = self.client.get(reverse('day_daily', args=[self.event.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'quizPopup')
        self.assertNotContains(response, 'correct_answer')
        for hidden in ('Promotion admin', 'Manage events', 'leaderboard', 'Event agenda', 'Gifts for top scorers'):
            self.assertNotContains(response, hidden)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('day_event', args=[self.event.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('day_admin_event', args=[self.event.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('day_admin'), follow=True).status_code, 200)

    def test_no_active_quiz_shows_only_saved_points(self):
        self.event.published = False; self.event.save()
        DayParticipant.objects.create(event=self.event, user=self.user, points=41)
        self.client.force_login(self.user)
        response = self.client.get(reverse('day_landing'))
        self.assertContains(response, '41 points')
        for hidden in ('Promotion admin', 'December 20', 'agenda', 'leaderboard', 'gifts'):
            self.assertNotContains(response, hidden)

    def test_promotion_permission_grant_revoke_and_no_escalation(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('day_admin'), {'action': 'grant', 'username': self.user.username})
        self.assertTrue(PromotionAdmin.objects.get(user=self.user).is_active)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse('day_admin'), follow=True).status_code, 200)
        self.assertEqual(self.client.post(reverse('day_admin'), {'action': 'grant', 'username': self.other.username}).status_code, 403)
        self.assertEqual(self.client.get('/super-admin/').status_code, 302)
        self.client.force_login(self.admin)
        self.client.post(reverse('day_admin'), {'action': 'revoke', 'admin_id': PromotionAdmin.objects.get(user=self.user).pk})
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse('day_admin'), follow=True).status_code, 403)

    def test_finalization_rank_minimum_and_lock(self):
        first = DayParticipant.objects.create(event=self.event, user=self.user, points=15, attending=True)
        DayParticipant.objects.create(event=self.event, user=self.other, points=15)
        gift = DayGift.objects.create(event=self.event, name='First gift', rank=1, minimum_points=10)
        second = DayGift.objects.create(event=self.event, name='Second gift', rank=2, minimum_points=20)
        self.client.force_login(self.admin)
        url = reverse('day_admin_event', args=[self.event.pk])
        self.client.post(url, {'action': 'finalize'})
        self.event.refresh_from_db()
        self.assertIsNone(self.event.finalized_at)
        self.event.quiz_closes_on = today()-timedelta(days=1)
        self.event.starts_at = timezone.now()-timedelta(hours=1)
        self.event.save()
        self.client.post(url, {'action': 'finalize'})
        gift.refresh_from_db(); second.refresh_from_db(); self.event.refresh_from_db()
        self.assertEqual(gift.winner_id, first.pk)
        self.assertIsNone(second.winner)
        self.assertIsNotNone(self.event.finalized_at)
        self.client.post(url, {'action': 'delete_gift', 'gift_id': gift.pk})
        self.assertTrue(DayGift.objects.filter(pk=gift.pk).exists())
        self.client.post(url, {'action': 'present', 'participant_id': first.pk, 'present': 'yes'})
        first.refresh_from_db(); self.assertTrue(first.present)
        self.client.post(url, {'action': 'delivered', 'gift_id': gift.pk})
        gift.refresh_from_db(); self.assertTrue(gift.delivered)

    def test_duplicate_questions_and_gift_ranks_rejected(self):
        existing = self.event.questions.first()
        question = QuestionForm({'text': existing.text, 'option_a': '1', 'option_b': '2', 'option_c': '3', 'option_d': '4', 'correct_answer': 'A'}, instance=DayQuestion(event=self.event))
        self.assertFalse(question.is_valid())
        DayGift.objects.create(event=self.event, name='Gift', rank=1)
        form = GiftForm({'name': 'Duplicate', 'rank': 1, 'minimum_points': 0}, instance=DayGift(event=self.event))
        self.assertFalse(form.is_valid())

    def test_attendance_post_only_and_csrf(self):
        from django.test import Client
        self.client.force_login(self.user)
        url = reverse('day_attend', args=[self.event.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.client.post(url)
        self.assertTrue(DayParticipant.objects.get(event=self.event, user=self.user).attending)
        client = Client(enforce_csrf_checks=True); client.force_login(self.user)
        self.assertEqual(client.post(url).status_code, 403)

    def test_closed_event_and_unissued_question_cannot_score(self):
        from django.http import Http404
        participant, answers = allocate(self.event, self.user)
        unissued = self.event.questions.exclude(pk__in=[a.question_id for a in answers]).first()
        with self.assertRaises(Http404):
            record_answer(self.event.pk, self.user, unissued.pk + 100000, 'A')
        self.event.published = False; self.event.save()
        with self.assertRaises(ValidationError):
            record_answer(self.event.pk, self.user, answers[0].pk, 'A')
        participant.refresh_from_db(); self.assertEqual(participant.points, 0)

    def test_scoped_user_requires_explicit_promotion_appointment(self):
        self.user.admin_role = 'scoped_admin'; self.user.save()
        PromotionAdmin.objects.create(user=self.user)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse('day_admin'), follow=True).status_code, 200)

    def test_publish_requires_pool_and_rejects_invalid_dates(self):
        event = PincodeDay.objects.create(starts_at=self.event.starts_at, ends_at=self.event.ends_at,
            quiz_opens_on=self.event.quiz_opens_on, quiz_closes_on=self.event.quiz_closes_on)
        data = {'title': 'Draft', 'starts_at': '2026-12-20T10:00', 'ends_at': '2026-12-20T18:00',
            'quiz_opens_on': '2026-11-11', 'quiz_closes_on': '2026-12-19', 'published': 'on'}
        form = EventForm(data, instance=event)
        self.assertFalse(form.is_valid()); self.assertIn('published', form.errors)
        data.update(ends_at='2026-12-19T18:00', quiz_closes_on='2026-11-10')
        form = EventForm(data, instance=event)
        self.assertFalse(form.is_valid()); self.assertIn('ends_at', form.errors)
        self.assertIn('quiz_closes_on', form.errors)

    def test_full_admin_create_publish_user_answer_and_reports_flow(self):
        self.client.force_login(self.admin)
        data = {'action': 'event', 'title': 'New daily promotion',
            'starts_at': (timezone.now()+timedelta(days=3)).isoformat(),
            'ends_at': (timezone.now()+timedelta(days=3, hours=8)).isoformat(),
            'quiz_opens_on': today().isoformat(), 'quiz_closes_on': (today()+timedelta(days=2)).isoformat()}
        response = self.client.post(reverse('day_admin')+'?new=1', data)
        event = PincodeDay.objects.get(title='New daily promotion')
        url = reverse('day_admin_event', args=[event.pk])
        self.assertRedirects(response, url)
        for index in range(3):
            response = self.client.post(url, {'action': 'question', 'text': f'Fresh saved question {index}',
                'option_a': 'Correct choice', 'option_b': 'Wrong choice', 'option_c': 'Third', 'option_d': 'Fourth', 'correct_answer': 'A'})
            self.assertRedirects(response, url+'#question-pool')
        refreshed = self.client.get(url)
        self.assertContains(refreshed, 'Fresh saved question 2')
        self.assertContains(refreshed, '3 saved questions')
        self.assertRedirects(self.client.get(reverse('day_admin')), url)
        self.client.post(url, {'action': 'publish'})
        event.refresh_from_db(); self.assertTrue(event.published)
        self.user.first_name = 'Ravi'; self.user.last_name = 'Kumar'; self.user.save()
        self.client.force_login(self.user)
        daily_url = reverse('day_daily', args=[event.pk])
        self.assertRedirects(self.client.get(reverse('day_landing')), daily_url)
        answers = list(DayAnswer.objects.filter(participant__user=self.user, participant__event=event).order_by('slot'))
        for answer, choice in zip(answers, ['A', 'B', 'A']):
            self.assertRedirects(self.client.post(daily_url, {'answer_id': answer.pk, 'choice': choice}), daily_url)
        refreshed = self.client.get(daily_url)
        self.assertContains(refreshed, "Today's quiz is complete")
        self.assertContains(refreshed, '11 points')
        self.assertEqual(refreshed.context['summary']['correct'], 2)
        self.assertEqual(refreshed.context['summary']['wrong'], 1)
        self.assertEqual(refreshed.context['history'].paginator.count, 3)
        self.assertNotContains(refreshed, 'Quiz answer report')
        self.assertEqual(DayAnswer.objects.filter(participant__user=self.user, participant__event=event).count(), 3)
        self.client.force_login(self.admin)
        report = self.client.get(url)
        self.assertContains(report, 'Ravi Kumar')
        self.assertContains(report, '1 users answered')
        self.assertEqual(report.context['answer_summary']['answered'], 3)
        participant = report.context['participants'].get(user=self.user)
        self.assertEqual((participant.answered_count, participant.correct_count, participant.wrong_count, participant.points), (3, 2, 1, 11))
        filtered = self.client.get(url, {'question': answers[0].question_id})
        self.assertEqual(filtered.context['responses'].paginator.count, 1)
        self.assertEqual(self.client.get(url, {'question': 'invalid'}).status_code, 404)

    def test_user_history_is_private_and_survives_closed_event(self):
        participant, answers = allocate(self.event, self.user)
        record_answer(self.event.pk, self.user, answers[0].pk, 'B')
        other_participant, other_answers = allocate(self.event, self.other)
        record_answer(self.event.pk, self.other, other_answers[0].pk, 'A')
        self.event.published = False; self.event.save()
        self.client.force_login(self.user)
        result = self.client.get(reverse('day_landing'))
        self.assertEqual(result.context['summary']['points'], 1)
        self.assertEqual(result.context['summary']['wrong'], 1)
        self.assertEqual(result.context['summary']['correct'], 0)
        self.assertEqual(result.context['history'].paginator.count, 1)
        self.assertEqual(result.context['history'][0].participant_id, participant.pk)
        self.assertEqual(self.client.get(reverse('day_admin_event', args=[self.event.pk])).status_code, 403)
