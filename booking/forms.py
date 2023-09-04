from django import forms
from .models import Booking


class BookingTokenForm(forms.ModelForm):
    token_used = forms.IntegerField(
        required=True,
        widget=forms.TextInput(attrs={'min': 1,
                                      'type': 'number'}
                               )
    )

    class Meta:
        model = Booking
        fields = ['token_used']

