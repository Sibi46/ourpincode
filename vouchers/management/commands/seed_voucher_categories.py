from django.core.management.base import BaseCommand
from vouchers.models import BusinessCategory, VoucherCategory


BUSINESS_CATEGORIES = [
    ('Restaurant & Food',     '🍽️'),
    ('Beauty & Spa',          '💆'),
    ('Fitness & Wellness',    '💪'),
    ('Shopping & Retail',     '🛍️'),
    ('Entertainment',         '🎭'),
    ('Travel & Hotels',       '✈️'),
    ('Healthcare',            '🏥'),
    ('Education',             '📚'),
    ('Bakery & Sweets',       '🎂'),
    ('Clothing & Fashion',    '👗'),
    ('Electronics',           '📱'),
    ('Home & Decor',          '🏠'),
    ('Supermarket & Grocery', '🛒'),
    ('Automotive',            '🚗'),
    ('Photography & Media',   '📷'),
]

VOUCHER_CATEGORIES = [
    ('Dining',            '🍽️', 1),
    ('Shopping',          '🛍️', 2),
    ('Beauty & Wellness', '💆', 3),
    ('Entertainment',     '🎭', 4),
    ('Travel',            '✈️', 5),
    ('Fitness',           '💪', 6),
    ('Electronics',       '📱', 7),
    ('Education',         '📚', 8),
    ('Healthcare',        '🏥', 9),
    ('Grocery',           '🛒', 10),
    ('Bakery & Cafe',     '☕', 11),
    ('Fashion',           '👗', 12),
    ('Home & Living',     '🏠', 13),
    ('Experiences',       '🎁', 14),
    ('Other',             '⭐', 15),
]


class Command(BaseCommand):
    help = 'Seed default business and voucher categories'

    def handle(self, *args, **options):
        self.stdout.write('--- Business Categories ---')
        for name, icon in BUSINESS_CATEGORIES:
            obj, created = BusinessCategory.objects.get_or_create(
                name=name, defaults={'icon': icon, 'is_active': True}
            )
            self.stdout.write(f"  {'Created' if created else 'OK'}: {name}")
        self.stdout.write(self.style.SUCCESS(
            f"  {BusinessCategory.objects.filter(is_active=True).count()} active business categories."
        ))

        self.stdout.write('--- Voucher Categories ---')
        for name, icon, order in VOUCHER_CATEGORIES:
            obj, created = VoucherCategory.objects.get_or_create(
                name=name, defaults={'icon': icon, 'is_active': True, 'order': order}
            )
            self.stdout.write(f"  {'Created' if created else 'OK'}: {name}")
        self.stdout.write(self.style.SUCCESS(
            f"  {VoucherCategory.objects.filter(is_active=True).count()} active voucher categories."
        ))
