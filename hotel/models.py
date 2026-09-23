from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator


class Room(models.Model):
    ROOM_TYPES = [

    ('Single Room', 'Single Room'),

    ('Deluxe Room', 'Deluxe Room'),

    ('Luxury Room', 'Luxury Room'),

    ('Executive Room', 'Executive Room'),

    ('Family Suite', 'Family Suite'),

    ('Presidential Suite', 'Presidential Suite'),

]

    room_number = models.CharField(max_length=10, unique=True)
    room_type = models.CharField(max_length=20, choices=ROOM_TYPES)
    price = models.DecimalField(max_digits=8, decimal_places=0)
    description = models.TextField()
    image = models.ImageField(upload_to='rooms/')
    available = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.room_number} - {self.room_type}"


class Wishlist(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    room = models.ForeignKey(Room, on_delete=models.CASCADE)
    added_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'room')

    def __str__(self):
         return f"{self.user.username} - Room {self.room.room_number}"

class Booking(models.Model):
    STATUS = [
        ('Pending', 'Pending'),
        ('Confirmed', 'Confirmed'),
        ('Completed', 'Completed'),
        ('Cancelled', 'Cancelled'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    room = models.ForeignKey(Room, on_delete=models.CASCADE)

    check_in = models.DateField()
    check_out = models.DateField()

    guests = models.PositiveIntegerField(default=1)

    total_price = models.DecimalField(
        max_digits=10,
        decimal_places=0
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS,
        default='Pending'
    )

    booking_date = models.DateTimeField(auto_now_add=True)

    qr_code = models.ImageField(
        upload_to="qr_codes/",
        blank=True,
        null=True
    )

    def __str__(self):
        return f"{self.user.username} - {self.room.room_number}"

class Review(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='reviews')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    booking = models.OneToOneField(
        Booking,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )

    rating = models.IntegerField(
        validators=[
            MinValueValidator(1),
            MaxValueValidator(5)
        ]
    )

    comment = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} - {self.room.room_type} ({self.rating}★)"

class Payment(models.Model):

    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Paid', 'Paid'),
        ('Failed', 'Failed'),
        ('Cancelled', 'Cancelled'),
        ('Refunded', 'Refunded'),
    ]

    booking = models.OneToOneField(
        Booking,
        on_delete=models.CASCADE,
        related_name='payment'
    )

    razorpay_order_id = models.CharField(
        max_length=120,
        unique=True,
        blank=True,
        null=True
    )

    razorpay_payment_id = models.CharField(
        max_length=120,
        blank=True,
        null=True
    )

    razorpay_signature = models.CharField(
        max_length=255,
        blank=True,
        null=True
    )

    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    payment_method = models.CharField(
        max_length=50,
        blank=True
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='Pending'
    )

    paid_at = models.DateTimeField(
        blank=True,
        null=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return f"Payment #{self.booking.id} - {self.status}"
    
class Contact(models.Model):
    name = models.CharField(max_length=100)

    email = models.EmailField()

    message = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


# =========================================================
# HOTEL SETTINGS
# =========================================================

class HotelSettings(models.Model):

    hotel_name = models.CharField(
        max_length=150,
        default="Luxury Grand Hotel"
    )

    hotel_email = models.EmailField(
        blank=True
    )

    hotel_phone = models.CharField(
        max_length=30,
        blank=True
    )

    hotel_address = models.TextField(
        blank=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):
        return self.hotel_name


# =========================================================
# NOTIFICATION SETTINGS
# =========================================================

class NotificationSettings(models.Model):

    booking_notifications = models.BooleanField(
        default=True
    )

    payment_notifications = models.BooleanField(
        default=True
    )

    cancellation_notifications = models.BooleanField(
        default=True
    )

    email_notifications = models.BooleanField(
        default=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):
        return "Notification Settings"