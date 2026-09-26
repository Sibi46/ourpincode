import json
import re
from datetime import timedelta
from xml.etree import ElementTree

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from jobs.models import CompanyProfile, District, Job, PinCode, State, User
from newsdesk.models import NewsItem


class SEOTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username='seo-business', user_type='company', pincode='600001', city='Chennai')
        cls.business = CompanyProfile.objects.create(user=cls.owner, company_name='Neighbourhood Shop', industry='Retail')
        cls.job = Job.objects.create(posted_by=cls.owner, title='Shop Assistant', location='Chennai',
            collar_type='blue', category='Retail', description='Help local customers with purchases and keep the store organised. Full training is provided.',
            is_approved=True, job_plan='free', status='active')

    def locations(self, response):
        self.assertEqual(response.status_code, 200)
        return [node.text for node in ElementTree.fromstring(response.content).iter('{http://www.sitemaps.org/schemas/sitemap/0.9}loc')]

    def test_robots_public_and_assets_crawlable(self):
        response = self.client.get('/robots.txt', HTTP_USER_AGENT='Googlebot')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response['Content-Type'].startswith('text/plain'))
        self.assertContains(response, 'User-agent: *\nAllow: /')
        self.assertContains(response, 'Sitemap: https://ourpincode.com/sitemap.xml')
        self.assertNotContains(response, 'Disallow: /')

    def test_sitemap_index_uses_canonical_host(self):
        urls = self.locations(self.client.get('/sitemap.xml'))
        self.assertEqual(len(urls), 4)
        for url in urls:
            self.assertTrue(url.startswith('https://ourpincode.com/sitemaps/'))
            self.locations(self.client.get(url.removeprefix('https://ourpincode.com')))

    def test_sitemap_contains_only_eligible_public_pages(self):
        paths = []
        for section in ['pages', 'jobs', 'businesses', 'news']:
            paths.extend(self.locations(self.client.get(f'/sitemaps/{section}.xml')))
        self.assertIn('https://ourpincode.com/', paths)
        self.assertIn(f'https://ourpincode.com/jobs/{self.job.pk}/', paths)
        self.assertIn(f'https://ourpincode.com/business/{self.business.company_id}/', paths)
        for forbidden in ['/admin/', '/login/', '/network/', '/api/', '/coupons/', '/news/birthday/']:
            self.assertFalse(any(forbidden in path for path in paths))

    def test_expired_draft_unapproved_and_thin_jobs_excluded(self):
        for changes in [{'status': 'draft'}, {'is_approved': False}, {'description': 'Short'},
                        {'last_date': timezone.localdate() - timedelta(days=1)},
                        {'plan_expires_at': timezone.localdate() - timedelta(days=1)}]:
            with self.subTest(changes=changes):
                original = {key: getattr(self.job, key) for key in changes}
                Job.objects.filter(pk=self.job.pk).update(**changes)
                self.assertEqual(self.locations(self.client.get('/sitemaps/jobs.xml')), [])
                Job.objects.filter(pk=self.job.pk).update(**original)

    def test_inactive_owners_excluded(self):
        User.objects.filter(pk=self.owner.pk).update(is_active=False)
        for section in ['businesses', 'jobs']:
            self.assertEqual(self.locations(self.client.get(f'/sitemaps/{section}.xml')), [])

    def test_empty_directories_are_noindex(self):
        Job.objects.all().delete()
        response = self.client.get('/jobs/')
        self.assertContains(response, 'content="noindex,follow"')
        self.assertEqual(response['X-Robots-Tag'], 'noindex, follow')
        self.assertNotIn('https://ourpincode.com/jobs/', self.locations(self.client.get('/sitemaps/pages.xml')))

    def test_home_metadata_and_json_ld(self):
        response = self.client.get('/', HTTP_USER_AGENT='Googlebot')
        self.assertContains(response, '<title>OURPINCODE | Local Jobs, Businesses &amp; Community</title>', html=True)
        self.assertContains(response, '<link rel="canonical" href="https://ourpincode.com/">', html=True)
        self.assertContains(response, 'content="index,follow"')
        self.assertNotIn('X-Robots-Tag', response)
        self.assertContains(response, 'property="og:title"')
        self.assertContains(response, 'name="twitter:card"')
        graph = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', response.content.decode()).group(1))
        self.assertEqual(graph['@context'], 'https://schema.org')
        self.assertEqual([item['@type'] for item in graph['@graph']], ['Organization', 'WebSite'])
        self.assertEqual(response.content.decode().count('name="description"'), 1)

    def test_unique_public_metadata(self):
        titles = []
        for path in ['/', '/jobs/', '/businesses/', f'/jobs/{self.job.pk}/', f'/business/{self.business.company_id}/']:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'content="index,follow"')
            titles.append(re.search(r'<title>(.*?)</title>', response.content.decode()).group(1))
        self.assertEqual(len(set(titles)), len(titles))

    def test_filters_and_private_routes_noindex(self):
        for path in ['/jobs/?q=assistant', '/businesses/?page=2', '/login/', '/admin/', '/network/', '/api/check-phone/', '/missing-page/']:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertIn('noindex', response['X-Robots-Tag'])

    def test_tracking_urls_consolidate_without_noindex(self):
        response = self.client.get('/?utm_source=test')
        self.assertContains(response, 'href="https://ourpincode.com/"')
        self.assertNotIn('X-Robots-Tag', response)

    def test_www_redirect_preserves_path_and_query(self):
        response = self.client.get('/jobs/?q=shop', HTTP_HOST='www.ourpincode.com', secure=True)
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response['Location'], 'https://ourpincode.com/jobs/?q=shop')

    @override_settings(SECURE_SSL_REDIRECT=True)
    def test_http_redirects_to_https(self):
        response = self.client.get('/jobs/', HTTP_HOST='ourpincode.com')
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response['Location'], 'https://ourpincode.com/jobs/')

    def test_post_is_not_redirected_by_canonical_middleware(self):
        response = self.client.post('/login/', {}, HTTP_HOST='www.ourpincode.com', secure=True)
        self.assertNotEqual(response.status_code, 301)

    def test_private_authenticated_page_stays_noindex(self):
        self.client.force_login(self.owner)
        response = self.client.get('/network/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('noindex', response['X-Robots-Tag'])

    def test_metadata_escapes_user_content(self):
        Job.objects.filter(pk=self.job.pk).update(title='<script>alert(1)</script>')
        response = self.client.get(f'/jobs/{self.job.pk}/')
        self.assertNotContains(response, '<title><script>')
        self.assertContains(response, '&lt;script&gt;')

    def test_news_only_published_substantive_active_pincode_stories(self):
        state = State.objects.create(name='SEO state', code='SE')
        district = District.objects.create(name='SEO district', state=state)
        pin = PinCode.objects.create(code='600001', district=district)
        story = NewsItem.objects.create(author=self.owner, pincode=pin, title='Neighbourhood park opens',
            body='The neighbourhood park has opened with walking paths and a play area. Residents can visit every morning.', status='published')
        expected = f'https://ourpincode.com/news/stories/{story.pk}/'
        self.assertIn(expected, self.locations(self.client.get('/sitemaps/news.xml')))
        response = self.client.get(f'/news/stories/{story.pk}/')
        self.assertContains(response, 'Neighbourhood park opens | OURPINCODE News')
        self.assertContains(response, 'content="index,follow"')
        for changes in [{'status': 'draft'}, {'category': 'birthday'}, {'body': 'Thin'},
                        {'published_at': timezone.now() + timedelta(days=1)}]:
            with self.subTest(changes=changes):
                original = {key: getattr(story, key) for key in changes}
                NewsItem.objects.filter(pk=story.pk).update(**changes)
                self.assertEqual(self.locations(self.client.get('/sitemaps/news.xml')), [])
                NewsItem.objects.filter(pk=story.pk).update(**original)
        pin.is_active = False
        pin.save()
        self.assertEqual(self.locations(self.client.get('/sitemaps/news.xml')), [])

    def test_sitemap_pagination(self):
        from unittest.mock import patch
        from jobportal.seo import PublicPagesSitemap
        with patch.object(PublicPagesSitemap, 'limit', 1):
            urls = self.locations(self.client.get('/sitemap.xml'))
            self.assertIn('https://ourpincode.com/sitemaps/pages.xml?p=2', urls)
            self.assertEqual(len(self.locations(self.client.get('/sitemaps/pages.xml?p=2'))), 1)
