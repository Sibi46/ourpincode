"""Conservative public indexing policy, shared by metadata and sitemaps."""
import json
from types import SimpleNamespace
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.sitemaps import Sitemap
from django.db.models import Q
from django.db.models.functions import Length, Trim
from django.http import HttpResponse, HttpResponsePermanentRedirect
from django.urls import reverse
from django.utils import timezone
from django.utils.html import strip_tags
from django.views.decorators.http import require_safe
from django.shortcuts import render


def origin():
    return settings.SITE_URL.rstrip('/')


def public_jobs():
    from jobs.models import Job, User
    today = timezone.localdate()
    return Job.objects.filter(
        status='active', is_approved=True, job_plan__in=['free', 'paid'],
        posted_by__is_active=True, posted_by__user_type__in=User.EMPLOYER_TYPES,
    ).filter(Q(last_date__isnull=True) | Q(last_date__gte=today)).filter(
        Q(plan_expires_at__isnull=True) | Q(plan_expires_at__gte=today),
    ).annotate(seo_length=Length(Trim('description'))).filter(seo_length__gte=80).exclude(title='').exclude(location='')


def public_businesses():
    from jobs.models import CompanyProfile, User
    return CompanyProfile.objects.filter(
        user__is_active=True, user__user_type__in=User.EMPLOYER_TYPES,
    ).exclude(company_name='').exclude(company_id='').exclude(industry='').exclude(user__pincode='')


def public_stories():
    from newsdesk.permissions import published_items
    return published_items().exclude(category='birthday').exclude(title='').annotate(
        seo_length=Length(Trim('body')),
    ).filter(seo_length__gte=80)


def summary(text):
    return ' '.join(strip_tags(text).split())[:160]


def metadata(request):
    if hasattr(request, '_seo_metadata'):
        return request._seo_metadata
    match = request.resolver_match
    name = match.view_name if match else ''
    data = {
        'title': 'OURPINCODE',
        'description': "OUR PINCODE — Business, Opportunity, Job at Near You. Find Jobs Near You. Hire People Near You. India's PIN-code based hyperlocal job portal.",
        'canonical': origin() + request.path, 'indexable': False, 'type': 'website',
        'image': origin() + '/static/images/ourpincod.jpeg',
    }
    if name == 'home':
        data.update(title='OURPINCODE | Local Jobs, Businesses & Community',
                    description='Discover nearby businesses, jobs, local offers and community news. Connect with your neighbourhood by pincode on OURPINCODE.', indexable=True)
    elif name == 'job_list':
        data.update(title='Jobs Near You by Pincode | OURPINCODE',
                    description='Find local job opportunities by pincode, job role and location. Explore nearby employers and apply through OURPINCODE.', indexable=public_jobs().exists())
    elif name == 'business_list':
        data.update(title='Local Businesses & Shops Near You | OURPINCODE',
                    description='Discover businesses and shops in your pincode. Explore local business profiles, offers and opportunities on OURPINCODE.', indexable=public_businesses().exists())
    elif name == 'job_detail':
        job = public_jobs().filter(pk=match.kwargs['pk']).first()
        if job:
            data.update(title=f'{job.title} in {job.location} | OURPINCODE', description=summary(job.description), indexable=True)
    elif name == 'business_profile':
        business = public_businesses().select_related('user').filter(company_id=match.kwargs['company_id']).first()
        if business:
            place = business.user.city or business.user.pincode
            data.update(title=f'{business.company_name} in {place} | OURPINCODE',
                        description=summary(f'Explore {business.company_name}, {business.industry} in {place}, pincode {business.user.pincode}. View its business profile, local offers and job opportunities.'), indexable=True)
    elif name == 'newsdesk:detail':
        story = public_stories().filter(pk=match.kwargs['pk']).first()
        if story:
            data.update(title=f'{story.title} | OURPINCODE News', description=summary(story.body), indexable=True, type='article')
    # Search/filter/pagination variants remain crawlable but are not search landing pages.
    # Tracking-only URLs consolidate to the clean URL without a conflicting noindex.
    if any(not (key.startswith('utm_') or key in {'gclid', 'fbclid'}) for key in request.GET):
        data['indexable'] = False
    data['robots'] = 'index,follow' if data['indexable'] else 'noindex,follow'
    if name == 'home':
        graph = {'@context': 'https://schema.org', '@graph': [
            {'@type': 'Organization', '@id': origin() + '/#organization', 'name': 'OURPINCODE', 'url': origin() + '/', 'logo': data['image']},
            {'@type': 'WebSite', '@id': origin() + '/#website', 'name': 'OURPINCODE', 'url': origin() + '/', 'publisher': {'@id': origin() + '/#organization'}},
        ]}
        # Safe inside a script element even if configurable values contain HTML.
        data['json_ld'] = json.dumps(graph).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    request._seo_metadata = data
    return data


