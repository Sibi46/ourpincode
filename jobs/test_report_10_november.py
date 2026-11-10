from datetime import timedelta
from io import StringIO
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from jobs.account import DashboardSeekerForm
from jobs.models import CompanyProfile, Flick, LocalOffer, User
from portal.models import Community, Event
from vouchers.forms import BranchForm, BusinessRegistrationForm, GiftVoucherForm
from vouchers.models import Branch, Business, BusinessCategory, VoucherCategory


class ReportTenNovemberTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('report-ten-owner', user_type='company', first_name='Ravi')
        self.company = CompanyProfile.objects.create(user=self.user, company_name='Lotus Store')
        self.community = Community.objects.create(name='Local Community', created_by=self.user, purpose='Community', description='Local events')
        self.business = Business.objects.create(owner=self.user, business_name='Lotus', owner_name='Ravi', status='approved')
        self.client.force_login(self.user, backend='django.contrib.auth.backends.ModelBackend')

    def test_event_rejects_excess_words_and_numeric_contact_before_creation(self):
        url = f'/portal/c/{self.community.page_id}/events/create/'
        data = {'name': 'Community Meeting', 'description': 'word ' * 121, 'contact_person': 'Ravi', 'date': '2026-12-01', 'time': '10:00', 'location': 'Hall'}
        self.assertEqual(self.client.post(url, data).status_code, 400)
        self.assertFalse(Event.objects.exists())
        data.update(description='word ' * 120, contact_person='Ravi 123')
        self.assertEqual(self.client.post(url, data).status_code, 400)
        self.assertFalse(Event.objects.exists())
        data['contact_person'] = 'Ravi Kumar'
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.assertEqual(len(Event.objects.get().description.split()), 120)

    def test_offers_require_real_category_and_validity_selection(self):
        base = {'title': 'Special offer', 'business_name': 'Lotus', 'discount_text': '10 percent off'}
        for extra in ({}, {'category': '123456'}, {'category': 'food_restaurant'}, {'category': 'food_restaurant', 'valid_type': 'repeat'}, {'category': 'food_pizza', 'valid_type': 'specific', 'valid_until': '202666-11-20'}):
            response = self.client.post('/offers/post/', {**base, **extra})
            self.assertEqual(response.status_code, 400)
            self.assertFalse(LocalOffer.objects.exists())
        self.assertEqual(self.client.post('/offers/post/', {**base, 'category': 'food_pizza', 'valid_type': 'week'}).status_code, 302)
        today = timezone.localdate()
        self.assertEqual(LocalOffer.objects.get().valid_until, today + timedelta(days=(6 - today.weekday()) % 7 or 7))
        self.assertEqual(self.client.post('/offers/post/', {**base, 'category': 'food_biryani', 'valid_type': 'repeat', 'valid_days': 'Mon,Fri'}).status_code, 302)
        self.assertEqual(LocalOffer.objects.get(category='food_biryani').valid_days, 'Mon,Fri')

    def test_branch_rejects_bad_name_phone_and_numeric_only_address(self):
        base = {'branch_name': 'Main Branch', 'address': 'Market Road 12', 'pincode': '600073', 'contact_number': '9876543210'}
        for changes in ({'branch_name': 'Branch 123'}, {'contact_number': 'letters'}, {'contact_number': '12345678901'}, {'address': '1234567890'}):
            form = BranchForm({**base, **changes})
            self.assertFalse(form.is_valid())
            self.client.post('/vouchers/branches/add/', {**base, **changes})
            self.assertFalse(Branch.objects.exists())
        self.assertTrue(BranchForm(base).is_valid())
        self.assertEqual(self.client.post('/vouchers/branches/add/', base).status_code, 302)
        self.assertEqual(Branch.objects.count(), 1)

    def test_seed_populates_both_category_forms_and_preserves_disabled_categories(self):
        from vouchers.management.commands.seed_voucher_categories import BUSINESS_CATEGORIES
        inactive = BusinessCategory.objects.create(name=BUSINESS_CATEGORIES[0][0], is_active=False)
        call_command('seed_voucher_categories', stdout=StringIO())
        counts = (BusinessCategory.objects.count(), VoucherCategory.objects.count())
        call_command('seed_voucher_categories', stdout=StringIO())
        self.assertEqual(counts, (BusinessCategory.objects.count(), VoucherCategory.objects.count()))
        self.assertTrue(BusinessRegistrationForm().fields['category'].queryset.exists())
        self.assertTrue(GiftVoucherForm(self.business).fields['category'].queryset.exists())
        inactive.refresh_from_db()
        self.assertFalse(inactive.is_active)

    def test_dates_require_four_digit_year_and_portfolio_label_is_optional(self):
        for value in ('202666-11-10', '10/11/202666', '2026-02-30'):
            form = DashboardSeekerForm({'job_category': 'any', 'dob': value})
            self.assertFalse(form.is_valid())
            self.assertIn('dob', form.errors)
            voucher = GiftVoucherForm(self.business, {'valid_from': '2026-11-10', 'expiry_date': value})
            self.assertFalse(voucher.is_valid())
            self.assertIn('expiry_date', voucher.errors)
        form = DashboardSeekerForm({'job_category': 'any', 'dob': '10/11/2000'})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIn('optional', form.fields['portfolio_url'].label.lower())
        self.assertFalse(form.fields['portfolio_url'].required)

    def test_business_flick_links_to_real_profile_and_personal_post_remains_plain(self):
        Flick.objects.create(user=self.user, title='Shop Update', caption='Local news')
        personal = User.objects.create_user('personal-poster', first_name='Personal User')
        Flick.objects.create(user=personal, caption='Personal update')
        response = self.client.get('/flicks/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.company.get_absolute_url())
        self.assertContains(response, self.company.company_id)
        self.assertContains(response, 'Personal User')

    def test_home_signup_has_accessible_password_toggle_target(self):
        self.client.logout()
        self.assertContains(self.client.get('/?signup=1'), 'id="rpPwd" data-password-toggle')
