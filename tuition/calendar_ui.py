"""Read-only calendar presentation; callers supply only authorized sessions."""
import calendar
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
from django.utils import timezone

ZONE = ZoneInfo('Asia/Kolkata')


def month_start(value):
    try:
        result = datetime.strptime(value, '%Y-%m').date().replace(day=1)
        if not 1901 <= result.year <= 2099:
            raise ValueError
        return result
    except (ValueError, TypeError):
        return timezone.localdate(timezone=ZONE).replace(day=1)


def bounds(first):
    return datetime.combine(first, time.min, ZONE), datetime.combine(first + timedelta(days=calendar.monthrange(first.year, first.month)[1]), time.min, ZONE)


def merge(intervals):
    result = []
    for start, end in sorted(intervals):
        if result and start <= result[-1][1]:
            result[-1] = (result[-1][0], max(result[-1][1], end))
        else:
            result.append((start, end))
    return result


def build_month(first, sessions, hours):
    days = []
    today = timezone.localdate(timezone=ZONE)
    for number in range(1, calendar.monthrange(first.year, first.month)[1]+1):
        day = date(first.year, first.month, number)
        start = datetime.combine(day, time.min, ZONE); end = start + timedelta(days=1)
        events, busy = [], []
        for session in sessions:
            if session.start < end and session.end > start:
                a, b = max(start, session.start), min(end, session.end)
                events.append({'session': session, 'time': f'{a.astimezone(ZONE):%H:%M}–{b.astimezone(ZONE):%H:%M}'})
                if session.status == 'scheduled':
                    busy.append((a, b))
        available = merge([(datetime.combine(day, h.start, ZONE), datetime.combine(day, h.end, ZONE)) for h in hours if h.weekday == day.weekday()])
        for a, b in merge(busy):
            pieces = []
            for x, y in available:
                if b <= x or a >= y:
                    pieces.append((x, y))
                else:
                    if x < a: pieces.append((x, a))
                    if b < y: pieces.append((b, y))
            available = pieces
        days.append({'date': day, 'events': events, 'busy': bool(busy), 'today': day == today,
                     'free': [f'{a:%H:%M}–{b:%H:%M}' for a, b in available]})
    cells = [None]*first.weekday() + days
    cells += [None]*((-len(cells))%7)
    return {'weekdays': ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'], 'days': days, 'weeks': [cells[i:i+7] for i in range(0,len(cells),7)],
            'busy_days': sum(d['busy'] for d in days), 'unbooked_days': sum(not d['busy'] for d in days),
            'free_days': sum(bool(d['free']) for d in days), 'month': first,
            'previous_month': (first-timedelta(days=1)).strftime('%Y-%m'),
            'next_month': (first+timedelta(days=len(days))).strftime('%Y-%m')}
