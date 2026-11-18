import json
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase

from .models import District, PinCode, State


class PostalAreaTests(TestCase):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    @patch('urllib.request.urlopen')
    def test_main_post_office_wins_over_first_alphabetical_branch(self, lookup):
        state = State.objects.create(name='Tamil Nadu')
        district = District.objects.create(name='Tiruvannamalai', state=state)
        PinCode.objects.create(code='604408', area_name='Alathur', district=district)
        offices = [{'Name': 'Alathur', 'BranchType': 'Branch Post Office'},
                   {'Name': 'Vandavasi', 'BranchType': 'Sub Post Office'}]
        for office in offices:
            office.update(District=district.name, State=state.name)
        lookup.return_value.__enter__.return_value.read.return_value = json.dumps(
            [{'Status': 'Success', 'PostOffice': offices}]).encode()
        data = self.client.get('/api/pincode/604408/').json()
        self.assertEqual(data['area'], 'Vandavasi')
        self.assertEqual(data['areas'], ['Alathur', 'Vandavasi'])
        self.client.get('/api/pincode/604408/')
        self.assertEqual(lookup.call_count, 1)

    @patch('urllib.request.urlopen', side_effect=OSError('offline'))
    def test_local_fallback_on_outage(self, lookup):
        state = State.objects.create(name='Tamil Nadu')
        district = District.objects.create(name='Tiruvannamalai', state=state)
        PinCode.objects.create(code='604408', area_name='Vandavasi', district=district)
        self.assertEqual(self.client.get('/api/pincode/604408/').json()['area'], 'Vandavasi')

    @patch('urllib.request.urlopen')
    def test_invalid_pin_never_calls_external_service(self, lookup):
        self.assertFalse(self.client.get('/api/pincode/000000/').json()['success'])
        lookup.assert_not_called()

    @patch('jobs.postal_areas.geoapify_lookup', return_value=None)
    @patch('urllib.request.urlopen')
    def test_selaiyur_is_default_for_shared_600073_pin_in_any_order(self, lookup, geo):
        offices = [
            {'Name': 'Gowriwakkam', 'BranchType': 'Sub Post Office'},
            {'Name': 'Rajakilpakkam', 'BranchType': 'Branch Post Office'},
            {'Name': 'Selaiyur', 'BranchType': 'Sub Post Office'},
        ]
        for office in offices:
            office.update(District='Kanchipuram', State='Tamil Nadu')
        for ordered in [offices, list(reversed(offices))]:
            cache.clear()
            lookup.return_value.__enter__.return_value.read.return_value = json.dumps(
                [{'Status': 'Success', 'PostOffice': ordered}]).encode()
            data = self.client.get('/api/pincode/600073/').json()
            self.assertEqual(data['area'], 'Selaiyur')
            self.assertEqual(data['areas'], ['Gowriwakkam', 'Rajakilpakkam', 'Selaiyur'])

    @patch('jobs.postal_areas.geoapify_lookup', return_value=None)
    @patch('urllib.request.urlopen')
    def test_preference_does_not_invent_an_office_missing_from_provider(self, lookup, geo):
        lookup.return_value.__enter__.return_value.read.return_value = json.dumps(
            [{'Status': 'Success', 'PostOffice': [{'Name': 'Gowriwakkam', 'BranchType': 'Sub Post Office',
             'District': 'Kanchipuram', 'State': 'Tamil Nadu'}]}]).encode()
        self.assertEqual(self.client.get('/api/pincode/600073/').json()['area'], 'Gowriwakkam')
