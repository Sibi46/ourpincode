from django.shortcuts import redirect

# Pages anyone can visit without logging in
PUBLIC_PREFIXES = [
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
    '/api/reset-password/',
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

            # Allow exact home
            if path == '/':
                return self.get_response(request)

            # Allow all public prefixes
            for prefix in PUBLIC_PREFIXES:
                if path.startswith(prefix):
                    return self.get_response(request)

            # Everything else — redirect to login
            return redirect(f'/login/?next={path}')

        return self.get_response(request)
