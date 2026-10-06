from django.core.management.base import BaseCommand
from django.utils import timezone

from coupons.lucky_draw import select_winner
from coupons.models import MonthlyDraw


class Command(BaseCommand):
    help = 'Select winners for completed months. Safe to schedule daily or retry.'

    def handle(self, *args, **options):
        draws = MonthlyDraw.objects.filter(month__lt=timezone.localdate().replace(day=1), winner__isnull=True)
        for draw in draws:
            try:
                selected = select_winner(draw.pk)
            except ValueError as exc:
                self.stdout.write(f'{draw}: skipped: {exc}')
            else:
                self.stdout.write(f'{draw}: winning entry {selected.winner_id}')
