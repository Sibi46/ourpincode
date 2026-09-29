from django.test import Client, TestCase
from django.urls import reverse

from .assigned_admin import SECTIONS, scoped_records
from .models import AdminProfile, District, Job, PinCode, State, User, SystemNotification


class AssignedAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.main = User.objects.create_user('main', admin_role='super_admin')
        cls.owner = User.objects.create_user('owner', user_type='company')
        cls.admin = User.objects.create_user('9000000091', phone='9000000091', password='Secure-admin-123!', admin_role='scoped_admin')
        cls.tn = State.objects.create(name='Tamil Nadu', code='TN')
        cls.delhi = State.objects.create(name='Delhi', code='DL')
        for state, code in [(cls.tn, '600001'), (cls.delhi, '110001')]:
            district = District.objects.create(state=state, name=state.name)
            PinCode.objects.create(district=district, code=code)
        cls.profile = AdminProfile.objects.create(user=cls.admin, role='scoped_admin', state=cls.tn, sections=['jobs'])
        cls.local = Job.objects.create(posted_by=cls.owner, title='Chennai vacancy', pincode='600001', latitude=13, longitude=80)
        cls.remote = Job.objects.create(posted_by=cls.owner, title='Delhi vacancy', pincode='110001', latitude=28, longitude=77)
        cls.unknown = Job.objects.create(posted_by=cls.owner, title='Unknown location', pincode='999999', latitude=28, longitude=77)

    def setUp(self):
        self.client.force_login(self.admin)

    def action(self, obj, action='approve', client=None):
        return (client or self.client).post(reverse('assigned_action', args=['jobs', obj.pk]), {'action': action})

    def test_only_assigned_state_visible(self):
        response = self.client.get(reverse('assigned_section', args=['jobs']))
        self.assertContains(response, 'Chennai vacancy')
        self.assertNotContains(response, 'Delhi vacancy')
        self.assertNotContains(response, 'Unknown location')

    def test_cross_state_and_unknown_writes_rejected(self):
        for obj in (self.remote, self.unknown):
            self.assertEqual(self.action(obj).status_code, 404)
            obj.refresh_from_db()
            self.assertFalse(obj.is_approved)

    def test_own_state_can_approve(self):
        self.assertEqual(self.action(self.local).status_code, 302)
        self.local.refresh_from_db()
        self.assertTrue(self.local.is_approved)
        self.assertEqual(self.local.status, 'active')
        self.assertEqual(self.owner.notifications.count(), 1)

    def test_unassigned_section_denied(self):
        self.assertEqual(self.client.get(reverse('assigned_section', args=['news'])).status_code, 403)
        self.assertEqual(self.client.post(reverse('assigned_action', args=['news', 1]), {'action': 'publish'}).status_code, 403)

    def test_old_admin_endpoints_cannot_bypass_scope(self):
        for url in ('/district-admin/jobs/', '/super-admin/team/', '/super-admin/users/', '/admin/', '/news/manage/'):
            response = self.client.post(url, {'job_id': self.remote.pk, 'action': 'approve'})
            self.assertIn(response.status_code, (403, 404))
        self.remote.refresh_from_db()
        self.assertFalse(self.remote.is_approved)

    def test_national_section_admin(self):
        self.profile.all_states = True
        self.profile.state = None
        self.profile.save()
        self.assertContains(self.client.get(reverse('assigned_section', args=['jobs'])), 'Delhi vacancy')
        self.assertEqual(self.action(self.remote).status_code, 302)
        self.assertEqual(self.client.get(reverse('assigned_section', args=['offers'])).status_code, 403)

    def test_missing_or_disabled_assignment_fails_closed(self):
        self.profile.state = None
        self.profile.save()
        self.assertEqual(self.client.get(reverse('assigned_dashboard')).status_code, 403)
        self.profile.state = self.tn
        self.profile.is_active = False
        self.profile.save()
        self.assertEqual(self.client.get(reverse('assigned_dashboard')).status_code, 404)

    def test_main_admin_keeps_full_access(self):
        self.client.force_login(self.main)
        SystemNotification.objects.create(title='Maintenance notice', message='Test announcement')
        response = self.client.get(reverse('super_admin_dashboard'))
        self.assertContains(response, 'Create admin')
        self.assertContains(response, 'Maintenance notice')
        self.assertLess(response.content.index(b'admin-notifications'), response.content.index(b'news-management'))
        self.assertContains(self.client.get(reverse('manage_assigned_admins')), 'Create an admin')
        self.assertEqual(self.action(self.remote).status_code, 302)

    def account_payload(self, **extra):
        data = {'first_name': 'Delhi Admin', 'username': '9000000092', 'phone': '9000000092', 'password1': 'Strong-team-849!', 'password2': 'Strong-team-849!', 'state': self.delhi.pk, 'sections': ['jobs', 'news']}
        data.update(extra)
        return data

    def test_create_admin_and_login(self):
        self.client.force_login(self.main)
        response = self.client.post(reverse('manage_assigned_admins'), self.account_payload(is_superuser='on', admin_role='super_admin'))
        self.assertRedirects(response, reverse('manage_assigned_admins'))
        user = User.objects.get(username='9000000092')
        self.assertEqual(user.admin_role, 'scoped_admin')
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(user.admin_profile.state, self.delhi)
        self.client.logout()
        self.assertTrue(self.client.login(username=user.phone, password='Strong-team-849!'))
        self.assertRedirects(self.client.get(reverse('dashboard')), reverse('assigned_dashboard'))

    def test_invalid_creation_does_not_create_account(self):
        self.client.force_login(self.main)
        for extra in ({'sections': []}, {'state': ''}, {'password2': 'mismatch'}, {'sections': ['billing']}, {'phone': self.admin.phone}):
            self.client.post(reverse('manage_assigned_admins'), self.account_payload(**extra))
            self.assertFalse(User.objects.filter(username='9000000092').exists())

    def test_changes_and_suspension_apply_to_existing_sessions(self):
        manager = Client()
        manager.force_login(self.main)
        response = manager.post(reverse('edit_assigned_admin', args=[self.profile.pk]), {'state': self.delhi.pk, 'sections': ['jobs']})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.action(self.local).status_code, 404)
        self.assertEqual(self.action(self.remote).status_code, 302)
        manager.post(reverse('toggle_assigned_admin', args=[self.profile.pk]))
        self.assertEqual(self.action(self.remote).status_code, 302)  # Login required after suspension.
        self.assertFalse(User.objects.get(pk=self.admin.pk).is_active)

    def test_csrf_and_post_required(self):
        url = reverse('assigned_action', args=['jobs', self.local.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        self.assertEqual(client.post(url, {'action': 'approve'}).status_code, 403)

    def test_all_section_queries_and_templates(self):
        self.profile.sections = list(SECTIONS)
        self.profile.save()
        for section in SECTIONS:
            with self.subTest(section=section):
                list(scoped_records(self.admin, section))
                self.assertEqual(self.client.get(reverse('assigned_section', args=[section])).status_code, 200)

    def test_non_admin_denied(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse('assigned_dashboard')).status_code, 403)
        self.assertEqual(self.client.post(reverse('manage_assigned_admins'), self.account_payload()).status_code, 403)

    def test_scoping_and_actions_for_other_sections(self):
        from newsdesk.models import NewsItem
        from portal.models import Community
        from quiz.models import Quiz
        from coupons.models import Salesman, Shop
        from vouchers.models import Business
        from .models import AdPost, Flick, LocalOffer
        self.profile.sections = list(SECTIONS)
        self.profile.save()
        owners = [self.owner, User.objects.create_user('delhi-owner', pincode='110001')]
        self.owner.pincode = '600001'
        self.owner.save()
        salesman = Salesman.objects.create(user=User.objects.create_user('salesman'))
        for section in SECTIONS:
            if section == 'jobs':
                continue
            objects = []
            for owner, pin in zip(owners, ('600001', '110001')):
                common = {'title': f'{section} {pin}'}
                if section == 'news':
                    obj = NewsItem.objects.create(author=owner, pincode=PinCode.objects.get(code=pin), body='Local news', **common)
                elif section == 'offers':
                    obj = LocalOffer.objects.create(owner=owner, business_name='Shop', discount_text='10%', is_active=False, **common)
                elif section == 'ads':
                    obj = AdPost.objects.create(user=owner, pincode=pin, company_name=common['title'])
                elif section == 'community':
                    obj = Community.objects.create(created_by=owner, pincode=pin, name=common['title'])
                elif section == 'quiz':
                    obj = Quiz.objects.create(created_by=owner, pincode=pin, is_active=False, **common)
                elif section == 'coupons':
                    obj = Shop.objects.create(salesman=salesman, pincode=pin, name=common['title'], is_active=False)
                elif section == 'vouchers':
                    obj = Business.objects.create(owner=owner, pincode=pin, business_name=common['title'])
                else:
                    obj = Flick.objects.create(user=owner, **common)
                objects.append(obj)
            with self.subTest(section=section):
                self.assertEqual(list(scoped_records(self.admin, section)), [objects[0]])
                action = SECTIONS[section][4][0]
                payload = {'action': action, 'confirm': 'yes'}
                self.assertEqual(self.client.post(reverse('assigned_action', args=[section, objects[1].pk]), payload).status_code, 404)
                self.assertEqual(self.client.post(reverse('assigned_action', args=[section, objects[0].pk]), payload).status_code, 302)
                if section == 'flicks':
                    self.assertFalse(Flick.objects.filter(pk=objects[0].pk).exists())
                else:
                    objects[0].refresh_from_db()
                    if section == 'news':
                        self.assertEqual(objects[0].status, 'published')
                        self.assertIsNotNone(objects[0].published_at)
                    elif section in ('ads', 'vouchers'):
                        self.assertEqual(objects[0].status, 'approved')
                    else:
                        self.assertTrue(objects[0].is_active)

    def test_username_creation_without_phone_and_real_admin_login(self):
        from django.core.cache import cache
        from .models import AdminActivity
        cache.clear()
        self.client.force_login(self.main)
        payload = self.account_payload(username='delhi.manager', phone='')
        response = self.client.post(reverse('manage_assigned_admins'), payload)
        self.assertRedirects(response, reverse('manage_assigned_admins'))
        user = User.objects.get(username='delhi.manager')
        self.assertTrue(user.check_password(payload['password1']))
        self.assertFalse(user.is_staff)
        self.client.logout()
        self.assertContains(self.client.get(reverse('assigned_login')), 'Admin login')
        response = self.client.post(reverse('assigned_login'), {'username': 'delhi.manager', 'password': payload['password1']}, follow=True)
        self.assertContains(response, 'Delhi dashboard')
        self.assertTrue(AdminActivity.objects.filter(actor=user, action='login').exists())
        self.assertTrue(AdminActivity.objects.filter(action='create_admin', target_name='delhi.manager').exists())
        self.assertNotIn(payload['password1'], str(list(AdminActivity.objects.values())))

    def test_username_collision_case_and_phone_alias(self):
        from .assigned_admin import AdminAccountForm
        User.objects.create_user('DELHI.manager')
        for username in ('delhi.manager', self.admin.phone):
            self.assertFalse(AdminAccountForm(self.account_payload(username=username)).is_valid())

    def test_all_features_can_be_switched_off_immediately(self):
        from .models import AdminActivity
        manager = Client()
        manager.force_login(self.main)
        response = manager.post(reverse('edit_assigned_admin', args=[self.profile.pk]), {'state': self.tn.pk, 'sections': []})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.action(self.local).status_code, 403)
        response = self.client.get(reverse('assigned_dashboard'))
        self.assertContains(response, '0 sections enabled')
        self.assertNotContains(response, 'Manage Jobs')
        self.assertTrue(AdminActivity.objects.filter(action='change_access', target_id=str(self.admin.pk)).exists())

    def test_moderation_audited_and_denied_action_not_recorded(self):
        from .models import AdminActivity
        self.assertEqual(self.action(self.local).status_code, 302)
        log = AdminActivity.objects.get(section='jobs', action='approve')
        self.assertEqual(log.actor, self.admin)
        self.assertEqual(log.target_id, str(self.local.pk))
        self.assertEqual(log.state_name, 'Tamil Nadu')
        self.assertFalse(log.details['before']['is_approved'])
        self.assertTrue(log.details['after']['is_approved'])
        self.assertEqual(self.action(self.remote).status_code, 404)
        self.assertEqual(AdminActivity.objects.filter(section='jobs').count(), 1)
        self.client.force_login(self.main)
        response = self.client.get(reverse('admin_activity'), {'actor': self.admin.username, 'section': 'jobs'})
        self.assertContains(response, self.local.title)
        self.assertNotContains(response, self.remote.title)

    def test_audit_failure_rolls_back_action(self):
        from unittest.mock import patch
        with patch('jobs.assigned_admin.record_activity', side_effect=RuntimeError('audit unavailable')):
            with self.assertRaises(RuntimeError):
                self.action(self.local)
        self.local.refresh_from_db()
        self.assertFalse(self.local.is_approved)
        self.assertFalse(self.owner.notifications.exists())

    def test_assigned_admin_cannot_read_global_history(self):
        self.assertRedirects(self.client.get(reverse('admin_activity')), reverse('assigned_dashboard'))
        self.assertEqual(self.client.post(reverse('admin_activity')).status_code, 403)

    def test_dashboard_counts_are_state_and_section_scoped(self):
        response = self.client.get(reverse('assigned_dashboard'))
        self.assertEqual(response.context['record_count'], 1)
        self.assertEqual(response.context['enabled_count'], 1)
        disabled = [s for s in response.context['sections'] if not s['enabled']]
        self.assertTrue(all(s['count'] is None for s in disabled))
        self.assertContains(response, 'Tamil Nadu dashboard')

    def test_login_rejects_suspended_user_and_limits_attempts(self):
        from django.core.cache import cache
        cache.clear()
        self.client.logout()
        self.admin.is_active = False
        self.admin.save()
        response = self.client.post(reverse('assigned_login'), {'username': self.admin.username, 'password': 'Secure-admin-123!'})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)
        for _ in range(5):
            response = self.client.post(reverse('assigned_login'), {'username': 'missing', 'password': 'wrong'})
        self.assertContains(response, 'Too many attempts')
