import re
from datetime import date
from django import forms


class FourDigitYearDateField(forms.DateField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('input_formats', ['%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'])
        super().__init__(*args, **kwargs)
        self.widget.attrs.update({'max': '9999-12-31', 'data-four-digit-year': ''})

    def to_python(self, value):
        if value and not isinstance(value, date) and not re.fullmatch(r'(?:[0-9]{4}-[0-9]{2}-[0-9]{2}|[0-9]{2}[/-][0-9]{2}[/-][0-9]{4})', str(value)):
            raise forms.ValidationError('Enter a valid date with a four-digit year.', code='invalid')
        return super().to_python(value)
