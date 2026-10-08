from datetime import date, datetime, time, timedelta
from types import SimpleNamespace
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone
from . import models as m, tests as fixtures, forms
from .calendar_ui import build_month, month_start, ZONE


class CalendarCalculationTests(SimpleTestCase):
    def test_busy_cancelled_and_free_intervals(self):
        session = SimpleNamespace(start=datetime(2026,10,5,10,tzinfo=ZONE), end=datetime(2026,10,5,11,tzinfo=ZONE), status='scheduled')
        cancelled = SimpleNamespace(start=datetime(2026,10,5,12,tzinfo=ZONE), end=datetime(2026,10,5,13,tzinfo=ZONE), status='cancelled')
        hours = [SimpleNamespace(weekday=0, start=time(9), end=time(14)), SimpleNamespace(weekday=0, start=time(13), end=time(15))]
        result = build_month(date(2026,10,1), [session,cancelled], hours)
        self.assertEqual(result['busy_days'], 1)
        self.assertEqual(result['unbooked_days'], 30)
        self.assertEqual(result['days'][4]['free'], ['09:00–10:00','11:00–15:00'])
        self.assertEqual(len(result['weeks'][0]), 7)

    def test_cross_midnight_and_invalid_month(self):
        event = SimpleNamespace(start=datetime(2026,10,5,23,tzinfo=ZONE),end=datetime(2026,10,6,1,tzinfo=ZONE),status='scheduled')
        self.assertEqual(build_month(date(2026,10,1),[event],[])['busy_days'],2)
        self.assertEqual(month_start('bad'), timezone.localdate(timezone=ZONE).replace(day=1))


class CalendarWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixtures.TuitionTests.setUpTestData.__func__(cls)

    def test_calendar_owner_access_and_student_isolation(self):
        day = timezone.localdate()+timedelta(days=2)
        session = m.ClassSession.objects.create(batch=self.batch,start=datetime.combine(day,time(10),ZONE),end=datetime.combine(day,time(11),ZONE),mode='offline')
        url = reverse('tuition:timetable')+'?month='+day.strftime('%Y-%m')
        self.client.force_login(self.owner)
        response = self.client.get(url)
        self.assertTemplateUsed(response,'tuition/calendar.html')
        self.assertContains(response,reverse('tuition:session',args=[session.uid]))
        self.assertEqual(response.context['calendar']['busy_days'],1)
        self.client.force_login(self.other)
        response = self.client.get(url)
        self.assertNotContains(response,reverse('tuition:session',args=[session.uid]))
        self.assertEqual(response.context['calendar']['busy_days'],0)

    def test_group_timetable_shows_days_and_multiple_start_times_privately(self):
        today = timezone.localdate()
        for hour in (10, 12):
            m.ScheduleRule.objects.create(batch=self.batch, weekday=0, start_time=time(hour), start_date=today, end_date=today+timedelta(days=30))
        m.ScheduleRule.objects.create(batch=self.batch, weekday=1, start_time=time(18), start_date=today, end_date=today+timedelta(days=30), active=False)
        self.client.force_login(self.owner)
        response = self.client.get(reverse('tuition:timetable'))
        self.assertTemplateUsed(response, 'tuition/group_timetable.html')
        self.assertContains(response, self.batch.name)
        self.assertContains(response, 'Monday')
        self.assertContains(response, '10:00 AM')
        self.assertContains(response, '12:00 PM')
        self.assertNotContains(response, '6:00 PM')
        self.client.force_login(self.other)
        response = self.client.get(reverse('tuition:timetable'))
        self.assertEqual(list(response.context['groups']), [])

    def test_weekday_times_saved_and_invalid_slot_rejected(self):
        from .test_groups import GroupWorkflowTests
        fixture = GroupWorkflowTests()
        fixture.owner=self.owner; fixture.teacher=self.teacher; fixture.client=self.client
        fixture.setUp()
        day=fixture.date.weekday()
        data={**fixture.data, f'day_start_{day}':['10:00', '12:00'], 'fee':''}
        response=self.client.post(fixture.url,data)
        self.assertEqual(response.status_code,302)
        batch=m.Batch.objects.get(name='Evening group')
        self.assertEqual(batch.lesson.fee,0)
        self.assertEqual(batch.rules.count(),2)
        rule=batch.rules.get(start_time=time(10))
        self.assertEqual(rule.start_time,time(10))
        self.assertEqual(rule.duration_minutes,60)
        self.assertEqual(rule.start_date.weekday(),day)
        data[f'day_start_{day}']=['10:00','10:00']
        form=forms.GroupCreateForm(data,instance=m.Lesson(teacher=self.teacher))
        self.assertFalse(form.is_valid())
        self.assertIn(f'day_start_{day}',form.errors)

    def test_missing_selected_times_rejected(self):
        form=forms.GroupCreateForm({'weekdays':['0']})
        self.assertFalse(form.is_valid())
        self.assertIn('day_start_0',form.errors)

    def test_removed_controls_and_online_fields(self):
        self.client.force_login(self.owner)
        response=self.client.get(reverse('tuition:group_create',args=[self.teacher.uid]))
        for name in ('start_date','end_date','start_time','min_age','max_age','subjects','day_date_0'):
            self.assertNotContains(response,'name="'+name+'"')
        self.assertContains(response,'name="day_start_0"')
        self.assertNotContains(response,'name="day_end_0"')
        self.assertContains(response,'class="add-slot"')
        self.assertContains(response,'data-field="meeting_url"')

    def test_export_calendar_and_group_preview(self):
        import os
        if os.environ.get('TUITION_AUDIT_UI')!='1': self.skipTest('Optional browser export')
        from pathlib import Path
        self.client.force_login(self.owner)
        root=Path('.audit-tools/ui');root.mkdir(parents=True,exist_ok=True)
        for name,url in [('calendar',reverse('tuition:timetable')),('group-form',reverse('tuition:group_create',args=[self.teacher.uid]))]:
            response=self.client.get(url)
            self.assertEqual(response.status_code,200)
            (root/(name+'.html')).write_bytes(response.content)
