"""Monthly selection shared by the admin page and the scheduled command."""
import secrets
from datetime import datetime, time, timedelta

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import Coupon, MonthlyDraw


def eligible_entries(draw):
    next_month = (draw.month + timedelta(days=32)).replace(day=1)
    start = timezone.make_aware(datetime.combine(draw.month, time.min))
    end = timezone.make_aware(datetime.combine(next_month, time.min))
    return draw.entries.filter(
        coupon__status=Coupon.STATUS_USED,
        coupon__activated_by_id=F('customer_id'),
        coupon__activated_at__gte=start,
        coupon__activated_at__lt=end,
    )


@transaction.atomic
def select_winner(draw_id):
    draw = MonthlyDraw.objects.select_for_update().get(pk=draw_id)
    if draw.winner_id:
        return draw  # Retrying never redraws a winner.
    if draw.month >= timezone.localdate().replace(day=1):
        raise ValueError('The month must finish before selecting its winner.')
    if not draw.prize.strip():
        raise ValueError('Configure the prize before selecting a winner.')
    entries = eligible_entries(draw).order_by('pk')
    count = entries.count()
    if not count:
        raise ValueError('There are no eligible entries for this month.')
    draw.winner = entries[secrets.randbelow(count)]
    draw.selected_at = timezone.now()
    draw.save(update_fields=['winner', 'selected_at'])
    return draw
