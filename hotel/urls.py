from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('rooms/', views.rooms, name='rooms'),
    path('register/', views.register, name='register'),
    path('login/', views.user_login, name='login'),
    path('logout/', views.user_logout, name='logout'),
    path('book/<int:room_id>/', views.book_room, name='book_room'),

    path(
        'payment/<int:booking_id>/',
         views.payment_page,
         name='payment_page'
    ),
    
    path
       (
       'test-payment-success/<int:booking_id>/',
        views.test_payment_success,
        name='test_payment_success'
    ),

    path('booking-history/', views.booking_history, name='booking_history'),

    path(
        'cancel-booking/<int:booking_id>/',
         views.cancel_booking,
         name='cancel_booking'
    ),

    path
       (
       'delete-booking/<int:booking_id>/',
       views.delete_booking,
       name='delete_booking'
    ),

    # Part 9 Pages
    path('about/', views.about, name='about'),
    path('gallery/', views.gallery, name='gallery'),
    path('contact/', views.contact, name='contact'),
    
    path(
        'wishlist/',
         views.wishlist,
         name='wishlist'
    ),

    path(
        'wishlist/add/<int:room_id>/',
         views.add_to_wishlist,
         name='add_to_wishlist'
    ),

    path(
        'wishlist/remove/<int:room_id>/',
         views.remove_from_wishlist,
         name='remove_from_wishlist'
    ),

    path(
        'booking/<int:booking_id>/',
         views.booking_details,
         name='booking_details'
    ),

    path(
        'booking/<int:booking_id>/invoice/',
         views.download_invoice,
         name='download_invoice'
    ),

    path(
        'booking/<int:booking_id>/download/',
         views.download_receipt,
         name='download_receipt'
    ),

    path(
        'booking/<int:booking_id>/modify/',
         views.modify_booking,
         name='modify_booking'
    ),

    path(
        'payment/success/',
         views.payment_success,
         name='payment_success'
    ),

    path(
        'review/<int:booking_id>/',
         views.add_review,
         name='add_review'
    ),
    
    path(
        'admin-dashboard/',
         views.admin_dashboard,
         name='admin_dashboard'
    ),
    
    path
       (
       'admin-dashboard/users/',
        views.admin_users,
        name='admin_users'
    ),
   
    path
       (
       'admin-dashboard/bookings/',
        views.admin_bookings,
        name='admin_bookings'
    ),

    path
       (
       'admin-dashboard/bookings/<int:booking_id>/',
        views.admin_booking_details,
        name='admin_booking_details'
    ),

    path(
        'admin-dashboard/bookings/<int:booking_id>/<str:action>/',
         views.admin_booking_status,
        name='admin_booking_status'
    ),

    path
       (
       'admin-dashboard/reports/',
        views.admin_reports,
        name='admin_reports'
    ),
    
    # =========================================================
    # ADMIN ROOM MANAGEMENT
    # =========================================================

    path 
        (
        'admin-dashboard/rooms/',
         views.admin_rooms,
         name='admin_rooms'
        ),

    path
       (
       'admin-dashboard/rooms/add/',
        views.admin_room_add,
        name='admin_room_add'
    ),

    path
       (
       'admin-dashboard/rooms/<int:room_id>/edit/',
        views.admin_room_edit,
        name='admin_room_edit'
    ),

    path
       (
       'admin-dashboard/rooms/<int:room_id>/delete/',
        views.admin_room_delete,
        name='admin_room_delete'
    ),
    
    path
       (
       'admin-dashboard/hotel-settings/',
        views.hotel_settings,
        name='hotel_settings'
    ),

    path
       (
       'admin-dashboard/notification-settings/',
        views.notification_settings,
        name='notification_settings'
    ),

    path
       (
       'admin-dashboard/security-settings/',
        views.security_settings,
        name='security_settings'
    ),

    path
      (
      'admin-dashboard/profile/',
       views.admin_profile,
       name='admin_profile'
    ),

]