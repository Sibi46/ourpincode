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

    def test_selected_date_used_and_wrong_weekday_rejected(self):
        from .test_groups import GroupWorkflowTests
        fixture = GroupWorkflowTests()
        fixture.owner=self.owner; fixture.teacher=self.teacher; fixture.client=self.client
        fixture.setUp()
        chosen=fixture.date+timedelta(days=7)
        data={**fixture.data,'end_date':chosen+timedelta(days=6),f'day_date_{chosen.weekday()}':chosen}
        response=self.client.post(fixture.url,data)
        self.assertEqual(response.status_code,302)
        batch=m.Batch.objects.get(name='Evening group')
        self.assertEqual(batch.rules.get().start_date,chosen)
        self.assertEqual(timezone.localtime(batch.sessions.first().start,ZONE).date(),chosen)
        data[f'day_date_{chosen.weekday()}']=chosen+timedelta(days=1)
        form=forms.GroupCreateForm(data,instance=m.Lesson(teacher=self.teacher))
        self.assertFalse(form.is_valid())
        self.assertIn(f'day_date_{chosen.weekday()}',form.errors)

    def test_missing_selected_date_is_rejected(self):
        form=forms.GroupCreateForm({'weekdays':['0']})
        self.assertFalse(form.is_valid())
        self.assertIn('day_date_0',form.errors)

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
