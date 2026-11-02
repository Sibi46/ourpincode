from datetime import date

from django.test import SimpleTestCase

from .account import DashboardSeekerForm
from .models import JobSeekerProfile


class DashboardDateOfBirthTests(SimpleTestCase):
    def test_saved_date_renders_in_browser_date_format(self):
        form = DashboardSeekerForm(instance=JobSeekerProfile(dob=date(1996, 12, 31)))
        field = str(form['dob'])
        self.assertIn('type="date"', field)
        self.assertIn('value="1996-12-31"', field)

    def test_native_and_day_first_dates_are_accepted(self):
        field = DashboardSeekerForm().fields['dob']
        for value in ('1996-12-31', '31/12/1996', '31-12-1996'):
            with self.subTest(value=value):
                self.assertEqual(field.clean(value), date(1996, 12, 31))
        self.assertIsNone(field.clean(''))

    def test_invalid_calendar_date_is_rejected(self):
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            DashboardSeekerForm().fields['dob'].clean('31/02/1996')
