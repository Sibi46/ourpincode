"""Resolve postal towns without treating the first branch office as the town."""
import json
import re
import urllib.request

from django.core.cache import cache
from django.http import JsonResponse

from .models import PinCode


def pincode_lookup(request, pin):
    if not re.fullmatch(r'[1-9][0-9]{5}', pin):
        return JsonResponse({'success': False, 'error': 'Invalid PIN code'})
    key = 'postal-areas-v2:' + pin
    result = cache.get(key)
    if result:
        return JsonResponse(result)
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
                      'areas': sorted({office['Name'].strip() for office in offices})}
            cache.set(key, result, 86400)
            return JsonResponse(result)
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        pass
    # Keep the picker usable when the postal service is temporarily unavailable.
    local = PinCode.objects.select_related('district__state').filter(code=pin).first()
    if local:
        return JsonResponse({'success': True, 'area': local.area_name.strip() or local.district.name,
                             'district': local.district.name, 'state': local.district.state.name,
                             'areas': [], 'source': 'local'})
    return JsonResponse({'success': False, 'error': 'Area lookup unavailable. Please try again.'})
