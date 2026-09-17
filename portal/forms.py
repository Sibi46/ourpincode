from django import forms


class BadgeArtworkForm(forms.Form):
    icon_image = forms.ImageField(required=False)
    image = forms.ImageField(required=False)

    def clean(self):
        data = super().clean()
        for field in ('icon_image', 'image'):
            upload = data.get(field)
            if upload and upload.size > 2 * 1024 * 1024:
                self.add_error(field, 'Use an image smaller than 2 MB.')
        return data