def seo_context(request):
    return {'seo': metadata(request)}


class SEOMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Only canonicalize safe page requests on the known production alias.
        # Leave local development, alternate configured sites, and POSTs intact.
        if (request.method in {'GET', 'HEAD'} and request.get_host().split(':')[0] == 'www.ourpincode.com'
                and urlsplit(origin()).hostname == 'ourpincode.com'):
            return HttpResponsePermanentRedirect(origin() + request.get_full_path())
        response = self.get_response(request)
        if request.path.startswith(('/static/', '/media/')):
            return response
        if request.path in {'/robots.txt', '/sitemap.xml'} or request.path.startswith('/sitemaps/'):
            return response
        content_type = response.get('Content-Type', '')
        indexable = (response.status_code == 200 and request.method in {'GET', 'HEAD'}
                     and 'text/html' in content_type and metadata(request)['indexable'])
        if not indexable and 'X-Robots-Tag' not in response:
            response['X-Robots-Tag'] = 'noindex, follow'
        return response


@require_safe
def robots(request):
    # Do not disallow private URLs here: crawlers must see their noindex header.
    # Authentication remains the access control, never robots.txt.
    return HttpResponse('User-agent: *\nAllow: /\n\nSitemap: ' + origin() + '/sitemap.xml\n', content_type='text/plain; charset=utf-8')


class CanonicalSitemap(Sitemap):
    protocol = 'https'
    limit = 1000

    def get_urls(self, page=1, site=None, protocol=None):
        return super().get_urls(page=page, site=SimpleNamespace(domain=urlsplit(origin()).netloc), protocol=urlsplit(origin()).scheme)


class PublicPagesSitemap(CanonicalSitemap):
    def items(self):
        pages = ['home']
        if public_jobs().exists():
            pages.append('job_list')
        if public_businesses().exists():
            pages.append('business_list')
        return pages

    def location(self, item):
        return reverse(item)


class JobsSitemap(CanonicalSitemap):
    def items(self):
        return public_jobs().order_by('pk')

    def location(self, item):
        return reverse('job_detail', args=[item.pk])


class BusinessesSitemap(CanonicalSitemap):
    def items(self):
        return public_businesses().order_by('pk')

    def location(self, item):
        return reverse('business_profile', args=[item.company_id])


class NewsSitemap(CanonicalSitemap):
    def items(self):
        return public_stories().order_by('pk')

    def location(self, item):
        return reverse('newsdesk:detail', args=[item.pk])

    def lastmod(self, item):
        return item.updated_at


SITEMAPS = {'pages': PublicPagesSitemap, 'jobs': JobsSitemap, 'businesses': BusinessesSitemap, 'news': NewsSitemap}


@require_safe
def sitemap_index(request):
    sections = []
    for name, sitemap_class in SITEMAPS.items():
        sitemap = sitemap_class()
        if not sitemap.paginator.count:
            continue
        base = origin() + reverse('seo_sitemap', kwargs={'section': name})
        for page in range(1, sitemap.paginator.num_pages + 1):
            sections.append({'location': base + (f'?p={page}' if page > 1 else '')})
    return render(request, 'sitemap_index.xml', {'sitemaps': sections}, content_type='application/xml')
