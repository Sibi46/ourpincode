from datetime import timedelta
from unittest.mock import patch
from django.test import Client,TestCase
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from jobs.models import User,AdminActivity
from .models import PincodeDay,DayQuestion,DayParticipant,DayAnswer,DayGift,PromotionAdmin
from .pincodeday import allocate,record_answer,today,EventForm


class QuizDeletionTests(TestCase):
    def setUp(self):
        self.admin=User.objects.create_user('quiz-delete-admin',admin_role='super_admin')
        self.player=User.objects.create_user('quiz-delete-player')
        self.promoter=User.objects.create_user('quiz-delete-promoter')
        PromotionAdmin.objects.create(user=self.promoter)
        self.event=PincodeDay.objects.create(title='Delete Test Quiz',starts_at=timezone.now()+timedelta(days=4),
            ends_at=timezone.now()+timedelta(days=4,hours=4),quiz_opens_on=today()-timedelta(days=1),
            quiz_closes_on=today()+timedelta(days=3),published=True)
        self.questions=[DayQuestion.objects.create(event=self.event,text=f'Question {i}',option_a='Yes',
            option_b='No',option_c='Maybe',option_d='Other',correct_answer='A') for i in range(9)]
        self.client.force_login(self.admin)

    def url(self,question=None):
        return reverse('day_delete_question',args=[self.event.pk,question.pk]) if question else reverse('day_delete_event',args=[self.event.pk])

    def review(self,question=None):
        response=self.client.get(self.url(question))
        self.assertEqual(response.status_code,200)
        return response.context['review_token']

    def delete(self,question=None):
        return self.client.post(self.url(question),{'confirmation':'DELETE','review_token':self.review(question)})

    def test_only_super_admin_can_delete_and_sees_actions(self):
        for user in [self.player,self.promoter,User.objects.create_user('quiz-staff',is_staff=True)]:
            self.client.force_login(user)
            self.assertEqual(self.client.get(self.url()).status_code,403)
            self.assertEqual(self.client.post(self.url(self.questions[0]),{'confirmation':'DELETE'}).status_code,403)
        self.client.force_login(self.promoter)
        response=self.client.get(reverse('day_admin_event',args=[self.event.pk]))
        self.assertNotContains(response,'Delete Quiz Event')
        self.assertNotContains(response,'Delete Question')
        self.client.force_login(self.admin)
        response=self.client.get(reverse('day_admin_event',args=[self.event.pk]))
        self.assertContains(response,'Delete Quiz Event')
        self.assertContains(response,'Delete Question')

    def test_review_is_read_only_and_confirmation_and_csrf_are_required(self):
        token=self.review()
        self.event.refresh_from_db();self.assertIsNone(self.event.deleted_at)
        self.assertEqual(self.client.post(self.url(),{'confirmation':'DELETE'}).status_code,409)
        self.assertEqual(self.client.post(self.url(),{'review_token':token,'confirmation':'NO'}).status_code,400)
        client=Client(enforce_csrf_checks=True);client.force_login(self.admin)
        self.assertEqual(client.post(self.url(),{'review_token':token,'confirmation':'DELETE'}).status_code,403)

    def test_removed_question_is_not_allocated_to_new_users(self):
        question=self.questions[0]
        self.assertEqual(self.delete(question).status_code,302)
        question.refresh_from_db();self.assertIsNotNone(question.deleted_at)
        for n in range(6):
            user=User.objects.create_user(f'new-player-{n}')
            _,answers=allocate(self.event,user)
            self.assertEqual(len(answers),3)
            self.assertNotIn(question.pk,[answer.question_id for answer in answers])
        response=self.client.get(reverse('day_admin_event',args=[self.event.pk]))
        self.assertNotIn(question.pk,[q.pk for q in response.context['questions']])
        response=self.client.get(reverse('day_admin_event',args=[self.event.pk])+'?include_deleted=1')
        self.assertIn(question.pk,[q.pk for q in response.context['questions']])

    def test_issued_sets_and_scores_survive_question_deletion(self):
        participant,answers=allocate(self.event,self.player)
        record_answer(self.event.pk,self.player,answers[0].pk,'A')
        question=answers[1].question
        self.delete(question)
        _,same=allocate(self.event,self.player)
        self.assertEqual([a.pk for a in answers],[a.pk for a in same])
        record_answer(self.event.pk,self.player,answers[1].pk,'B')
        participant.refresh_from_db()
        self.assertEqual(participant.points,6)
        self.assertEqual(DayAnswer.objects.filter(participant=participant).count(),3)

    def test_deleted_event_is_closed_but_history_and_winners_are_preserved(self):
        participant,answers=allocate(self.event,self.player)
        record_answer(self.event.pk,self.player,answers[0].pk,'A')
        gift=DayGift.objects.create(event=self.event,name='Top Gift',rank=1,winner=participant)
        self.assertEqual(self.delete().status_code,302)
        self.event.refresh_from_db();participant.refresh_from_db();gift.refresh_from_db()
        self.assertIsNotNone(self.event.deleted_at);self.assertFalse(self.event.published)
        self.assertEqual(participant.points,5);self.assertEqual(gift.winner_id,participant.pk)
        self.assertEqual(self.event.questions.count(),9)
        with self.assertRaises(ValidationError):allocate(self.event,self.player)
        with self.assertRaises(ValidationError):record_answer(self.event.pk,self.player,answers[1].pk,'A')
        self.client.force_login(self.player)
        self.assertEqual(self.client.get(reverse('day_daily',args=[self.event.pk])).status_code,404)
        self.assertEqual(self.client.post(reverse('day_attend',args=[self.event.pk])).status_code,404)
        response=self.client.get(reverse('day_landing')+'?history=1')
        self.assertEqual(response.context['summary']['points'],5)
        self.assertEqual(response.context['summary']['answered'],1)

    def test_archived_event_reports_are_read_only_and_not_in_active_list(self):
        self.delete()
        response=self.client.get(reverse('day_admin_event',args=[self.event.pk]))
        self.assertContains(response,'reports are read-only')
        self.assertNotIn(self.event.pk,[event.pk for event in response.context['events']])
        self.assertIn(self.event.pk,[event.pk for event in response.context['deleted_events']])
        self.assertNotContains(response,'Save event')
        self.assertNotContains(response,'Save Quiz Question')
        self.assertEqual(self.client.post(reverse('day_admin_event',args=[self.event.pk]),{'action':'publish'}).status_code,403)

    def test_finalized_event_can_be_removed_without_changing_winners(self):
        participant,answers=allocate(self.event,self.player)
        record_answer(self.event.pk,self.player,answers[0].pk,'A')
        finalized=timezone.now()
        self.event.finalized_at=finalized;self.event.save()
        gift=DayGift.objects.create(event=self.event,name='Final Gift',rank=1,winner=participant,delivered=True)
        self.assertEqual(self.delete().status_code,302)
        self.event.refresh_from_db();gift.refresh_from_db();participant.refresh_from_db()
        self.assertEqual(self.event.finalized_at,finalized)
        self.assertEqual(gift.winner_id,participant.pk)
        self.assertTrue(gift.delivered)
        self.assertEqual(participant.points,5)

    def test_wrong_event_question_scope_and_stale_reviews_are_rejected(self):
        other=PincodeDay.objects.create(title='Other',starts_at=self.event.starts_at,ends_at=self.event.ends_at,
                                       quiz_opens_on=self.event.quiz_opens_on,quiz_closes_on=self.event.quiz_closes_on)
        self.assertEqual(self.client.get(reverse('day_delete_question',args=[other.pk,self.questions[0].pk])).status_code,404)
        token=self.review()
        self.event.title='Changed title';self.event.save()
        self.assertEqual(self.client.post(self.url(),{'review_token':token,'confirmation':'DELETE'}).status_code,409)

    def test_deleted_questions_do_not_count_towards_publication_minimum(self):
        for question in self.questions[:7]:self.delete(question)
        form=EventForm({'title':self.event.title,'starts_at':self.event.starts_at,'ends_at':self.event.ends_at,
            'quiz_opens_on':self.event.quiz_opens_on,'quiz_closes_on':self.event.quiz_closes_on,'published':True},instance=self.event)
        self.assertFalse(form.is_valid());self.assertIn('published',form.errors)
        _,answers=allocate(self.event,self.player)
        self.assertEqual(answers,[])

    def test_history_can_be_viewed_even_while_another_quiz_is_live(self):
        participant,answers=allocate(self.event,self.player)
        record_answer(self.event.pk,self.player,answers[0].pk,'A')
        self.client.force_login(self.player)
        self.assertEqual(self.client.get(reverse('day_landing')).status_code,302)
        response=self.client.get(reverse('day_landing')+'?history=1')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.context['summary']['points'],5)

    def test_failed_audit_rolls_back_and_repeat_does_not_duplicate(self):
        question=self.questions[0];token=self.review(question)
        with patch('quiz.deletion.AdminActivity.objects.create',side_effect=RuntimeError('audit failed')):
            with self.assertRaises(RuntimeError):
                self.client.post(self.url(question),{'review_token':token,'confirmation':'DELETE'})
        question.refresh_from_db();self.assertIsNone(question.deleted_at)
        self.delete(question)
        self.assertEqual(self.client.post(self.url(question),{'review_token':token,'confirmation':'DELETE'}).status_code,404)
        self.assertEqual(AdminActivity.objects.filter(action='delete_quiz_question').count(),1)
