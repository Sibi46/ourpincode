"""Resolve postal towns without treating the first branch office as the town."""
import json
import re
import urllib.request
from urllib.parse import urlencode
from django.conf import settings

from django.core.cache import cache
from django.http import JsonResponse

from .models import PinCode


def geoapify_lookup(pin, area='', state=''):
    api_key = getattr(settings, 'GEOAPIFY_API_KEY', '')
    if not api_key or cache.get('geoapify-backoff'):
        return None
    params = {'filter': 'countrycode:in', 'format': 'json', 'lang': 'en', 'limit': 5, 'apiKey': api_key}
    if area:
        params['text'] = f'{area} {pin} {state} India'
    else:
        params.update(postcode=pin, country='India', type='postcode')
    query = urlencode(params)
    try:
        with urllib.request.urlopen('https://api.geoapify.com/v1/geocode/search?' + query, timeout=4) as response:
            payload = json.loads(response.read())
        for item in payload.get('results', []):
            if item.get('country_code', '').lower() != 'in' or str(item.get('postcode', '')).strip() != pin:
                continue
            city = (item.get('city') or item.get('town') or item.get('village') or '').strip()
            matched_area = (item.get('suburb') or item.get('quarter') or item.get('name') or '').strip()
            if area and matched_area.casefold() != area.casefold():
                continue
            if not city or not item.get('state'):
                continue
            return {'success': True, 'area': area or matched_area or city, 'city': city,
                    'district': '', 'state': item['state'].strip(),
                    'areas': [area or matched_area or city], 'source': 'geoapify'}
    except (OSError, ValueError, KeyError, IndexError, TypeError, AttributeError):
        # Do not log exceptions: provider URLs contain the private API key.
        cache.set('geoapify-backoff', True, 60)
    return None


def pincode_lookup(request, pin):
    if not re.fullmatch(r'[1-9][0-9]{5}', pin):
        return JsonResponse({'success': False, 'error': 'Invalid PIN code'})
    key = 'postal-areas-v3:' + ('geo:' if getattr(settings, 'GEOAPIFY_API_KEY', '') else 'postal:') + pin
    result = cache.get(key)
    if result:
        return JsonResponse(result)
    geo = None
    try:
        with urllib.request.urlopen('https://api.postalpincode.in/pincode/' + pin, timeout=5) as response:
            data = json.loads(response.read())
        offices = data[0].get('PostOffice') if data and data[0].get('Status') == 'Success' else None
        if offices:
            offices = [office for office in offices if office.get('Name')]
            # The API orders offices alphabetically, not by postal importance.
            rank = {'Head Post Office': 0, 'Sub Post Office': 1, 'Branch Post Office': 2}
            primary = min(offices, key=lambda office: rank.get(office.get('BranchType'), 3))
            result = {'success': True, 'area': primary['Name'].strip(),
                      'district': primary.get('District', '').strip(),
                      'state': primary.get('State', '').strip(),
                      'areas': sorted({office['Name'].strip() for office in offices}),
                      'city': '', 'source': 'postal'}
            geo = geoapify_lookup(pin, result['area'], result['state'])
            if geo:
                # Preserve specific post-office areas, enriching only the city and administrative fields.
                result.update(city=geo['city'], source='postal+geoapify')
                result['state'] = geo['state']
            cache.set(key, result, 86400 if geo or not getattr(settings, 'GEOAPIFY_API_KEY', '') else 300)
            return JsonResponse(result)
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        pass
    geo = geoapify_lookup(pin)
    if geo:
        cache.set(key, geo, 86400)
        return JsonResponse(geo)
    # Keep the picker usable when the postal service is temporarily unavailable.
    local = PinCode.objects.select_related('district__state').filter(code=pin).first()
    if local:
        return JsonResponse({'success': True, 'area': local.area_name.strip() or local.district.name,
                             'district': local.district.name, 'state': local.district.state.name,
                             'areas': [], 'city': '', 'source': 'local'})
    return JsonResponse({'success': False, 'error': 'Area lookup unavailable. Please try again.'})
