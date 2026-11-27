from datetime import date, datetime, timedelta
from importlib import import_module
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase

from jobs.models import AdminActivity
from .models import PincodeDay, DayParticipant


class LaunchRescheduleTests(TestCase):
    def setUp(self):
        self.zone = ZoneInfo('Asia/Kolkata')
        self.event, _ = PincodeDay.objects.update_or_create(pk=1, defaults={
            'title': 'PincodeDay',
            'starts_at': datetime(2026, 12, 20, 10, 30, tzinfo=self.zone),
            'ends_at': datetime(2026, 12, 20, 19, tzinfo=self.zone),
            'quiz_opens_on': date(2026, 11, 11),
            'quiz_closes_on': date(2026, 12, 19),
            'description': 'Gifts on December 20, 2026',
            'published': True, 'deleted_at': None, 'finalized_at': None,
        })

    def reschedule(self):
        import_module('quiz.migrations.0006_reschedule_pincodeday_january').reschedule_launch(
            apps, SimpleNamespace(connection=connection))
        self.event.refresh_from_db()

    def test_schedule_and_points_preserved_and_idempotent(self):
        user = get_user_model().objects.create_user(username='schedule-player')
        participant = DayParticipant.objects.create(event=self.event, user=user, points=21)
        self.reschedule()
        self.assertEqual(self.event.starts_at.astimezone(self.zone),
                         datetime(2027, 1, 29, 10, 30, tzinfo=self.zone))
        self.assertEqual(self.event.ends_at - self.event.starts_at, timedelta(hours=8, minutes=30))
        self.assertEqual(self.event.quiz_closes_on, date(2027, 1, 28))
        self.assertEqual(self.event.quiz_opens_on, date(2026, 11, 11))
        self.assertTrue(self.event.published)
        self.assertIn('January 29, 2027', self.event.description)
        participant.refresh_from_db()
        self.assertEqual(participant.points, 21)
        count = AdminActivity.objects.filter(action='reschedule_quiz_event').count()
        self.reschedule()
        self.assertEqual(AdminActivity.objects.filter(action='reschedule_quiz_event').count(), count)

    def test_custom_schedule_is_untouched(self):
        self.event.starts_at += timedelta(days=1)
        self.event.save()
        original = self.event.starts_at
        self.reschedule()
        self.assertEqual(self.event.starts_at, original)

    def test_finalized_event_is_untouched(self):
        self.event.finalized_at = self.event.starts_at
        self.event.save()
        self.reschedule()
        self.assertEqual(self.event.quiz_closes_on, date(2026, 12, 19))
