from datetime import timedelta
from io import StringIO
from unittest.mock import Mock, patch

from django.core import mail
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import (BusinessReview, BusinessReviewReport, CompanyProfile, Flick,
                     FlickLike, Job, ReviewVoucher, User, UserNotification)


class ReportTwoTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('business', user_type='company', pincode='600073',
            city='Chennai', address='Test street', email='owner@example.com')
        self.company = CompanyProfile.objects.create(user=self.owner, company_name='Neighbourhood Store',
            description='Groceries and fresh produce.', industry='Retail', company_size='2–10 employees')
        self.customer = User.objects.create_user('reviewer_account_42')
        self.other = User.objects.create_user('other')
        self.url = reverse('business_profile', args=[self.company.company_id])
        self.review_url = reverse('business_review', args=[self.company.company_id])

    def login(self, user):
        self.client.force_login(user, backend='django.contrib.auth.backends.ModelBackend')

    def review(self, rating=4, text='Friendly service and useful products.'):
        return self.client.post(self.review_url, {'rating': rating, 'text': text})

    def test_legacy_referral_link_and_single_notification_bell(self):
        self.login(self.owner)
        session = self.client.session
        session['show_referral_popup'] = True
        session.save()
        response = self.client.get('/employer/dashboard/')
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.referral_code)
        self.assertContains(response, '/register/?ref=' + self.owner.referral_code)
        self.assertContains(response, 'copyRefPopup(event)')
        self.client.post(reverse('employer_profile_save'), {})
        response = self.client.get('/businesses/')
        self.assertContains(response, 'aria-label="My profile and features"', count=1)

    def test_post_job_redirects_to_its_actual_state_and_preserves_pin(self):
        self.login(self.owner)
        for action, section in [('publish', 'approval-pending'), ('draft', 'pending-jobs')]:
            response = self.client.post('/post-job/', {'title': 'Cashier', 'action': action,
                'latitude': '13.082680', 'longitude': '80.270718'})
            self.assertRedirects(response, '/employer/dashboard/#' + section, fetch_redirect_response=False)
        job = Job.objects.order_by('pk').first()
        self.assertEqual(str(job.latitude), '13.082680')
        self.assertFalse(job.is_approved)
        response = self.client.get('/employer/dashboard/#approval-pending')
        self.assertContains(response, 'Under review (1)')
        self.assertContains(response, 'Drafts (1)')
        self.assertContains(self.client.get('/post-job/'), 'Posting for Neighbourhood Store')

    def test_review_validation_self_review_update_and_escaping(self):
        self.assertEqual(self.review().status_code, 302)
        self.assertFalse(BusinessReview.objects.exists())
        self.login(self.owner)
        self.review()
        self.assertFalse(BusinessReview.objects.exists())
        self.login(self.customer)
        self.assertEqual(self.client.get(self.review_url).status_code, 405)
        for rating, text in [(6, 'Long enough text'), (0, 'Long enough text'), ('x', 'Long enough text'), (3, 'short')]:
            self.review(rating, text)
        self.assertFalse(BusinessReview.objects.exists())
        self.review(1, '<script>alert(1)</script> Slow service.')
        response = self.client.get(self.url)
        self.assertContains(response, '&lt;script&gt;')
        self.assertNotContains(response, '<script>alert(1)</script>')
        self.review(5)
        self.assertEqual(BusinessReview.objects.count(), 1)
        self.assertEqual(BusinessReview.objects.get().rating, 5)
        self.assertFalse(ReviewVoucher.objects.exists())

    def test_reward_rating_independence_owner_only_and_single_redemption(self):
        self.company.review_reward_percent = 10
        self.company.save()
        self.login(self.customer)
        self.review(1)
        voucher = ReviewVoucher.objects.get()
        self.assertEqual(voucher.discount_percent, 10)
        self.review(5)
        self.assertEqual(ReviewVoucher.objects.count(), 1)
        self.assertContains(self.client.get(self.url), voucher.code)
        self.login(self.other)
        self.assertNotContains(self.client.get(self.url), voucher.code)
        redeem = reverse('redeem_review_voucher', args=[self.company.company_id])
        self.assertEqual(self.client.post(redeem, {'code': voucher.code}).status_code, 404)
        self.login(self.owner)
        self.client.post(redeem, {'code': voucher.code})
        voucher.refresh_from_db()
        first = voucher.redeemed_at
        self.assertIsNotNone(first)
        self.client.post(redeem, {'code': voucher.code})
        voucher.refresh_from_db()
        self.assertEqual(voucher.redeemed_at, first)

    def test_expired_voucher_cannot_be_redeemed(self):
        review = BusinessReview.objects.create(company=self.company, user=self.customer, rating=2, text='Not enough stock today.')
        voucher = ReviewVoucher.objects.create(review=review, code='TESTEXPIRED', discount_percent=5,
            expires_at=timezone.now() - timedelta(days=1))
        self.login(self.owner)
        self.client.post(reverse('redeem_review_voucher', args=[self.company.company_id]), {'code': voucher.code})
        voucher.refresh_from_db()
        self.assertIsNone(voucher.redeemed_at)

    def test_discovery_sort_and_pincode_filter(self):
        BusinessReview.objects.create(company=self.company, user=self.customer, rating=5, text='Excellent service every visit.')
        other_company = CompanyProfile.objects.create(user=self.other, company_name='A distant business')
        response = self.client.get('/businesses/?sort=trending&pincode=600073')
        self.assertContains(response, self.company.company_name)
        self.assertNotContains(response, other_company.company_name)
        self.assertEqual(response.context['businesses'][0], self.company)
        self.assertContains(response, '5.0/5')

    def test_business_post_like_uses_existing_toggle(self):
        flick = Flick.objects.create(user=self.owner, title='New arrivals', moderation_status='approved')
        self.login(self.customer)
        self.assertContains(self.client.get(self.url), 'likeBusinessPost(this,' + str(flick.pk))
        url = reverse('like_flick', args=[flick.pk])
        self.assertTrue(self.client.post(url).json()['liked'])
        self.assertFalse(self.client.post(url).json()['liked'])
        self.assertFalse(FlickLike.objects.exists())

    def test_monthly_reports_and_email_are_idempotent(self):
        BusinessReview.objects.create(company=self.company, user=self.customer, rating=2, text='Please improve stock availability.')
        month = timezone.localdate().strftime('%Y-%m')
        for _ in range(2):
            call_command('send_business_review_reports', month=month, email=True, stdout=StringIO())
        report = BusinessReviewReport.objects.get(company=self.company)
        self.assertIn('1 customer reviews', report.summary)
        self.assertEqual(UserNotification.objects.filter(user=self.owner, title__startswith='Monthly review report').count(), 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIsNotNone(report.emailed_at)
        self.login(self.owner)
        self.assertContains(self.client.get(self.url), 'Monthly review reports')

    @override_settings(ANTHROPIC_API_KEY='synthetic-test-key')
    @patch('anthropic.Anthropic')
    def test_ai_summary_is_labeled_and_uses_only_review_content(self, client):
        BusinessReview.objects.create(company=self.company, user=self.customer, rating=4, text='Friendly service. More stock would help.')
        client.return_value.messages.create.return_value.content = [Mock(type='text', text='Customers like the service and suggest improving stock.')]
        call_command('send_business_review_reports', month=timezone.localdate().strftime('%Y-%m'), ai=True, stdout=StringIO())
        report = BusinessReviewReport.objects.get(company=self.company)
        self.assertTrue(report.ai_generated)
        self.assertContains(self.client.get(self.url), 'AI review summary')
        kwargs = client.return_value.messages.create.call_args.kwargs
        self.assertNotIn(self.customer.username, kwargs['messages'][0]['content'])

    def test_database_prevents_duplicate_reviews_and_out_of_range_ratings(self):
        BusinessReview.objects.create(company=self.company, user=self.customer, rating=3, text='A reasonable local shop.')
        with self.assertRaises(IntegrityError), transaction.atomic():
            BusinessReview.objects.create(company=self.company, user=self.customer, rating=4, text='Duplicate')
        with self.assertRaises(IntegrityError), transaction.atomic():
            BusinessReview.objects.create(company=self.company, user=self.other, rating=8, text='Invalid rating')
