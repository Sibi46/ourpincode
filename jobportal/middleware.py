from django.shortcuts import redirect

# Pages anyone can visit without logging in
PUBLIC_PREFIXES = [
    '/language/',
    '/admin-workspace/login/',
    '/news/',                     # News Desk views enforce write/agent permissions
    '/businesses/',
    '/business/',
    '/login/',
    '/logout/',
    '/register/',
    '/forgot-password/',
    '/reset-password/',
    '/api/send-otp/',
    '/api/verify-otp/',
    '/api/quick-register/',
    '/api/phone-login/',
    '/api/check-phone/',
    '/api/pincode/',
    '/api/reset-password/',
    '/quiz/play/',                # quiz landing page; answer APIs require login
    '/quiz/pincodeday/',          # public event pages; participation views require login
    '/flicks/',                   # browse flicks
    '/health/',                   # browse health
    '/vouchers/marketplace/',     # browse vouchers
    '/vouchers/v/',               # voucher card share link
    '/jobs/',                     # browse jobs
    '/advertise/',
    '/offers/post/success/',
    '/community/',                # community hub (read-only browsing)
    '/community/school-corner/',  # school pages
    '/community/school-kids/',
    '/community/local-heroes/',
    '/community/events/',
    '/community/business-stories/',
    '/community/community-watch/',
    '/community/volunteer/',
    '/community/family/',
    '/community/student-success/',
    '/community/kids-corner/',
    '/community/parenting/',
    '/community/grandparents-archive/',
    '/static/',
    '/media/',
    '/ads/',
    '/admin/',
    '/campus/',       # campus public pages
    '/coupons/salesman/login/',
    '/coupons/salesman/logout/',
    '/api/send-register-otp/',
    '/api/verify-register-otp/',
]


class LoginRequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.user.is_authenticated:
            path = request.path
            if path.startswith('/tuition/'):
                from django.urls import resolve, Resolver404
                try:
                    match = resolve(path)
                    if match.namespace == 'tuition' and match.url_name in {'discover', 'profile', 'apply', 'received', 'file', 'showcase', 'event', 'programme', 'result', 'achievement', 'asset', 'activity_file'}:
                        return self.get_response(request)
                except Resolver404:
                    pass

            # Offer merchant detail pages are public; posting and management remain protected.
            import re
            if re.fullmatch(r'/offers/[0-9]+/store/', path):
                return self.get_response(request)

            # Allow exact home
            if path in {'/', '/favicon.ico', '/robots.txt', '/sitemap.xml', '/api/nearby-jobs/', '/area/select/'} or path.startswith('/sitemaps/'):
                return self.get_response(request)

            # Allow all public prefixes
            for prefix in PUBLIC_PREFIXES:
                if path.startswith(prefix):
                    return self.get_response(request)

            # Everything else — redirect to login
            return redirect(f'/login/?next={path}')

        return self.get_response(request)
