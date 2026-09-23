from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required

from .forms import RegisterForm, BookingForm, ContactForm, RoomForm
from .models import Room, Booking, Wishlist, Review, Contact, Payment, HotelSettings, NotificationSettings

from django.core.mail import send_mail
from django.conf import settings

from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

import qrcode
import io
from django.utils import timezone


from django.core.files.base import ContentFile
from email.mime.image import MIMEImage
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.db.models.functions import TruncMonth

from .forms import ReviewForm
from django.db.models import Avg, Count, Sum, Q
from django.db import transaction

from django.http import HttpResponse
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader

import razorpay

razorpay_client = razorpay.Client(
    auth=(
        settings.RAZORPAY_KEY_ID,
        settings.RAZORPAY_KEY_SECRET
    )
)

# =========================================================
# NOTIFICATION CONTROL HELPER
# =========================================================

def notification_enabled(notification_type):

    notification = NotificationSettings.objects.first()

    if notification is None:
        notification = NotificationSettings.objects.create()

    # Master email switch
    if not notification.email_notifications:
        return False

    if notification_type == "booking":
        return notification.booking_notifications

    if notification_type == "payment":
        return notification.payment_notifications

    if notification_type == "cancellation":
        return notification.cancellation_notifications

    return False

def home(request):

    featured_rooms = Room.objects.filter(
        available=True
    )[:3]

    return render(
        request,
        'index.html',
        {
            'rooms': featured_rooms
        }
    )


def rooms(request):
    room_list = Room.objects.filter(available=True)

    search = request.GET.get('search')
    room_type = request.GET.get('room_type')
    guests = request.GET.get('guests')
    price_range = request.GET.get('price_range')

    if search:
        room_list = room_list.filter(room_type__icontains=search)

    if room_type:
        room_list = room_list.filter(room_type=room_type)

    if price_range == 'under_5000':
        room_list = room_list.filter(price__lte=5000)
    elif price_range == '5000_10000':
        room_list = room_list.filter(price__gte=5000, price__lte=10000)
    elif price_range == 'above_10000':
        room_list = room_list.filter(price__gt=10000)

    # Guests selection is available in the form but not currently stored on Room.
    # It can be used later if the model is extended with a guest capacity field.

    # Calculate average rating and review count
    room_list = room_list.annotate(
    average_rating=Avg('reviews__rating'),
    review_count=Count('reviews')
    ).prefetch_related('reviews__user')

    # Get wishlist room IDs for logged-in users
    wishlist_room_ids = []

    if request.user.is_authenticated:
        wishlist_room_ids = Wishlist.objects.filter(
            user=request.user
        ).values_list('room_id', flat=True)

    return render(request, 'rooms.html', {
        'rooms': room_list,
        'wishlist_room_ids': wishlist_room_ids,
    })


def register(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)

        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('home')
    else:
        form = RegisterForm()

    return render(request, 'register.html', {
        'form': form
    })


