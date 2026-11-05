import unicodedata

from django import forms

from .person_names import valid_person_name

BLUE_TYPES = [('labour', 'General Labour'), ('construction', 'Construction / Mason / Carpenter'), ('factory', 'Factory / Production'), ('domestic', 'Domestic Worker / Cook'), ('agriculture', 'Agriculture / Farming'), ('welder', 'Welder / Fabricator'), ('helper', 'Helper'), ('sweeper', 'Sweeper / Cleaning'), ('tailor', 'Tailor'), ('other_blue', 'Other Blue Collar'), ('electrician', 'Electrician'), ('plumber', 'Plumber'),
              ('driver', 'Driver / Delivery'), ('mechanic', 'Mechanic'), ('carpenter', 'Carpenter'),
              ('painter', 'Painter'), ('security', 'Security'), ('housekeeping', 'Housekeeping'), ('other', 'Other')]
WHITE_TYPES = [('manager', 'Manager'), ('teacher', 'Teacher'), ('engineer', 'Engineer'),
               ('accountant', 'Accountant'), ('it', 'IT / Software'), ('admin', 'Administration'),
               ('sales', 'Sales / Marketing'), ('hr', 'Human Resources'), ('other', 'Other')]


class ProfileValidationMixin:
    person_fields = ()
    text_fields = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in self.person_fields:
            self.fields[name].widget.attrs.update({'pattern': r'[\p{L}\p{M} ]+', 'data-profile-name': '',
                                                   'title': 'Use letters and spaces only.'})
        for name in self.text_fields:
            self.fields[name].widget.attrs['data-profile-text'] = ''
        if 'whatsapp' in self.fields:
            self.fields['whatsapp'].widget.attrs.update({'type': 'tel', 'inputmode': 'numeric',
                'pattern': '[0-9]{10}', 'maxlength': '10', 'title': 'Enter a 10-digit WhatsApp number.'})

    def clean(self):
        data = super().clean()
        for name in self.person_fields:
            value = data.get(name)
            if value and not valid_person_name(value):
                self.add_error(name, 'Use letters and spaces only.')
        for name in self.text_fields:
            value = data.get(name)
            if value and any(unicodedata.category(c).startswith('N') for c in value):
                self.add_error(name, 'Use text without numbers.')
        phone = data.get('whatsapp')
        if phone and (len(phone) != 10 or any(c not in '0123456789' for c in phone)):
            self.add_error('whatsapp', 'Enter a 10-digit WhatsApp number using numbers only.')
        return data
