from django.contrib import admin
from .models import Room, Booking, Wishlist, Payment, Review, Contact


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = (
        'room_number',
        'room_type',
        'price',
        'available',
    )

@admin.register(Wishlist)
class WishlistAdmin(admin.ModelAdmin):
    list_display = (
        'user',
        'room',
        'added_on',
    )


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = (
        'user',
        'room',
        'check_in',
        'check_out',
        'status',
    )


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):

    list_display = (
        'booking',
        'amount',
        'payment_method',
        'status',
        'razorpay_order_id',
        'razorpay_payment_id',
        'paid_at',
        'created_at',
    )

    list_filter = (
        'status',
        'payment_method',
        'created_at',
    )

    search_fields = (
        'booking__user__username',
        'razorpay_order_id',
        'razorpay_payment_id',
    )

    readonly_fields = (
        'razorpay_order_id',
        'razorpay_payment_id',
        'razorpay_signature',
        'created_at',
        'paid_at',
    )


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = (
        'user',
        'room',
        'rating',
        'created_at'
    )

    list_filter = (
        'rating',
        'created_at'
    )

    search_fields = (
        'user__username',
        'room__room_number',
        'comment'
    )
    
@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'email',
        'created_at'
    )

    search_fields = (
        'name',
        'email'
    )

    list_filter = (
        'created_at',
    )