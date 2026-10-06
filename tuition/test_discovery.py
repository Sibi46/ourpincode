"""Focused PIN-search and discovery UI regressions."""
from django.test import TestCase
from django.urls import reverse
from . import models as m, tests as fixtures


class DiscoveryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixtures.TuitionTests.setUpTestData.__func__(cls)
        cls.second = m.TeacherProfile.objects.create(owner=cls.other, name='Neighbourhood Maths',
            pincode='600002', phone='9000000002', status='approved')
        m.ServiceArea.objects.create(teacher=cls.teacher, pincode='600003')
        m.ServiceArea.objects.create(teacher=cls.teacher, pincode='600004')

    def search(self, value):
        return self.client.get(reverse('tuition:discover'), {'pincode': value})

    def test_three_pins_match_location_or_service_area_without_duplicates(self):
        response = self.search('600002, 600003, 600004')
        self.assertEqual({row.pk for row in response.context['teachers']}, {self.teacher.pk, self.second.pk})
        self.assertEqual(response.context['teachers'].paginator.count, 2)

    def test_single_unregistered_pin_spaces_and_duplicates(self):
        self.assertEqual([row.pk for row in self.search('999999').context['teachers']], [self.teacher.pk])
        response = self.search('999999 600002 999999')
        self.assertEqual(response.context['teachers'].paginator.count, 2)
        self.assertEqual(response.context['search'].cleaned_data['pincode'], ['999999', '600002'])

    def test_invalid_pins_fail_closed_with_visible_errors(self):
        for value in ('123', '600001,600002,600003,600004', 'abc123', ',', '６００００１'):
            with self.subTest(value=value):
                response = self.search(value)
                self.assertIn('pincode', response.context['search'].errors)
                self.assertEqual(response.context['teachers'].paginator.count, 0)
                self.assertContains(response, 'Enter up to 3 complete six-digit PIN codes')

    def test_pending_or_inactive_teacher_not_discovered(self):
        self.second.status = 'pending'; self.second.save()
        self.assertEqual(self.search('600002').context['teachers'].paginator.count, 0)
        self.owner.is_active = False; self.owner.save()
        self.assertEqual(self.search('600003').context['teachers'].paginator.count, 0)

    def test_page_uses_pin_search_without_coordinate_controls(self):
        response = self.search('')
        self.assertTemplateUsed(response, 'tuition/discover.html')
        self.assertContains(response, 'Up to 3 six-digit PIN codes')
        for name in ('latitude', 'longitude', 'radius'):
            self.assertNotContains(response, 'name="'+name+'"')
        self.assertContains(response, 'More filters')
        self.assertContains(response, reverse('tuition:profile', args=[self.teacher.slug]))
