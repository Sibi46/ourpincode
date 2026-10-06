"""Real MySQL locking tests. Skipped explicitly on SQLite, never simulated."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from decimal import Decimal
from datetime import timedelta
from unittest import skipUnless
import uuid

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, close_old_connections, connections
from django.test import TransactionTestCase
from django.utils import timezone
from . import models as m, services as svc, activities as a, test_activities as fixtures


@skipUnless(connection.vendor == 'mysql', 'Requires isolated MySQL')
class MySQLConcurrencyTests(TransactionTestCase):
    def setUp(self):
        fixtures.ActivityTests.setUpTestData.__func__(type(self))

    def race(self, *functions):
        barrier = Barrier(len(functions))
        def run(fn):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return fn()
            except (ValidationError, PermissionDenied):
                return 'rejected'
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=len(functions)) as pool:
            return list(pool.map(run, functions))

    def invoice(self):
        fee = svc.save_agreement(self.owner, m.FeeAgreement(enrolment=self.enrolment, start_date=timezone.localdate(), amount=100))
        return svc.create_invoice(self.owner, m.Invoice(agreement=fee, period_start=timezone.localdate(), period_end=timezone.localdate(), due_date=timezone.localdate(), amount=100))

    def sibling(self):
        learner = m.Learner.objects.create(name='Second learner', pincode='999999', age=10, created_by=self.parent)
        m.GuardianLink.objects.create(learner=learner, user=self.parent, relationship='Parent', attestation='Reviewed', status='verified', reviewed_by=self.admin, reviewed_at=timezone.now())
        return m.Enrolment.objects.create(learner=learner, lesson=self.lesson)

    def test_duplicate_payment_key_credits_once(self):
        invoice = self.invoice(); key = uuid.uuid4()
        fn = lambda: svc.record_payment(self.owner, invoice, Decimal('60'), 'cash', key).pk
        result = self.race(fn, fn)
        self.assertEqual(result[0], result[1]); self.assertEqual(invoice.paid, Decimal('60'))
        self.assertEqual(invoice.payments.count(), 1)

    def test_concurrent_payments_cannot_overpay(self):
        invoice = self.invoice()
        fn = lambda: svc.record_payment(self.owner, invoice, Decimal('60'), 'cash', uuid.uuid4()).pk
        result = self.race(fn, fn)
        self.assertEqual(result.count('rejected'), 1); self.assertEqual(invoice.balance, Decimal('40'))

    def test_concurrent_reversals_append_once(self):
        invoice = self.invoice(); payment = svc.record_payment(self.owner, invoice, Decimal('60'), 'cash', uuid.uuid4())
        fn = lambda: svc.reverse_payment(self.owner, payment).pk
        result = self.race(fn, fn)
        self.assertEqual(result[0], result[1]); self.assertEqual(invoice.paid, 0)
        self.assertEqual(invoice.payments.count(), 2)

    def test_batch_capacity_serialized(self):
        sibling = self.sibling(); self.batch.capacity = 1; self.batch.save()
        result = self.race(lambda: svc.transfer(self.owner, self.enrolment, self.batch), lambda: svc.transfer(self.owner, sibling, self.batch))
        self.assertEqual(result.count('rejected'), 1)
        self.assertEqual(self.batch.memberships.count(), 1)

    def test_event_last_slot_serialized(self):
        sibling = self.sibling(); now = timezone.now()
        event = m.LearningEvent.objects.create(teacher=self.teacher, kind='festival', title='Annual day', description='Music', start=now+timedelta(days=1), end=now+timedelta(days=2), venue='Hall', registration_start=now-timedelta(days=1), registration_end=now+timedelta(hours=10), capacity=1, status='published', moderation='approved')
        result = self.race(lambda: a.register_event(self.parent, event, self.enrolment, True).pk, lambda: a.register_event(self.parent, event, sibling, True).pk)
        self.assertEqual(result.count('rejected'), 1); self.assertEqual(event.participants.count(), 1)

    def test_points_retries_award_once(self):
        achievement = m.Achievement.objects.create(teacher=self.teacher, enrolment=self.enrolment, title='Award', kind='other')
        fn = lambda: a.award(self.enrolment, 'achievement', 'achievement', achievement, True, '1')
        self.race(fn, fn)
        self.assertEqual(a.points(self.enrolment), 25); self.assertEqual(self.enrolment.point_entries.count(), 1)

    def test_consent_revocation_stays_private(self):
        achievement = m.Achievement.objects.create(teacher=self.teacher, enrolment=self.enrolment, title='Award', kind='other', moderation='approved', public_requested=True)
        self.race(lambda: a.consent(self.parent, achievement, self.child, '', False, timezone.now()+timedelta(days=1)),
                  lambda: svc.review_guardian(self.admin, self.guardian, 'revoked', 'Authority revoked'))
        self.assertFalse(a.public_allowed(m.Achievement.objects.get(pk=achievement.pk)))
