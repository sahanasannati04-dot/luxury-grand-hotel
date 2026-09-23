from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from .models import Booking, Review, Contact, Room


class RegisterForm(UserCreationForm):

    email = forms.EmailField()

    class Meta:
        model = User

        fields = [
            'first_name',
            'last_name',
            'username',
            'email',
            'password1',
            'password2'
        ]
        
class BookingForm(forms.ModelForm):
    class Meta:
        model = Booking
        fields = ['check_in', 'check_out', 'guests']

        widgets = {
            'check_in': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'check_out': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'guests': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
        }
        

class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ['rating', 'comment']

        widgets = {
            'rating': forms.Select(
                choices=[
                    (1, '⭐ 1 - Poor'),
                    (2, '⭐⭐ 2 - Fair'),
                    (3, '⭐⭐⭐ 3 - Good'),
                    (4, '⭐⭐⭐⭐ 4 - Very Good'),
                    (5, '⭐⭐⭐⭐⭐ 5 - Excellent'),
                ],
                attrs={
                    'class': 'form-select'
                }
            ),

            'comment': forms.Textarea(
                attrs={
                    'class': 'form-control',
                    'rows': 5,
                    'placeholder': 'Share your experience...'
                }
            ),
        }
        
class ContactForm(forms.ModelForm):
    class Meta:
        model = Contact
        fields = ['name', 'email', 'message']

        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Your Name'
            }),

            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'Email Address'
            }),

            'message': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 5,
                'placeholder': 'Your Message'
            }),
        }
        
class RoomForm(forms.ModelForm):

    class Meta:
        model = Room

        fields = "__all__"

        widgets = {

            "room_number": forms.TextInput(
                attrs={
                    "class": "premium-form-control",
                    "placeholder": "e.g. 101"
                }
            ),

            "room_type": forms.Select(
                attrs={
                    "class": "premium-form-control"
                }
            ),

            "price": forms.NumberInput(
                attrs={
                    "class": "premium-form-control",
                    "placeholder": "Enter price per night",
                    "min": "0",
                    "step": "1"
                }
            ),

            "description": forms.Textarea(
                attrs={
                    "class": "premium-form-control",
                    "placeholder": "Describe the room, view, facilities and experience...",
                    "rows": 5
                }
            ),

            "image": forms.ClearableFileInput(
                attrs={
                    "class": "premium-form-control"
                }
            ),

            "available": forms.CheckboxInput(
                attrs={
                    "class": "premium-checkbox"
                }
            ),
        }