def user_login(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']

        user = authenticate(
            request,
            username=username,
            password=password
        )

        if user:
            login(request, user)
            return redirect('home')

    return render(request, 'login.html')


def user_logout(request):
    logout(request)
    return redirect('home')

# =========================================================
# BOOKING VALIDATION HELPER
# =========================================================

def room_has_booking_conflict(
    room,
    check_in,
    check_out,
    exclude_booking_id=None
):
    """
    Check whether the room already has a confirmed or
    completed booking overlapping the requested dates.

    Pending bookings do NOT permanently block the room
    because payment may fail or the user may abandon checkout.

    Cancelled bookings do not block the room.
    """

    bookings = Booking.objects.filter(
        room=room,
        status__in=["Confirmed", "Completed"],
        check_in__lt=check_out,
        check_out__gt=check_in
    )

    if exclude_booking_id:
        bookings = bookings.exclude(
            id=exclude_booking_id
        )

    return bookings.exists()


@login_required
def book_room(request, room_id):

    room = get_object_or_404(
        Room,
        id=room_id
    )

    # =====================================================
    # ROOM AVAILABILITY
    # =====================================================

    if not room.available:

        return render(
            request,
            "booking_failed.html",
            {
                "message": "This room is currently not available."
            }
        )

    # =====================================================
    # POST REQUEST
    # =====================================================

    if request.method == "POST":

        form = BookingForm(request.POST)

        print("BOOKING FORM DATA:", request.POST)
        print("BOOKING FORM ERRORS:", form.errors)

        if form.is_valid():
            
            print("BOOKING FORM IS VALID")

            booking = form.save(commit=False)

            booking.user = request.user
            booking.room = room

            # =================================================
            # DATE VALIDATION
            # =================================================

            today = timezone.localdate()

            check_in = booking.check_in
            check_out = booking.check_out

            # Check-in cannot be before today
            if check_in < today:

                form.add_error(
                    "check_in",
                    "Check-in date cannot be in the past."
                )

                return render(
                    request,
                    "book_room.html",
                    {
                        "form": form,
                        "room": room
                    }
                )

            # Check-out must be after check-in
            if check_out <= check_in:

                form.add_error(
                    "check_out",
                    "Check-out must be after check-in."
                )

                return render(
                    request,
                    "book_room.html",
                    {
                        "form": form,
                        "room": room
                    }
                )

            # =================================================
            # GUEST VALIDATION
            # =================================================

            if booking.guests < 1:

                form.add_error(
                    "guests",
                    "At least 1 guest is required."
                )

                return render(
                    request,
                    "book_room.html",
                    {
                        "form": form,
                        "room": room
                    }
                )

            # =================================================
            # PREVENT DOUBLE BOOKING
            # =================================================

            with transaction.atomic():

                # Lock this room while checking availability.
                locked_room = Room.objects.select_for_update().get(
                    id=room.id
                )

                # Check room is still available
                if not locked_room.available:

                    messages.error(
                        request,
                        "This room is no longer available."
                    )

                    return redirect(
                        "rooms"
                    )

                # Check overlapping active bookings
                conflict = room_has_booking_conflict(
                    locked_room,
                    check_in,
                    check_out
                )

                if conflict:

                    form.add_error(
                        None,
                        "This room is already booked for the selected dates. Please choose different dates."
                    )

                    return render(
                        request,
                        "book_room.html",
                        {
                            "form": form,
                            "room": locked_room
                        }
                    )

                # =================================================
                # CALCULATE TOTAL
                # =================================================

                days = (
                    check_out - check_in
                ).days

                booking.total_price = (
                    days * locked_room.price
                )

                # Booking remains Pending until payment succeeds
                booking.status = "Pending"

                booking.save()

                # =================================================
                # CREATE RAZORPAY ORDER
                # =================================================

                amount_in_paise = int(
                    booking.total_price * 100
                )

                try:

                    razorpay_order = (
                        razorpay_client.order.create(
                            {
                                "amount": amount_in_paise,
                                "currency": "INR",
                                "receipt": f"booking_{booking.id}",
                                "notes": {
                                    "booking_id": str(booking.id),
                                    "user_id": str(request.user.id),
                                }
                            }
                        )
                    )

                except Exception as e:

                    print("RAZORPAY ORDER ERROR:", repr(e))

                     # Remove booking if Razorpay order creation fails
                    booking.delete()

                    messages.error(
                       request,
                       f"Unable to initialize payment: {str(e)}"
                    )


                    return render(
                        request,
                        "book_room.html",
                        {
                            "form": form,
                            "room": locked_room
                        }
                    )

                # =================================================
                # CREATE PAYMENT RECORD
                # =================================================

                Payment.objects.create(

                    booking=booking,

                    razorpay_order_id=
                        razorpay_order["id"],

                    amount=
                        booking.total_price,

                    status="Pending"

                )

                # =================================================
                # GENERATE QR CODE
                # =================================================

                qr_data = f"""
Booking ID: {booking.id}
Customer: {request.user.username}
Room: {locked_room.room_type}
Room Number: {locked_room.room_number}
Check-in: {booking.check_in}
Check-out: {booking.check_out}
Guests: {booking.guests}
Total: ₹{booking.total_price}
"""

                qr = qrcode.make(
                    qr_data
                )

                buffer = io.BytesIO()

                qr.save(
                    buffer,
                    format="PNG"
                )

                filename = (
                    f"booking_{booking.id}.png"
                )

                booking.qr_code.save(
                    filename,
                    ContentFile(
                        buffer.getvalue()
                    ),
                    save=True
                )

                # =================================================
                # PAYMENT PAGE
                # =================================================

                return redirect(
                    "payment_page",
                    booking_id=booking.id
                )

    else:

        form = BookingForm()

    return render(
        request,
        "book_room.html",
        {
            "form": form,
            "room": room
        }
    )

# ==========================================
# RAZORPAY PAYMENT PAGE
# ==========================================

@login_required
def payment_page(request, booking_id):

    booking = get_object_or_404(
        Booking,
        id=booking_id,
        user=request.user
    )

    payment = get_object_or_404(
        Payment,
        booking=booking
    )

    # ------------------------------------------
    # Cancelled booking
    # ------------------------------------------

    if booking.status == "Cancelled":

        messages.error(
            request,
            "This booking has been cancelled."
        )

        return redirect(
            "booking_details",
            booking_id=booking.id
        )


    # ------------------------------------------
    # Already paid
    # ------------------------------------------

    if payment.status == "Paid":

        messages.info(
            request,
            "This booking has already been paid."
        )

        return redirect(
            "booking_details",
            booking_id=booking.id
        )


    # ------------------------------------------
    # Convert amount to paise
    # Example:
    # ₹7000 -> 700000 paise
    # ------------------------------------------

    amount_in_paise = int(
        payment.amount * 100
    )


    # ------------------------------------------
    # Make sure Razorpay order exists
    # and has the correct amount
    # ------------------------------------------

    try:

        existing_order = None

        if payment.razorpay_order_id:

            try:

                existing_order = (
                    razorpay_client.order.fetch(
                        payment.razorpay_order_id
                    )
                )

            except Exception:

                existing_order = None


        # Create a new Razorpay order when:
        #
        # 1. There is no order ID
        # OR
        # 2. Existing order has wrong amount
        #
        if (
            not existing_order
            or int(existing_order["amount"])
            != amount_in_paise
        ):

            razorpay_order = (
                razorpay_client.order.create({
                    "amount": amount_in_paise,
                    "currency": "INR",
                    "receipt": f"booking_{booking.id}",
                    "notes": {
                        "booking_id": str(booking.id),
                        "payment_id": str(payment.id),
                    }
                })
            )

            payment.razorpay_order_id = (
                razorpay_order["id"]
            )

            payment.save(
                update_fields=[
                    "razorpay_order_id"
                ]
            )

        else:

            razorpay_order = existing_order


    except Exception as e:

        messages.error(
            request,
            "Unable to initialize secure payment. Please try again."
        )

        return redirect(
            "booking_details",
            booking_id=booking.id
        )


    # ------------------------------------------
    # Render payment page
    # ------------------------------------------

    return render(
        request,
        "payment.html",
        {
            "booking": booking,
            "payment": payment,

            "razorpay_key_id":
                settings.RAZORPAY_KEY_ID,

            "razorpay_order_id":
                payment.razorpay_order_id,

            "amount":
                amount_in_paise,

            "debug":
                settings.DEBUG,
       }
    )

# ==========================================
# RAZORPAY PAYMENT VERIFICATION
# ==========================================

@login_required
def payment_success(request):

    if request.method != "POST":

        return redirect(
            "booking_history"
        )


    # ==========================================
    # GET RAZORPAY RESPONSE
    # ==========================================

    razorpay_order_id = request.POST.get(
        "razorpay_order_id"
    )

    razorpay_payment_id = request.POST.get(
        "razorpay_payment_id"
    )

    razorpay_signature = request.POST.get(
        "razorpay_signature"
    )


    # ==========================================
    # CHECK REQUIRED DATA
    # ==========================================

    if not all([
        razorpay_order_id,
        razorpay_payment_id,
        razorpay_signature
    ]):

        messages.error(
            request,
            "Payment verification failed."
        )

        return redirect(
            "booking_history"
        )


    try:

        # ==========================================
        # FIND PAYMENT
        # ==========================================

        payment = get_object_or_404(
            Payment,
            razorpay_order_id=razorpay_order_id,
            booking__user=request.user
        )


        booking = payment.booking


        # ==========================================
        # PREVENT DUPLICATE PAYMENT PROCESSING
        # ==========================================

        if payment.status == "Paid":

            messages.info(
                request,
                "This payment has already been completed."
            )

            return redirect(
                "booking_details",
                booking_id=booking.id
            )


        # ==========================================
        # VERIFY RAZORPAY SIGNATURE
        # ==========================================

        razorpay_client.utility.verify_payment_signature({

            "razorpay_order_id":
                razorpay_order_id,

            "razorpay_payment_id":
                razorpay_payment_id,

            "razorpay_signature":
                razorpay_signature

        })


        # ==========================================
        # SAVE SUCCESSFUL PAYMENT
        # ==========================================

        payment.razorpay_payment_id = (
            razorpay_payment_id
        )

        payment.razorpay_signature = (
            razorpay_signature
        )

        payment.status = "Paid"

        payment.paid_at = timezone.now()

        payment.save()


        # ==========================================
        # CONFIRM BOOKING
        # ==========================================

        booking.status = "Confirmed"

        booking.save(
            update_fields=[
                "status"
            ]
        )


                # ==========================================
        # SEND CONFIRMATION EMAIL
        # ONLY AFTER SUCCESSFUL PAYMENT
        # ==========================================

        try:

            # Get current hotel settings
            hotel = HotelSettings.objects.first()

            if hotel is None:
                hotel = HotelSettings.objects.create(
                    hotel_name="Luxury Grand Hotel"
                )


            # Dynamic hotel name
            subject = f"🏨 Booking Confirmation - {hotel.hotel_name}"


            context = {

                "user":
                    request.user,

                "room":
                    booking.room,

                "booking":
                    booking,

                "hotel_settings":
                    hotel,

            }


            html_content = render_to_string(
                "emails/booking_confirmation.html",
                context
            )


            email = EmailMultiAlternatives(

                subject,

                "Your booking has been confirmed.",

                settings.DEFAULT_FROM_EMAIL,

                [request.user.email],

            )


            email.attach_alternative(
                html_content,
                "text/html"
            )


            # ==========================================
            # ATTACH / EMBED QR CODE
            # ==========================================

            if booking.qr_code:

                with open(
                    booking.qr_code.path,
                    "rb"
                ) as f:

                    qr_image = MIMEImage(
                        f.read()
                    )


                    qr_image.add_header(
                        "Content-ID",
                        "<qrcode>"
                    )


                    qr_image.add_header(
                        "Content-Disposition",
                        "inline",
                        filename="qrcode.png"
                    )


                    email.attach(
                        qr_image
                    )


            # ==========================================
            # SEND EMAIL
            # ==========================================

            if notification_enabled("payment"):
                email.send()


        except Exception as email_error:

            # Payment is already successful.
            # Do NOT mark the payment as failed
            # just because the email could not be sent.

            print(
                "Booking confirmation email error:",
                email_error
            )


        # ==========================================
        # SUCCESS MESSAGE
        # ==========================================

        messages.success(
            request,
            "Payment successful! Your booking has been confirmed."
        )


        return redirect(
            "booking_details",
            booking_id=booking.id
        )


    # ==========================================
    # RAZORPAY SIGNATURE ERROR
    # ==========================================

    except razorpay.errors.SignatureVerificationError:

        messages.error(
            request,
            "Payment verification failed. Please contact support."
        )

        return redirect(
            "booking_history"
        )


    # ==========================================
    # PAYMENT RECORD NOT FOUND
    # ==========================================

    except Payment.DoesNotExist:

        messages.error(
            request,
            "Payment record could not be found."
        )

        return redirect(
            "booking_history"
        )


    # ==========================================
    # OTHER ERRORS
    # ==========================================

    except Exception:

        messages.error(
            request,
            "Something went wrong while verifying your payment."
        )

        return redirect(
            "booking_history"
        )

@login_required
def test_payment_success(request, booking_id):

    # --------------------------------------------------
    # DEVELOPMENT ONLY
    # --------------------------------------------------

    if not settings.DEBUG:
        return redirect("booking_history")

    if request.method != "POST":
        return redirect(
            "payment_page",
            booking_id=booking_id
        )

    booking = get_object_or_404(
        Booking,
        id=booking_id,
        user=request.user
    )

    payment = get_object_or_404(
        Payment,
        booking=booking
    )

    # --------------------------------------------------
    # ALREADY PAID
    # --------------------------------------------------

    if payment.status == "Paid":

        messages.info(
            request,
            "This booking has already been paid."
        )

        return redirect(
            "booking_details",
            booking_id=booking.id
        )

    # --------------------------------------------------
    # SIMULATE SUCCESSFUL PAYMENT
    # --------------------------------------------------

    payment.razorpay_payment_id = (
        f"TEST_PAYMENT_{booking.id}_{int(timezone.now().timestamp())}"
    )

    payment.razorpay_signature = (
        "TEST_SIGNATURE_DEVELOPMENT_ONLY"
    )

    payment.status = "Paid"
    payment.paid_at = timezone.now()

    payment.save()

    # --------------------------------------------------
    # CONFIRM BOOKING
    # --------------------------------------------------

    booking.status = "Confirmed"

    booking.save(
        update_fields=["status"]
    )

    # --------------------------------------------------
    # SUCCESS MESSAGE
    # --------------------------------------------------

    messages.success(
        request,
        "Test payment successful! Your booking has been confirmed."
    )

    return redirect(
        "booking_details",
        booking_id=booking.id
    )


@login_required
def booking_history(request):

    # Automatically mark expired bookings as completed
    Booking.objects.filter(
        user=request.user,
        status="Confirmed",
        check_out__lt=timezone.now().date()
    ).update(status="Completed")

    bookings = Booking.objects.filter(user=request.user)

    reviewed_bookings = Review.objects.filter(
        user=request.user
    ).values_list('booking_id', flat=True)

    total_bookings = bookings.count()

    upcoming = bookings.filter(status="Confirmed").count()

    completed = bookings.filter(status="Completed").count()

    cancelled = bookings.filter(status="Cancelled").count()

    return render(request, 'booking_history.html', {
        'bookings': bookings,
        'reviewed_bookings': reviewed_bookings,
        'total_bookings': total_bookings,
        'upcoming': upcoming,
        'completed': completed,
        'cancelled': cancelled,
    })
    
@login_required
def booking_details(request, booking_id):

    booking = get_object_or_404(
        Booking,
        id=booking_id,
        user=request.user
    )

    # ==========================================
    # GENERATE QR CODE IF BOOKING DOES NOT HAVE ONE
    # ==========================================

    if not booking.qr_code:

        hotel = HotelSettings.objects.first()

        if hotel is None:
            hotel = HotelSettings.objects.create(
                hotel_name="Luxury Grand Hotel"
            )

        qr_data = f"""
{hotel.hotel_name}

Booking ID: PGH-{booking.id:05d}

Guest: {booking.user.username}

Room: {booking.room.room_type}

Room Number: {booking.room.room_number}

Check In: {booking.check_in}

Check Out: {booking.check_out}

Guests: {booking.guests}

Total Amount: ₹{booking.total_price}

Status: {booking.status}
"""

        qr = qrcode.make(qr_data)

        buffer = io.BytesIO()

        qr.save(
            buffer,
            format="PNG"
        )

        filename = f"booking_{booking.id}.png"

        booking.qr_code.save(
            filename,
            ContentFile(buffer.getvalue()),
            save=True
        )

    return render(
        request,
        'booking_details.html',
        {
            'booking': booking
        }   
    )
 
@login_required
def download_receipt(request, booking_id):

    booking = get_object_or_404(
        Booking,
        id=booking_id,
        user=request.user
    )

    hotel = HotelSettings.objects.first()

    if hotel is None:
        hotel = HotelSettings.objects.create(
            hotel_name="Luxury Grand Hotel"
        )

    # ==================================================
    # PDF RESPONSE
    # ==================================================

    response = HttpResponse(
        content_type="application/pdf"
    )

    filename = (
        f"{hotel.hotel_name}_Receipt_"
        f"PGH-{booking.id:05d}.pdf"
    )

    response["Content-Disposition"] = (
        f'attachment; filename="{filename}"'
    )

    # ==================================================
    # CREATE PDF
    # ==================================================

    pdf = canvas.Canvas(
        response,
        pagesize=A4
    )

    width, height = A4

    # ==================================================
    # PREMIUM COLORS
    # ==================================================

    purple = colors.HexColor("#4c1d95")
    purple_light = colors.HexColor("#7c3aed")
    gold = colors.HexColor("#f5c542")

    dark = colors.HexColor("#111827")
    gray = colors.HexColor("#64748b")

    light_gray = colors.HexColor("#f8fafc")
    border = colors.HexColor("#e5e7eb")

    green = colors.HexColor("#15803d")
    red = colors.HexColor("#dc2626")

    # ==================================================
    # WHITE BACKGROUND
    # ==================================================

    pdf.setFillColor(colors.white)

    pdf.rect(
        0,
        0,
        width,
        height,
        fill=1,
        stroke=0
    )

    # ==================================================
    # PREMIUM HEADER
    # ==================================================

    pdf.setFillColor(purple)

    pdf.roundRect(
        0,
        height - 145,
        width,
        145,
        0,
        fill=1,
        stroke=0
    )

    # Gold line

    pdf.setFillColor(gold)

    pdf.rect(
        0,
        height - 150,
        width,
        5,
        fill=1,
        stroke=0
    )

    # ==================================================
    # HOTEL NAME
    # ==================================================

    pdf.setFillColor(colors.white)

    pdf.setFont(
        "Helvetica-Bold",
        25
    )

    pdf.drawString(
        45,
        height - 55,
        hotel.hotel_name
    )

    # Subtitle

    pdf.setFont(
        "Helvetica",
        10
    )

    pdf.setFillColor(
        colors.HexColor("#e9d5ff")
    )

    pdf.drawString(
        47,
        height - 76,
        "Luxury Hospitality & Premium Accommodation"
    )

    # Address

    pdf.setFillColor(colors.white)

    pdf.setFont(
        "Helvetica",
        9
    )

    pdf.drawString(
        47,
        height - 101,
        hotel.hotel_address
    )

    pdf.drawString(
        47,
        height - 116,
         hotel.hotel_phone
    )

    pdf.drawString(
        47,
        height - 131,
        hotel.hotel_email
    )

    # ==================================================
    # RECEIPT BADGE
    # ==================================================

    badge_x = width - 205
    badge_y = height - 120

    pdf.setFillColor(colors.white)

    pdf.roundRect(
        badge_x,
        badge_y,
        155,
        65,
        12,
        fill=1,
        stroke=0
    )

    pdf.setFillColor(purple)

    pdf.setFont(
        "Helvetica-Bold",
        14
    )

    pdf.drawCentredString(
        badge_x + 77.5,
        badge_y + 40,
        "BOOKING RECEIPT"
    )

    pdf.setFillColor(gold)

    pdf.setFont(
        "Helvetica-Bold",
        11
    )

    pdf.drawCentredString(
        badge_x + 77.5,
        badge_y + 20,
        f"PGH-{booking.id:05d}"
    )

    # ==================================================
    # RECEIPT TITLE
    # ==================================================

    title_y = height - 190

    pdf.setFillColor(dark)

    pdf.setFont(
        "Helvetica-Bold",
        17
    )

    pdf.drawString(
        45,
        title_y,
        "Booking Confirmation"
    )

    # Gold divider

    pdf.setFillColor(gold)

    pdf.rect(
        45,
        title_y - 10,
        65,
        3,
        fill=1,
        stroke=0
    )

    # ==================================================
    # GUEST & RESERVATION CARD
    # ==================================================

    card_y = height - 330
    card_height = 105

    pdf.setFillColor(light_gray)

    pdf.roundRect(
        45,
        card_y,
        width - 90,
        card_height,
        12,
        fill=1,
        stroke=0
    )

    pdf.setStrokeColor(border)

    pdf.roundRect(
        45,
        card_y,
        width - 90,
        card_height,
        12,
        fill=0,
        stroke=1
    )

    # Card heading

    pdf.setFillColor(purple)

    pdf.setFont(
        "Helvetica-Bold",
        11
    )

    pdf.drawString(
        65,
        card_y + 80,
        "GUEST & RESERVATION"
    )

    # Left labels

    left_x = 65
    right_x = 315

    pdf.setFillColor(gray)

    pdf.setFont(
        "Helvetica",
        8
    )

    pdf.drawString(
        left_x,
        card_y + 58,
        "GUEST"
    )

    pdf.drawString(
        left_x,
        card_y + 30,
        "RESERVATION ID"
    )

    pdf.drawString(
        right_x,
        card_y + 58,
        "BOOKING DATE"
    )

    pdf.drawString(
        right_x,
        card_y + 30,
        "STATUS"
    )

    # Values

    pdf.setFillColor(dark)

    pdf.setFont(
        "Helvetica-Bold",
        10
    )

    pdf.drawString(
        left_x,
        card_y + 44,
        str(booking.user.username)
    )

    pdf.drawString(
        left_x,
        card_y + 16,
        f"PGH-{booking.id:05d}"
    )

    # Booking date

    pdf.drawString(
        right_x,
        card_y + 44,
        booking.booking_date.strftime("%d %b %Y")
    )

    # Status color

    if booking.status == "Confirmed":

        status_color = green

    elif booking.status == "Cancelled":

        status_color = red

    elif booking.status == "Completed":

        status_color = purple

    else:

        status_color = gold

    pdf.setFillColor(status_color)

    pdf.setFont(
        "Helvetica-Bold",
        10
    )

    pdf.drawString(
        right_x,
        card_y + 16,
        str(booking.status)
    )

    # ==================================================
    # ROOM DETAILS
    # ==================================================

    room_title_y = card_y - 35

    pdf.setFillColor(dark)

    pdf.setFont(
        "Helvetica-Bold",
        14
    )

    pdf.drawString(
        45,
        room_title_y,
        "Room Details"
    )

    pdf.setFillColor(gold)

    pdf.rect(
        45,
        room_title_y - 10,
        55,
        3,
        fill=1,
        stroke=0
    )

    # Room card

    room_card_y = room_title_y - 120

    pdf.setFillColor(colors.white)

    pdf.roundRect(
        45,
        room_card_y,
        width - 90,
        100,
        12,
        fill=1,
        stroke=0
    )

    pdf.setStrokeColor(border)

    pdf.roundRect(
        45,
        room_card_y,
        width - 90,
        100,
        12,
        fill=0,
        stroke=1
    )

    # Room labels

    pdf.setFillColor(gray)

    pdf.setFont(
        "Helvetica",
        8
    )

    pdf.drawString(
        65,
        room_card_y + 72,
        "ROOM"
    )

    pdf.drawString(
        215,
        room_card_y + 72,
        "ROOM NUMBER"
    )

    pdf.drawString(
        365,
        room_card_y + 72,
        "GUESTS"
    )

    pdf.drawString(
        65,
        room_card_y + 35,
        "CHECK IN"
    )

    pdf.drawString(
        215,
        room_card_y + 35,
        "CHECK OUT"
    )

    # Room values

    pdf.setFillColor(dark)

    pdf.setFont(
        "Helvetica-Bold",
        10
    )

    pdf.drawString(
        65,
        room_card_y + 54,
        str(booking.room.room_type)
    )

    pdf.drawString(
        215,
        room_card_y + 54,
        str(booking.room.room_number)
    )

    pdf.drawString(
        365,
        room_card_y + 54,
        str(booking.guests)
    )

    pdf.drawString(
        65,
        room_card_y + 17,
        booking.check_in.strftime("%d %b %Y")
    )

    pdf.drawString(
        215,
        room_card_y + 17,
        booking.check_out.strftime("%d %b %Y")
    )

    # ==================================================
    # PAYMENT SUMMARY
    # ==================================================

    payment_title_y = room_card_y - 35

    pdf.setFillColor(dark)

    pdf.setFont(
        "Helvetica-Bold",
        14
    )

    pdf.drawString(
        45,
        payment_title_y,
        "Payment Summary"
    )

    pdf.setFillColor(gold)

    pdf.rect(
        45,
        payment_title_y - 10,
        55,
        3,
        fill=1,
        stroke=0
    )

    # Payment card

    payment_card_y = payment_title_y - 115

    pdf.setFillColor(light_gray)

    pdf.roundRect(
        45,
        payment_card_y,
        width - 90,
        90,
        12,
        fill=1,
        stroke=0
    )

    pdf.setStrokeColor(border)

    pdf.roundRect(
        45,
        payment_card_y,
        width - 90,
        90,
        12,
        fill=0,
        stroke=1
    )

    # Room price

    pdf.setFillColor(gray)

    pdf.setFont(
        "Helvetica",
        10
    )

    pdf.drawString(
        65,
        payment_card_y + 62,
        "Room Price"
    )

    pdf.drawRightString(
        width - 65,
        payment_card_y + 62,
        f"Rs. {booking.room.price}"
    )

    # Guests

    pdf.drawString(
        65,
        payment_card_y + 40,
        "Guests"
    )

    pdf.drawRightString(
        width - 65,
        payment_card_y + 40,
        str(booking.guests)
    )

    # Total background

    pdf.setFillColor(
        colors.HexColor("#f3e8ff")
    )

    pdf.roundRect(
        55,
        payment_card_y + 8,
        width - 110,
        24,
        8,
        fill=1,
        stroke=0
    )

    # Total label

    pdf.setFillColor(purple)

    pdf.setFont(
        "Helvetica-Bold",
        11
    )

    pdf.drawString(
        70,
        payment_card_y + 15,
        "TOTAL AMOUNT"
    )

    # Total value

    pdf.setFillColor(gold)

    pdf.setFont(
        "Helvetica-Bold",
        14
    )

    pdf.drawRightString(
        width - 70,
        payment_card_y + 15,
        f"Rs. {booking.total_price}"
    )

    # ==================================================
    # FOOTER
    # ==================================================

    pdf.setFillColor(purple)

    pdf.rect(
        0,
        0,
        width,
        48,
        fill=1,
        stroke=0
    )

    # Footer hotel name

    pdf.setFillColor(colors.white)

    pdf.setFont(
        "Helvetica-Bold",
        9
    )

    pdf.drawString(
        45,
        29,
        hotel.hotel_name
    )

    # Footer message

    pdf.setFont(
        "Helvetica",
        8
    )

    pdf.drawString(
        45,
        15,
        "Thank you for choosing us. We look forward to welcoming you."
    )

    # Footer reservation ID

    pdf.setFillColor(gold)

    pdf.setFont(
        "Helvetica-Bold",
        9
    )

    pdf.drawRightString(
        width - 45,
        24,
        f"PGH-{booking.id:05d}"
    )

    # ==================================================
    # SAVE PDF
    # ==================================================

    pdf.save()

    return response
    
@login_required
def download_invoice(request, booking_id):

    booking = get_object_or_404(
        Booking,
        id=booking_id,
        user=request.user
    )
    
    hotel = HotelSettings.objects.first()

    if hotel is None:
        hotel = HotelSettings.objects.create(
            hotel_name="Luxury Grand Hotel"
        )

    # ==================================================
    # PDF RESPONSE
    # ==================================================

    response = HttpResponse(
        content_type="application/pdf"
    )

    hotel_filename = hotel.hotel_name.replace(
      " ",
      "_"
    )

    filename = (
       f"{hotel_filename}_Invoice_PGH-{booking.id:05d}.pdf"
    )

    response["Content-Disposition"] = (
        f'attachment; filename="{filename}"'
    )

    # ==================================================
    # CREATE PDF
    # ==================================================

    pdf = canvas.Canvas(
        response,
        pagesize=A4
    )

    width, height = A4

    # ==================================================
    # PREMIUM COLORS
    # ==================================================

    purple = colors.HexColor("#4c1d95")
    purple_light = colors.HexColor("#7c3aed")
    gold = colors.HexColor("#f5c542")

    dark = colors.HexColor("#111827")
    gray = colors.HexColor("#64748b")
    light_gray = colors.HexColor("#f8fafc")
    border = colors.HexColor("#e5e7eb")

    green = colors.HexColor("#15803d")
    red = colors.HexColor("#dc2626")

    # ==================================================
    # BACKGROUND
    # ==================================================

    pdf.setFillColor(colors.white)

    pdf.rect(
        0,
        0,
        width,
        height,
        fill=1,
        stroke=0
    )

    # ==================================================
    # PREMIUM HEADER
    # ==================================================

    pdf.setFillColor(purple)

    pdf.roundRect(
        0,
        height - 150,
        width,
        150,
        0,
        fill=1,
        stroke=0
    )

    pdf.setFillColor(gold)

    pdf.rect(
        0,
        height - 154,
        width,
        4,
        fill=1,
        stroke=0
    )

    # Hotel name

    pdf.setFillColor(colors.white)

    pdf.setFont(
        "Helvetica-Bold",
        25
    )

    pdf.drawString(
        45,
        height - 55,
        hotel.hotel_name
    )

    # Subtitle

    pdf.setFont(
        "Helvetica",
        10
    )

    pdf.setFillColor(
        colors.HexColor("#e9d5ff")
    )

    pdf.drawString(
        47,
        height - 76,
        "Luxury Hospitality & Premium Accommodation"
    )

    # Address

    pdf.setFont(
        "Helvetica",
        9
    )

    pdf.setFillColor(colors.white)

    pdf.drawString(
        47,
        height - 101,
           hotel.hotel_address
    )

    pdf.drawString(
        47,
        height - 116,
        hotel.hotel_phone
    )

    pdf.drawString(
        47,
        height - 131,
        hotel.hotel_email
    )

    # ==================================================
    # INVOICE BADGE
    # ==================================================

    pdf.setFillColor(colors.white)

    pdf.roundRect(
        width - 210,
        height - 125,
        160,
        70,
        12,
        fill=1,
        stroke=0
    )

    pdf.setFillColor(purple)

    pdf.setFont(
        "Helvetica-Bold",
        14
    )

    pdf.drawCentredString(
        width - 130,
        height - 80,
        "BOOKING INVOICE"
    )

    pdf.setFillColor(gold)

    pdf.setFont(
        "Helvetica-Bold",
        11
    )

    pdf.drawCentredString(
        width - 130,
        height - 102,
        f"PGH-{booking.id:05d}"
    )

    # ==================================================
    # GUEST + RESERVATION
    # ==================================================

    section_top = height - 195

    pdf.setFillColor(dark)

    pdf.setFont(
        "Helvetica-Bold",
        14
    )

    pdf.drawString(
        45,
        section_top,
        "Guest & Reservation"
    )

    pdf.setFillColor(gold)

    pdf.rect(
        45,
        section_top - 10,
        55,
        3,
        fill=1,
        stroke=0
    )

    # Guest card

    card_y = section_top - 125

    pdf.setFillColor(light_gray)

    pdf.roundRect(
        45,
        card_y,
        width - 90,
        100,
        12,
        fill=1,
        stroke=0
    )

    pdf.setStrokeColor(border)

    pdf.roundRect(
        45,
        card_y,
        width - 90,
        100,
        12,
        fill=0,
        stroke=1
    )

    left_x = 65
    right_x = 315

    pdf.setFillColor(gray)

    pdf.setFont(
        "Helvetica",
        9
    )

    pdf.drawString(
        left_x,
        card_y + 75,
        "GUEST NAME"
    )

    pdf.drawString(
        left_x,
        card_y + 42,
        "RESERVATION ID"
    )

    pdf.drawString(
        right_x,
        card_y + 75,
        "BOOKING DATE"
    )

    pdf.drawString(
        right_x,
        card_y + 42,
        "STATUS"
    )

    pdf.setFillColor(dark)

    pdf.setFont(
        "Helvetica-Bold",
        11
    )

    pdf.drawString(
        left_x,
        card_y + 59,
        str(booking.user.username)
    )

    pdf.drawString(
        left_x,
        card_y + 26,
        f"PGH-{booking.id:05d}"
    )

    pdf.drawString(
        right_x,
        card_y + 59,
        booking.booking_date.strftime("%d %b %Y")
    )

    # Status color

    if booking.status == "Confirmed":

        status_color = green

    elif booking.status == "Cancelled":

        status_color = red

    else:

        status_color = gold

    pdf.setFillColor(status_color)

    pdf.drawString(
        right_x,
        card_y + 26,
        str(booking.status)
    )

    # ==================================================
    # ROOM DETAILS
    # ==================================================

    room_title_y = card_y - 40

    pdf.setFillColor(dark)

    pdf.setFont(
        "Helvetica-Bold",
        14
    )

    pdf.drawString(
        45,
        room_title_y,
        "Room Details"
    )

    pdf.setFillColor(gold)

    pdf.rect(
        45,
        room_title_y - 10,
        55,
        3,
        fill=1,
        stroke=0
    )

    room_card_y = room_title_y - 115

    pdf.setFillColor(colors.white)

    pdf.roundRect(
        45,
        room_card_y,
        width - 90,
        90,
        12,
        fill=1,
        stroke=0
    )

    pdf.setStrokeColor(border)

    pdf.roundRect(
        45,
        room_card_y,
        width - 90,
        90,
        12,
        fill=0,
        stroke=1
    )

    pdf.setFillColor(gray)

    pdf.setFont(
        "Helvetica",
        9
    )

    pdf.drawString(
        65,
        room_card_y + 63,
        "ROOM TYPE"
    )

    pdf.drawString(
        215,
        room_card_y + 63,
        "ROOM NUMBER"
    )

    pdf.drawString(
        365,
        room_card_y + 63,
        "GUESTS"
    )

    pdf.drawString(
        65,
        room_card_y + 25,
        "CHECK-IN"
    )

    pdf.drawString(
        215,
        room_card_y + 25,
        "CHECK-OUT"
    )

    pdf.setFillColor(dark)

    pdf.setFont(
        "Helvetica-Bold",
        10
    )

    pdf.drawString(
        65,
        room_card_y + 45,
        str(booking.room.room_type)
    )

    pdf.drawString(
        215,
        room_card_y + 45,
        str(booking.room.room_number)
    )

    pdf.drawString(
        365,
        room_card_y + 45,
        str(booking.guests)
    )

    pdf.drawString(
        65,
        room_card_y + 8,
        booking.check_in.strftime("%d %b %Y")
    )

    pdf.drawString(
        215,
        room_card_y + 8,
        booking.check_out.strftime("%d %b %Y")
    )

    # ==================================================
    # PAYMENT SECTION
    # ==================================================

    payment_title_y = room_card_y - 40

    pdf.setFillColor(dark)

    pdf.setFont(
        "Helvetica-Bold",
        14
    )

    pdf.drawString(
        45,
        payment_title_y,
        "Payment Summary"
    )

    pdf.setFillColor(gold)

    pdf.rect(
        45,
        payment_title_y - 10,
        55,
        3,
        fill=1,
        stroke=0
    )

    payment_card_y = payment_title_y - 125

    pdf.setFillColor(light_gray)

    pdf.roundRect(
        45,
        payment_card_y,
        width - 90,
        100,
        12,
        fill=1,
        stroke=0
    )

    pdf.setStrokeColor(border)

    pdf.roundRect(
        45,
        payment_card_y,
        width - 90,
        100,
        12,
        fill=0,
        stroke=1
    )

    pdf.setFillColor(gray)

    pdf.setFont(
        "Helvetica",
        10
    )

    # Room price

    pdf.drawString(
        65,
        payment_card_y + 65,
        "Room Price"
    )

    pdf.drawRightString(
        width - 65,
        payment_card_y + 65,
        f"Rs. {booking.room.price}"
    )

    # Guests

    pdf.drawString(
        65,
        payment_card_y + 42,
        "Guests"
    )

    pdf.drawRightString(
        width - 65,
        payment_card_y + 42,
        str(booking.guests)
    )

    # Total background

    pdf.setFillColor(
        colors.HexColor("#f3e8ff")
    )

    pdf.roundRect(
        55,
        payment_card_y + 8,
        width - 110,
        25,
        8,
        fill=1,
        stroke=0
    )

    pdf.setFillColor(purple)

    pdf.setFont(
        "Helvetica-Bold",
        12
    )

    pdf.drawString(
        70,
        payment_card_y + 16,
        "TOTAL AMOUNT"
    )

    pdf.setFillColor(gold)

    pdf.setFont(
        "Helvetica-Bold",
        15
    )

    pdf.drawRightString(
        width - 70,
        payment_card_y + 16,
        f"Rs. {booking.total_price}"
    )

    # ==================================================
    # QR VERIFICATION
    # ==================================================

    verification_y = 75

    pdf.setFillColor(light_gray)

    pdf.roundRect(
        45,
        verification_y - 5,
        width - 90,
        95,
        12,
        fill=1,
        stroke=0
    )

    pdf.setStrokeColor(border)

    pdf.roundRect(
        45,
        verification_y - 5,
        width - 90,
        95,
        12,
        fill=0,
        stroke=1
    )

    # Heading

    pdf.setFillColor(dark)

    pdf.setFont(
        "Helvetica-Bold",
        11
    )

    pdf.drawString(
        65,
        verification_y + 67,
        "QR VERIFICATION"
    )

    pdf.setFillColor(gray)

    pdf.setFont(
        "Helvetica",
        8
    )

    pdf.drawString(
        65,
        verification_y + 52,
        "Present this QR code at reception"
    )

    pdf.drawString(
        65,
        verification_y + 39,
        "for quick reservation verification."
    )

    # Reservation ID

    pdf.setFillColor(purple)

    pdf.setFont(
        "Helvetica-Bold",
        10
    )

    pdf.drawString(
        65,
        verification_y + 17,
        f"Reservation: PGH-{booking.id:05d}"
    )

    # QR Code

    if booking.qr_code:

        try:

            qr_size = 70

            qr_x = width - 135
            qr_y = verification_y + 8

            pdf.setFillColor(colors.white)

            pdf.roundRect(
                qr_x - 6,
                qr_y - 6,
                qr_size + 12,
                qr_size + 12,
                8,
                fill=1,
                stroke=0
            )

            pdf.drawImage(
                booking.qr_code.path,
                qr_x,
                qr_y,
                width=qr_size,
                height=qr_size,
                preserveAspectRatio=True,
                mask="auto"
            )

        except Exception:
            pass

    # ==================================================
    # FOOTER
    # ==================================================

    pdf.setFillColor(purple)

    pdf.rect(
        0,
        0,
        width,
        45,
        fill=1,
        stroke=0
    )

    pdf.setFillColor(colors.white)

    pdf.setFont(
        "Helvetica-Bold",
        9
    )

    pdf.drawString(
        45,
        27,
        hotel.hotel_name
    )

    pdf.setFont(
        "Helvetica",
        8
    )

    pdf.drawString(
        45,
        13,
        "Thank you for choosing us. We look forward to welcoming you."
    )

    pdf.setFillColor(gold)

    pdf.setFont(
        "Helvetica-Bold",
        9
    )

    pdf.drawRightString(
        width - 45,
        20,
        f"PGH-{booking.id:05d}"
    )

    # ==================================================
    # SAVE PDF
    # ==================================================

    pdf.save()

    return response

# ==============================
# MODIFY BOOKING
# ==============================

@login_required
def modify_booking(request, booking_id):
    booking = get_object_or_404(
        Booking,
        id=booking_id,
        user=request.user
    )

    if booking.status in ["Cancelled", "Completed"]:
        messages.warning(
            request,
            "This booking cannot be modified."
        )
        return redirect("booking_details", booking_id=booking.id)

    hotel = HotelSettings.objects.first()

    if hotel is None:
        hotel = HotelSettings.objects.create(
            hotel_name="Luxury Grand Hotel"
        )

    if request.method == "POST":
        form = BookingForm(
            request.POST,
            instance=booking
        )

        if form.is_valid():
            check_in = form.cleaned_data["check_in"]
            check_out = form.cleaned_data["check_out"]
            guests = form.cleaned_data["guests"]

            if check_in < timezone.localdate():
                form.add_error(
                    "check_in",
                    "Check-in cannot be in the past."
                )

            elif check_out <= check_in:
                form.add_error(
                    "check_out",
                    "Check-out must be after check-in."
                )

            elif room_has_booking_conflict(
                booking.room,
                check_in,
                check_out,
                exclude_booking_id=booking.id
            ):
                form.add_error(
                    None,
                    "This room is already booked for those dates."
                )

            else:
                booking.check_in = check_in
                booking.check_out = check_out
                booking.guests = guests
                booking.total_price = (
                    check_out - check_in
                ).days * booking.room.price

                booking.save()

                messages.success(
                    request,
                    "Your booking has been modified successfully."
                )

                return redirect(
                    "booking_details",
                    booking_id=booking.id
                )
    else:
        form = BookingForm(instance=booking)

    return render(
        request,
        "modify_booking.html",
        {
            "booking": booking,
            "form": form,
            "hotel_settings": hotel,
        }
        
    )

# ==============================
# CANCEL BOOKING
# ==============================

@login_required
def cancel_booking(request, booking_id):

    booking = get_object_or_404(
        Booking,
        id=booking_id,
        user=request.user
    )

    if booking.status != "Cancelled":

        booking.status = "Cancelled"
        booking.save()

        # ==========================================
        # GET HOTEL SETTINGS
        # ==========================================

        hotel = HotelSettings.objects.first()

        if hotel is None:
            hotel = HotelSettings.objects.create(
                hotel_name="Luxury Grand Hotel"
            )

        # ==========================================
        # SEND CANCELLATION EMAIL
        # ==========================================

        subject = f"❌ Booking Cancelled - {hotel.hotel_name}"

        context = {
            "user": request.user,
            "booking": booking,
            "hotel_settings": hotel,
        }

        html_content = render_to_string(
            "emails/booking_cancellation.html",
            context
        )

        email = EmailMultiAlternatives(
            subject,
            "Your booking has been cancelled.",
            settings.DEFAULT_FROM_EMAIL,
            [request.user.email],
        )

        email.attach_alternative(
            html_content,
            "text/html"
        )

        # ==========================================
        # SEND ONLY IF CANCELLATION NOTIFICATIONS
        # ARE ENABLED
        # ==========================================

        if notification_enabled("cancellation"):
            email.send()

        messages.success(
            request,
            "Your booking has been cancelled successfully."
        )

    return redirect("booking_history")

def about(request):
    return render(request, 'about.html')


def gallery(request):
    return render(request, 'gallery.html')


def contact(request):

    if request.method == 'POST':
        form = ContactForm(request.POST)

        if form.is_valid():
            form.save()

            messages.success(
                request,
                "Thank you! Your message has been sent successfully."
            )

            return redirect('contact')

    else:
        form = ContactForm()

    return render(request, 'contact.html', {
        'form': form
    })

# ==============================
# DELETE BOOKING
# ==============================

@login_required
def delete_booking(request, booking_id):

    booking = get_object_or_404(
        Booking,
        id=booking_id,
        user=request.user
    )

    if request.method == "POST":

        booking.delete()

        messages.success(
            request,
            "Booking has been deleted successfully."
        )

    return redirect("booking_history")


@login_required
def add_to_wishlist(request, room_id):
    room = get_object_or_404(Room, id=room_id)

    Wishlist.objects.get_or_create(
        user=request.user,
        room=room
    )

    return redirect('rooms')


@login_required
def remove_from_wishlist(request, room_id):
    room = get_object_or_404(Room, id=room_id)

    Wishlist.objects.filter(
        user=request.user,
        room=room
    ).delete()

    return redirect('wishlist')


@login_required
def wishlist(request):
    wishlist_items = Wishlist.objects.filter(
        user=request.user
    ).select_related("room")

    return render(
        request,
        "wishlist.html",
        {
            "wishlist_items": wishlist_items,
        },
    )    

@login_required
def add_review(request, booking_id):
    booking = get_object_or_404(
        Booking,
        id=booking_id,
        user=request.user
    )

    if booking.status != "Completed":
        messages.error(
           request,
           "You can review a room only after your booking is completed."
        )
        return redirect("booking_history")

    # Prevent duplicate review
    if Review.objects.filter(booking=booking).exists():
        messages.warning(request, "You have already reviewed this booking.")
        return redirect('booking_history')

    if request.method == 'POST':
        form = ReviewForm(request.POST)

        if form.is_valid():
            review = form.save(commit=False)
            review.user = request.user
            review.room = booking.room
            review.booking = booking
            review.save()

            messages.success(request, "Thank you! Your review has been submitted.")
            return redirect('booking_history')

    else:
        form = ReviewForm()

    return render(request, 'add_review.html', {
        'form': form,
        'booking': booking
    })
    
# ==========================================================
# ADMIN DASHBOARD
# ==========================================================

@login_required
def admin_dashboard(request):

    # ------------------------------------------------------
    # ADMIN PROTECTION
    # ------------------------------------------------------

    if not request.user.is_staff:
        messages.error(
            request,
            "You do not have permission to access the admin dashboard."
        )

        return redirect("home")

    # ------------------------------------------------------
    # BASIC STATISTICS
    # ------------------------------------------------------

    total_users = User.objects.count()

    total_rooms = Room.objects.count()

    total_bookings = Booking.objects.count()

    # ------------------------------------------------------
    # ROOM AVAILABILITY
    # ------------------------------------------------------

    available_rooms = Room.objects.filter(
        available=True
    ).count()

    unavailable_rooms = Room.objects.filter(
        available=False
    ).count()

    # ------------------------------------------------------
    # BOOKING STATISTICS
    # ------------------------------------------------------

    pending_bookings = Booking.objects.filter(
        status="Pending"
    ).count()

    confirmed_bookings = Booking.objects.filter(
        status="Confirmed"
    ).count()

    cancelled_bookings = Booking.objects.filter(
        status="Cancelled"
    ).count()

    completed_bookings = Booking.objects.filter(
        status="Completed"
    ).count()

    # ------------------------------------------------------
    # REVENUE
    #
    # Only count successful payments.
    # Razorpay is currently paused, but this structure
    # will work when payments are resumed.
    # ------------------------------------------------------

    total_revenue = Payment.objects.filter(
        status="Paid"
    ).aggregate(
        total=Sum("amount")
    )["total"] or 0

    # ------------------------------------------------------
    # RECENT BOOKINGS
    # ------------------------------------------------------

    recent_bookings = Booking.objects.select_related(
        "user",
        "room"
    ).order_by(
        "-booking_date"
    )[:10]

    # ------------------------------------------------------
    # RECENT PAYMENTS
    # ------------------------------------------------------

    recent_payments = Payment.objects.select_related(
        "booking",
        "booking__user"
    ).order_by(
        "-created_at"
    )[:5]

    # ------------------------------------------------------
    # ROOM TYPE STATISTICS
    # ------------------------------------------------------

    room_type_statistics = Room.objects.values(
        "room_type"
    ).annotate(
        total=Count("id")
    ).order_by(
        "-total"
    )

    # ------------------------------------------------------
    # DASHBOARD CONTEXT
    # ------------------------------------------------------

    context = {

        "total_users": total_users,

        "total_rooms": total_rooms,

        "total_bookings": total_bookings,

        "total_revenue": total_revenue,

        "available_rooms": available_rooms,

        "unavailable_rooms": unavailable_rooms,

        "pending_bookings": pending_bookings,

        "confirmed_bookings": confirmed_bookings,

        "completed_bookings": completed_bookings,

        "cancelled_bookings": cancelled_bookings,

        "recent_bookings": recent_bookings,

        "recent_payments": recent_payments,

        "room_type_statistics":
            room_type_statistics,

    }

    return render(
        request,
        "admin/dashboard.html",
        context
    )
    
    
# =========================================================
# ADMIN SETTINGS
# =========================================================
# =========================================================
# HOTEL SETTINGS
# =========================================================

@login_required
def hotel_settings(request):

    if not request.user.is_staff:
        return redirect("home")

    hotel = HotelSettings.objects.first()

    if hotel is None:
        hotel = HotelSettings.objects.create(
            hotel_name="Luxury Grand Hotel"
        )

    if request.method == "POST":

        hotel.hotel_name = request.POST.get(
            "hotel_name",
            "Luxury Grand Hotel"
        ).strip()

        hotel.hotel_email = request.POST.get(
            "hotel_email",
            ""
        ).strip()

        hotel.hotel_phone = request.POST.get(
            "hotel_phone",
            ""
        ).strip()

        hotel.hotel_address = request.POST.get(
            "hotel_address",
            ""
        ).strip()

        hotel.save()

        messages.success(
            request,
            "Hotel settings updated successfully."
        )

        return redirect("hotel_settings")

    context = {
        "hotel_name": hotel.hotel_name,
        "hotel_email": hotel.hotel_email,
        "hotel_phone": hotel.hotel_phone,
        "hotel_address": hotel.hotel_address,
    }

    return render(
        request,
        "admin/hotel_settings.html",
        context
    )

# =========================================================
# NOTIFICATION SETTINGS
# =========================================================

@login_required
def notification_settings(request):

    if not request.user.is_staff:
        return redirect("home")

    notification = NotificationSettings.objects.first()

    if notification is None:
        notification = NotificationSettings.objects.create()

    if request.method == "POST":

        notification.booking_notifications = (
            request.POST.get("booking_notifications") == "on"
        )

        notification.payment_notifications = (
            request.POST.get("payment_notifications") == "on"
        )

        notification.cancellation_notifications = (
            request.POST.get("cancellation_notifications") == "on"
        )

        notification.email_notifications = (
            request.POST.get("email_notifications") == "on"
        )

        notification.save()

        messages.success(
            request,
            "Notification preferences saved."
        )

        return redirect("notification_settings")

    context = {
        "booking_notifications":
            notification.booking_notifications,

        "payment_notifications":
            notification.payment_notifications,

        "cancellation_notifications":
            notification.cancellation_notifications,

        "email_notifications":
            notification.email_notifications,
    }

    return render(
        request,
        "admin/notification_settings.html",
        context
    )

# =========================================================
# SECURITY SETTINGS
# =========================================================

def security_settings(request):

    if not request.user.is_staff:
        return redirect('home')

    if request.method == "POST":

        current_password = request.POST.get(
            "current_password"
        )

        new_password = request.POST.get(
            "new_password"
        )

        confirm_password = request.POST.get(
            "confirm_password"
        )

        if not request.user.check_password(
            current_password
        ):

            messages.error(
                request,
                "Current password is incorrect."
            )

        elif new_password != confirm_password:

            messages.error(
                request,
                "New passwords do not match."
            )

        elif len(new_password) < 8:

            messages.error(
                request,
                "Password must contain at least 8 characters."
            )

        else:

            request.user.set_password(
                new_password
            )

            request.user.save()

            update_session_auth_hash(
                request,
                request.user
            )

            messages.success(
                request,
                "Your password has been updated successfully."
            )

            return redirect(
                "security_settings"
            )

    return render(
        request,
        "admin/security_settings.html"
    )


# =========================================================
# ADMIN PROFILE
# =========================================================

def admin_profile(request):

    if not request.user.is_staff:
        return redirect('home')

    if request.method == "POST":

        request.user.first_name = request.POST.get(
            "first_name",
            ""
        )

        request.user.last_name = request.POST.get(
            "last_name",
            ""
        )

        request.user.email = request.POST.get(
            "email",
            ""
        )

        request.user.save()

        messages.success(
            request,
            "Administrator profile updated successfully."
        )

        return redirect("admin_profile")

    return render(
        request,
        "admin/admin_profile.html"
    )
    
# =========================================================
# ADMIN ROOM MANAGEMENT
# =========================================================


@login_required
def admin_rooms(request):

    # -----------------------------------------------------
    # ADMIN PROTECTION
    # -----------------------------------------------------

    if not request.user.is_staff:
        messages.error(
            request,
            "You do not have permission to access room management."
        )

        return redirect("home")


    # -----------------------------------------------------
    # GET SEARCH / FILTER VALUES
    # -----------------------------------------------------

    search = request.GET.get("search", "").strip()

    room_type = request.GET.get(
        "room_type",
        ""
    ).strip()

    availability = request.GET.get(
        "availability",
        ""
    ).strip()


    # -----------------------------------------------------
    # GET ALL ROOMS
    # -----------------------------------------------------

    room_list = Room.objects.all().order_by(
        "room_number"
    )


    # -----------------------------------------------------
    # SEARCH
    # -----------------------------------------------------

    if search:

        room_list = room_list.filter(
            Q(room_number__icontains=search)
            | Q(room_type__icontains=search)
        )


    # -----------------------------------------------------
    # ROOM TYPE FILTER
    # -----------------------------------------------------

    if room_type:

        room_list = room_list.filter(
            room_type=room_type
        )


    # -----------------------------------------------------
    # AVAILABILITY FILTER
    # -----------------------------------------------------

    if availability == "available":

        room_list = room_list.filter(
            available=True
        )

    elif availability == "unavailable":

        room_list = room_list.filter(
            available=False
        )


    # -----------------------------------------------------
    # ROOM STATISTICS
    # -----------------------------------------------------

    total_rooms = Room.objects.count()

    available_rooms = Room.objects.filter(
        available=True
    ).count()

    unavailable_rooms = Room.objects.filter(
        available=False
    ).count()


    # -----------------------------------------------------
    # ROOM TYPES
    # -----------------------------------------------------

    room_types = Room.objects.values_list(
        "room_type",
        flat=True
    ).distinct().order_by(
        "room_type"
    )


    # -----------------------------------------------------
    # CONTEXT
    # -----------------------------------------------------

    context = {

        "rooms": room_list,

        "total_rooms":
            total_rooms,

        "available_rooms":
            available_rooms,

        "unavailable_rooms":
            unavailable_rooms,

        "room_types":
            room_types,

        "search":
            search,

        "selected_room_type":
            room_type,

        "selected_availability":
            availability,

    }


    return render(
        request,
        "admin/rooms.html",
        context
    )



# =========================================================
# ADD ROOM
# =========================================================


@login_required
def admin_room_add(request):

    # -----------------------------------------------------
    # ADMIN PROTECTION
    # -----------------------------------------------------

    if not request.user.is_staff:

        messages.error(
            request,
            "You do not have permission to add rooms."
        )

        return redirect("home")


    # -----------------------------------------------------
    # FORM SUBMISSION
    # -----------------------------------------------------

    if request.method == "POST":

        form = RoomForm(
            request.POST,
            request.FILES
        )


        if form.is_valid():

            room = form.save()


            messages.success(
                request,
                f"Room {room.room_number} has been added successfully."
            )


            return redirect(
                "admin_rooms"
            )


    else:

        form = RoomForm()


    # -----------------------------------------------------
    # RENDER
    # -----------------------------------------------------

    return render(
        request,
        "admin/room_form.html",
        {
            "form": form,
            "page_title": "Add New Room",
            "form_action": "Add Room",
        }
    )



# =========================================================
# EDIT ROOM
# =========================================================


@login_required
def admin_room_edit(request, room_id):

    # -----------------------------------------------------
    # ADMIN PROTECTION
    # -----------------------------------------------------

    if not request.user.is_staff:

        messages.error(
            request,
            "You do not have permission to edit rooms."
        )

        return redirect("home")


    # -----------------------------------------------------
    # GET ROOM
    # -----------------------------------------------------

    room = get_object_or_404(
        Room,
        id=room_id
    )


    # -----------------------------------------------------
    # FORM SUBMISSION
    # -----------------------------------------------------

    if request.method == "POST":

        form = RoomForm(
            request.POST,
            request.FILES,
            instance=room
        )


        if form.is_valid():

            room = form.save()


            messages.success(
                request,
                f"Room {room.room_number} has been updated successfully."
            )


            return redirect(
                "admin_rooms"
            )


    else:

        form = RoomForm(
            instance=room
        )


    # -----------------------------------------------------
    # RENDER
    # -----------------------------------------------------

    return render(
        request,
        "admin/room_form.html",
        {
            "form": form,
            "room": room,
            "page_title": "Edit Room",
            "form_action": "Update Room",
        }
    )



# =========================================================
# DELETE ROOM
# =========================================================


@login_required
def admin_room_delete(request, room_id):

    # -----------------------------------------------------
    # ADMIN PROTECTION
    # -----------------------------------------------------

    if not request.user.is_staff:

        messages.error(
            request,
            "You do not have permission to delete rooms."
        )

        return redirect("home")


    # -----------------------------------------------------
    # GET ROOM
    # -----------------------------------------------------

    room = get_object_or_404(
        Room,
        id=room_id
    )


    # -----------------------------------------------------
    # DELETE ONLY THROUGH POST
    # -----------------------------------------------------

    if request.method == "POST":

        room_number = room.room_number

        room.delete()


        messages.success(
            request,
            f"Room {room_number} has been deleted successfully."
        )


        return redirect(
            "admin_rooms"
        )


    # -----------------------------------------------------
    # IF SOMEONE OPENS DELETE URL DIRECTLY
    # -----------------------------------------------------

    return redirect(
        "admin_rooms"
    )
    
# =========================================================
# ADMIN USER MANAGEMENT
# =========================================================

@login_required
def admin_users(request):
    if not request.user.is_staff:
        messages.error(
            request,
            "You do not have permission to access user management."
        )
        return redirect("home")

    search = request.GET.get("search", "").strip()

    users = User.objects.all().order_by("-date_joined")

    if search:
        users = users.filter(
            Q(username__icontains=search)
            | Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
            | Q(email__icontains=search)
        )

    total_users = User.objects.count()
    staff_users = User.objects.filter(is_staff=True).count()
    normal_users = User.objects.filter(is_staff=False).count()
    active_users = User.objects.filter(is_active=True).count()

    context = {
        "users": users,
        "total_users": total_users,
        "staff_users": staff_users,
        "normal_users": normal_users,
        "active_users": active_users,
        "search": search,
    }

    return render(
        request,
        "admin/users.html",
        context
    )
    
# =========================================================
# ADMIN BOOKING MANAGEMENT
# =========================================================

@login_required
def admin_bookings(request):

    if not request.user.is_staff:
        messages.error(
            request,
            "You do not have permission to access booking management."
        )
        return redirect("home")

    search = request.GET.get("search", "").strip()
    status = request.GET.get("status", "").strip()

    bookings = Booking.objects.select_related(
        "user",
        "room"
    ).order_by("-booking_date")

    if search:
        bookings = bookings.filter(
            Q(user__username__icontains=search)
            | Q(user__first_name__icontains=search)
            | Q(user__last_name__icontains=search)
            | Q(room__room_number__icontains=search)
        )

    if status:
        bookings = bookings.filter(status=status)

    total_bookings = Booking.objects.count()

    pending_bookings = Booking.objects.filter(
        status="Pending"
    ).count()

    confirmed_bookings = Booking.objects.filter(
        status="Confirmed"
    ).count()

    completed_bookings = Booking.objects.filter(
        status="Completed"
    ).count()

    cancelled_bookings = Booking.objects.filter(
        status="Cancelled"
    ).count()

    context = {
        "bookings": bookings,
        "total_bookings": total_bookings,
        "pending_bookings": pending_bookings,
        "confirmed_bookings": confirmed_bookings,
        "completed_bookings": completed_bookings,
        "cancelled_bookings": cancelled_bookings,
        "search": search,
        "selected_status": status,
    }

    return render(
        request,
        "admin/bookings.html",
        context
    )

# =========================================================
# ADMIN BOOKING DETAILS
# =========================================================

@login_required
def admin_booking_details(request, booking_id):

    if not request.user.is_staff:
        messages.error(
            request,
            "You do not have permission to view booking details."
        )
        return redirect("home")

    booking = get_object_or_404(
        Booking.objects.select_related(
            "user",
            "room"
        ),
        id=booking_id
    )

    payment = getattr(
        booking,
        "payment",
        None
    )

    return render(
        request,
        "admin/booking_details.html",
        {
            "booking": booking,
            "payment": payment,
        }
    )

# =========================================================
# ADMIN BOOKING STATUS UPDATE
# =========================================================

@login_required
def admin_booking_status(request, booking_id, action):

    if not request.user.is_staff:
        messages.error(
            request,
            "You do not have permission to manage bookings."
        )
        return redirect("home")

    print("ADMIN BOOKING STATUS CALLED:", booking_id, action, request.method)
    if request.method != "POST":
        return redirect("admin_bookings")

    booking = get_object_or_404(
        Booking,
        id=booking_id
    )

    current_status = booking.status

    # -----------------------------------------------------
    # CONFIRM BOOKING
    # -----------------------------------------------------

    if action == "confirm":

        if current_status != "Pending":
            messages.error(
                request,
                "Only pending bookings can be confirmed."
            )
            return redirect("admin_bookings")

        conflict = room_has_booking_conflict(
            booking.room,
            booking.check_in,
            booking.check_out,
            exclude_booking_id=booking.id
        )

        if conflict:
            messages.error(
                request,
                "This booking cannot be confirmed because the room is already booked for these dates."
            )
            return redirect("admin_bookings")

        booking.status = "Confirmed"

        booking.save(
            update_fields=["status"]
        )

        messages.success(
            request,
            f"Booking #{booking.id} has been confirmed successfully."
        )

    # -----------------------------------------------------
    # COMPLETE BOOKING
    # -----------------------------------------------------

    elif action == "complete":

        if current_status != "Confirmed":
            messages.error(
                request,
                "Only confirmed bookings can be marked as completed."
            )
            return redirect("admin_bookings")

        booking.status = "Completed"

        booking.save(
            update_fields=["status"]
        )

        messages.success(
            request,
            f"Booking #{booking.id} has been marked as completed."
        )

    # -----------------------------------------------------
    # CANCEL BOOKING
    # -----------------------------------------------------

    elif action == "cancel":

        if current_status not in ["Pending", "Confirmed"]:
            messages.error(
                request,
                "This booking cannot be cancelled."
            )
            return redirect("admin_bookings")

        booking.status = "Cancelled"

        booking.save(
            update_fields=["status"]
        )

        # -------------------------------------------------
        # SEND CANCELLATION EMAIL
        # -------------------------------------------------

        if notification_enabled("cancellation"):

            hotel = HotelSettings.objects.first()

            if hotel is None:
                hotel = HotelSettings.objects.create(
                    hotel_name="Luxury Grand Hotel"
                )

            try:

                email_html = render_to_string(
                    "emails/booking_cancellation.html",
                    {
                        "booking": booking,
                        "hotel_settings": hotel,
                    }
                )

                email = EmailMultiAlternatives(
                    subject=(
                        f"Booking Cancelled - "
                        f"{hotel.hotel_name} "
                        f"#{booking.id}"
                    ),
                    body=(
                        f"Your booking #{booking.id} "
                        f"has been cancelled."
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=[booking.user.email],
                )

                email.attach_alternative(
                    email_html,
                    "text/html"
                )

                email.send(
                    fail_silently=True
                )

            except Exception:
                pass

        messages.success(
            request,
            f"Booking #{booking.id} has been cancelled successfully."
        )

    # -----------------------------------------------------
    # INVALID ACTION
    # -----------------------------------------------------

    else:

        messages.error(
            request,
            "Invalid booking action."
        )

    return redirect("admin_bookings")


# =========================================================
# ADMIN ANALYTICS & REPORTS
# =========================================================

@login_required
def admin_reports(request):

    # -----------------------------------------------------
    # ADMIN PROTECTION
    # -----------------------------------------------------

    if not request.user.is_staff:
        messages.error(
            request,
            "You do not have permission to access reports."
        )
        return redirect("home")


    # =====================================================
    # BASIC TOTALS
    # =====================================================

    total_bookings = Booking.objects.count()

    confirmed_bookings = Booking.objects.filter(
        status="Confirmed"
    ).count()

    completed_bookings = Booking.objects.filter(
        status="Completed"
    ).count()

    cancelled_bookings = Booking.objects.filter(
        status="Cancelled"
    ).count()

    pending_bookings = Booking.objects.filter(
        status="Pending"
    ).count()

    total_users = User.objects.count()

    total_rooms = Room.objects.count()

    available_rooms = Room.objects.filter(
        available=True
    ).count()

    unavailable_rooms = Room.objects.filter(
        available=False
    ).count()


    # =====================================================
    # REVENUE
    # =====================================================

    total_revenue = Payment.objects.filter(
        status="Paid"
    ).aggregate(
        total=Sum("amount")
    )["total"] or 0


    # =====================================================
    # BOOKING PERFORMANCE
    # =====================================================

    if total_bookings > 0:

        completion_rate = round(
            (completed_bookings / total_bookings) * 100,
            1
        )

        cancellation_rate = round(
            (cancelled_bookings / total_bookings) * 100,
            1
        )

    else:

        completion_rate = 0
        cancellation_rate = 0


    # =====================================================
    # ROOM AVAILABILITY RATE
    # =====================================================

    if total_rooms > 0:

        availability_rate = round(
            (available_rooms / total_rooms) * 100,
            1
        )

    else:

        availability_rate = 0


    # =====================================================
    # MONTHLY BOOKING ANALYTICS
    # =====================================================

    monthly_bookings = (
        Booking.objects
        .annotate(
            month=TruncMonth("booking_date")
        )
        .values("month")
        .annotate(
            bookings=Count("id")
        )
        .order_by("month")
    )


    # =====================================================
    # MONTHLY REVENUE ANALYTICS
    # =====================================================

    monthly_revenue = (
        Payment.objects
        .filter(status="Paid")
        .annotate(
            month=TruncMonth("created_at")
        )
        .values("month")
        .annotate(
            revenue=Sum("amount")
        )
        .order_by("month")
    )


    # =====================================================
    # ROOM TYPE ANALYTICS
    # =====================================================

    room_type_analytics = (
        Booking.objects
        .values(
            "room__room_type"
        )
        .annotate(
            bookings=Count("id"),
            revenue=Sum("total_price")
        )
        .order_by("-bookings")
    )


    # =====================================================
    # BOOKING STATUS ANALYTICS
    # =====================================================

    booking_status_analytics = [
        {
            "name": "Confirmed",
            "count": confirmed_bookings,
        },
        {
            "name": "Completed",
            "count": completed_bookings,
        },
        {
            "name": "Pending",
            "count": pending_bookings,
        },
        {
            "name": "Cancelled",
            "count": cancelled_bookings,
        },
    ]


    # =====================================================
    # TOP ROOM TYPE
    # =====================================================

    top_room_type = (
        room_type_analytics[0]
        if room_type_analytics
        else None
    )


    # =====================================================
    # CONTEXT
    # =====================================================

    context = {

        # Basic statistics
        "total_bookings": total_bookings,
        "confirmed_bookings": confirmed_bookings,
        "completed_bookings": completed_bookings,
        "cancelled_bookings": cancelled_bookings,
        "pending_bookings": pending_bookings,

        # Users
        "total_users": total_users,

        # Rooms
        "total_rooms": total_rooms,
        "available_rooms": available_rooms,
        "unavailable_rooms": unavailable_rooms,

        # Revenue
        "total_revenue": total_revenue,

        # Performance
        "completion_rate": completion_rate,
        "cancellation_rate": cancellation_rate,
        "availability_rate": availability_rate,

        # Analytics
        "monthly_bookings": monthly_bookings,
        "monthly_revenue": monthly_revenue,
        "room_type_analytics": room_type_analytics,
        "booking_status_analytics": booking_status_analytics,

        # Top performer
        "top_room_type": top_room_type,
    }


    return render(
        request,
        "admin/reports.html",
        context
    )