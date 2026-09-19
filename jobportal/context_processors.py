from django.conf import settings


def site_branding(request):
    """Canonical links must not depend on an incoming Host header."""
    return {
        'SITE_NAME': settings.SITE_NAME,
        'SITE_URL': settings.SITE_URL,
        'SITE_TAGLINE': settings.SITE_TAGLINE,
    }
