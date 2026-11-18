import json
from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings
from django.core.cache import cache


@override_settings(GEOAPIFY_API_KEY='test-private-key')
class GeoapifyLookupTests(TestCase):
    def setUp(self):
        cache.clear()
    def tearDown(self):
        cache.clear()
    def response(self,payload):
        r=MagicMock();r.__enter__.return_value.read.return_value=json.dumps(payload).encode();return r
    def postal(self):
        return [{'Status':'Success','PostOffice':[{'Name':'Medavakkam','BranchType':'Sub Post Office','District':'Kanchipuram','State':'Tamil Nadu'}]}]
    def geo(self,**changes):
        return {'results':[dict(country_code='in',postcode='600100',city='Chennai',suburb='Medavakkam',county='Do not use as city',state='Tamil Nadu',**changes)]}

    @patch('urllib.request.urlopen')
    def test_exact_area_and_pin_enrich_city_and_keep_postal_area(self,call):
        call.side_effect=[self.response(self.postal()),self.response(self.geo())]
        r=self.client.get('/api/pincode/600100/');data=r.json()
        self.assertEqual((data['area'],data['city'],data['district']),('Medavakkam','Chennai','Kanchipuram'))
        self.assertEqual(data['source'],'postal+geoapify')
        self.assertNotIn('test-private-key',r.content.decode())
        self.client.get('/api/pincode/600100/');self.assertEqual(call.call_count,2)
        self.assertIn('filter=countrycode%3Ain',call.call_args.args[0])

    @patch('urllib.request.urlopen')
    def test_unmatched_pin_or_area_never_fills_city(self,call):
        for field,value in [('postcode','600001'),('suburb','Wrong Area'),('country_code','us')]:
            cache.clear();geo=self.geo();geo['results'][0][field]=value
            call.side_effect=[self.response(self.postal()),self.response(geo)]
            data=self.client.get('/api/pincode/600100/').json()
            self.assertEqual(data['city'],'');self.assertEqual(data['source'],'postal')

    @patch('urllib.request.urlopen')
    def test_missing_city_does_not_use_county_as_city(self,call):
        geo=self.geo();del geo['results'][0]['city']
        call.side_effect=[self.response(self.postal()),self.response(geo)]
        self.assertEqual(self.client.get('/api/pincode/600100/').json()['city'],'')

    @patch('urllib.request.urlopen')
    def test_provider_outage_keeps_postal_fallback_and_backs_off(self,call):
        call.side_effect=[self.response(self.postal()),OSError('offline')]
        self.assertEqual(self.client.get('/api/pincode/600100/').json()['source'],'postal')
        self.assertTrue(cache.get('geoapify-backoff'))

    @override_settings(GEOAPIFY_API_KEY='')
    @patch('urllib.request.urlopen')
    def test_without_key_only_postal_service_used(self,call):
        call.return_value=self.response(self.postal())
        self.assertEqual(self.client.get('/api/pincode/600100/').json()['source'],'postal');self.assertEqual(call.call_count,1)

    @patch('urllib.request.urlopen')
    def test_geo_lookup_available_when_postal_service_down(self,call):
        call.side_effect=[OSError('offline'),self.response(self.geo())]
        self.assertEqual(self.client.get('/api/pincode/600100/').json()['city'],'Chennai')
