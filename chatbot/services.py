from google import genai
from django.conf import settings
from hotel.models import Room
from django.db.models import Min
from hotel.models import Booking, Payment
from django.utils import timezone
import re
import json
from datetime import datetime, timedelta
from .memory import guest_memory
from chatbot.hotel_context import HOTEL_INFORMATION

client = genai.Client(api_key=settings.GEMINI_API_KEY)


def get_room_information():
    rooms = Room.objects.all()

    if not rooms.exists():
        return "No rooms are currently available in the database."

    data = []

    for room in rooms:
        status = "Available" if room.available else "Not Available"

        data.append(
            f"""
Room Number: {room.room_number}
Room Type: {room.room_type}
Price: ₹{room.price} per night
Description: {room.description}
Availability: {status}
"""
        )

    return "\n".join(data)

def available_rooms():
    rooms = Room.objects.filter(available=True)

    if not rooms.exists():
        return "Sorry, there are currently no rooms available."

    reply = "🏨 Available Rooms:\n\n"

    for room in rooms:
        reply += (
            f"• Room {room.room_number}\n"
            f"  Type: {room.room_type}\n"
            f"  Price: ₹{room.price}/night\n\n"
        )

    return reply


def cheapest_room():
    room = Room.objects.filter(available=True).order_by("price").first()

    if not room:
        return "Sorry, there are no available rooms."

    return (
        f"💰 Cheapest Available Room\n\n"
        f"Room Number: {room.room_number}\n"
        f"Type: {room.room_type}\n"
        f"Price: ₹{room.price}/night\n"
        f"Description: {room.description}"
    )


def room_by_number(number):
    room = Room.objects.filter(room_number=number).first()

    if not room:
        return None

    status = "Available" if room.available else "Not Available"

    return (
        f"🏨 Room {room.room_number}\n\n"
        f"Type: {room.room_type}\n"
        f"Price: ₹{room.price}/night\n"
        f"Availability: {status}\n"
        f"Description:\n{room.description}"
    )

def my_bookings(user):
    if user is None or not user.is_authenticated:
        return "Please log in to view your bookings."

    bookings = Booking.objects.filter(user=user).order_by("-check_in")

    if not bookings.exists():
        return "You don't have any bookings yet."

    reply = "📅 Your Bookings\n\n"

    for booking in bookings:
        reply += (
            f"🏨 Room {booking.room.room_number}\n"
            f"Type: {booking.room.room_type}\n"
            f"Check-in: {booking.check_in}\n"
            f"Check-out: {booking.check_out}\n"
            f"Guests: {booking.guests}\n"
            f"Status: {booking.status}\n"
            f"Total: ₹{booking.total_price}\n\n"
        )

    return reply



def next_booking(user):
    if user is None or not user.is_authenticated:
        return "Please log in first."

    booking = (
        Booking.objects
        .filter(user=user, check_in__gte=timezone.now().date())
        .order_by("check_in")
        .first()
    )

    if not booking:
        return "You don't have any upcoming bookings."

    return (
        f"📅 Your Next Booking\n\n"
        f"Room: {booking.room.room_number}\n"
        f"Type: {booking.room.room_type}\n"
        f"Check-in: {booking.check_in}\n"
        f"Check-out: {booking.check_out}\n"
        f"Guests: {booking.guests}\n"
        f"Status: {booking.status}"
    )

def payment_history(user):
    if user is None or not user.is_authenticated:
        return "Please log in to view your payment history."

    payments = (
        Payment.objects
        .filter(booking__user=user)
        .order_by("-payment_date")
    )

    if not payments.exists():
        return "You have not made any payments yet."

    reply = "💳 Your Payment History\n\n"

    total = 0

    for payment in payments:
        total += payment.amount

        reply += (
            f"Booking ID: {payment.booking.id}\n"
            f"Room: {payment.booking.room.room_number}\n"
            f"Amount: ₹{payment.amount}\n"
            f"Method: {payment.payment_method}\n"
            f"Date: {payment.payment_date.strftime('%d %b %Y %I:%M %p')}\n"
            f"Status: {'Paid' if payment.paid else 'Pending'}\n\n"
        )

    reply += f"💰 Total Paid: ₹{total}"

    return reply

def cancel_latest_booking(user):
    if not user.is_authenticated:
        return "Please log in first."

    booking = (
        Booking.objects
        .filter(user=user)
        .exclude(status="Cancelled")
        .order_by("-booking_date")
        .first()
    )

    if booking is None:
        return "You don't have any active bookings."

    booking.status = "Cancelled"
    booking.save()

    return (
        "✅ Booking cancelled successfully.\n\n"
        f"Booking ID: {booking.id}\n"
        f"Room: {booking.room.room_number}\n"
        f"Check-in: {booking.check_in}\n"
        f"Check-out: {booking.check_out}"
    )

def recommend_room(user_message):
    message = user_message.lower()

    rooms = Room.objects.filter(available=True)

    if not rooms.exists():
        return "Sorry, there are no rooms available at the moment."

    # Budget recommendation
    if any(word in message for word in [
        "budget", "cheap", "cheapest", "low price"
    ]):
        room = rooms.order_by("price").first()

    # Luxury recommendation
    elif any(word in message for word in [
        "luxury", "best", "premium", "suite"
    ]):
        room = rooms.order_by("-price").first()

    # Family recommendation
    elif "family" in message:
        room = (
            rooms.filter(room_type__in=["Suite", "Deluxe"])
            .order_by("-price")
            .first()
        )

        if room is None:
            room = rooms.order_by("-price").first()

    # Couples
    elif any(word in message for word in [
        "couple", "honeymoon"
    ]):
        room = (
            rooms.filter(room_type__in=["Deluxe", "Suite"])
            .order_by("-price")
            .first()
        )

        if room is None:
            room = rooms.first()

    else:
        room = rooms.order_by("-price").first()

    return (
        f"🏨 Recommended Room\n\n"
        f"Room Number: {room.room_number}\n"
        f"Type: {room.room_type}\n"
        f"Price: ₹{room.price}/night\n"
        f"Description: {room.description}"
    )

def extract_booking_details(message):
    message = message.lower()

    details = {
        "room_number": None,
        "room_type": None,
        "check_in": None,
        "check_out": None,
        "guests": 1,
        
    }

    # Room Number
    room_match = re.search(
        r"(?:room\s*)?(\d{2,4})",
       message
    )

    if room_match:
        details["room_number"] = room_match.group(1)

    room_types = ["single", "double", "deluxe", "suite"]

    for room_type in room_types:
        if room_type in message:
            details["room_type"] = room_type.title()
            
    guest_match = re.search(
        r"(\d+)\s*(guest|guests|adult|adults|people|person)",
        message
    )

    if guest_match:
        details["guests"] = int(guest_match.group(1))

    today = timezone.now().date()

    if "today" in message:
        details["check_in"] = today

    elif "tomorrow" in message:
        details["check_in"] = today + timedelta(days=1)

    night_match = re.search(r"(\d+)\s*night", message)

    if night_match and details["check_in"]:
        nights = int(night_match.group(1))
        details["check_out"] = details["check_in"] + timedelta(days=nights)

    return details

def is_room_available(room, check_in, check_out):

    # Room must be enabled/available
    if not room.available:
        return False

    overlapping = Booking.objects.filter(
        room=room,
        status__in=["Pending", "Confirmed"],
        check_in__lt=check_out,
        check_out__gt=check_in,
    ).exists()

    return not overlapping

def ai_extract_booking_details(message):
    prompt = f"""
You are an AI hotel booking parser.

Extract booking information from the user's message.

Return ONLY valid JSON.

JSON format:

{{
    "intent":"BOOK_ROOM",
    "room_number":null,
    "room_type":null,
    "check_in":null,
    "check_out":null,
    "guests":1,
    "preference":null
}}

Rules:

- room_number should be a string or null
- room_type should be one of:
  Single
  Deluxe
  Luxury
  Executive
  Family Suite
  Presidential Suite
- guests must be an integer

Return dates in YYYY-MM-DD format.

Understand expressions like:
- today
- tomorrow
- next week
- next monday
- this weekend
- after 3 days
- 30 july
- july 30
- 2026-08-05

If checkout is not specified,
leave it null.

preference may be:
- cheapest
- luxury
- premium
- family
- honeymoon
- business
- null

Return ONLY JSON.

User:

{message}
"""

    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=prompt,
    )

    text = response.text.strip()

    if text.startswith("```json"):
        text = text.replace("```json", "").replace("```", "").strip()

    return json.loads(text)

def ai_book_room(user, message):

    # ---------------------------------------------------------
    # EXTRACT BOOKING DETAILS
    # ---------------------------------------------------------

    details = ai_extract_booking_details(message)

    # Fallback parser if AI extraction fails
    if not details:
        details = extract_booking_details(message)

    # ---------------------------------------------------------
    # VALIDATE DATES
    # ---------------------------------------------------------

    check_in = details.get("check_in")
    check_out = details.get("check_out")

    # Convert string dates into Python date objects
    if isinstance(check_in, str):
        try:
            check_in = datetime.strptime(
                check_in,
                "%Y-%m-%d"
            ).date()
        except ValueError:
            try:
                check_in = datetime.strptime(
                    check_in,
                    "%d-%m-%Y"
                ).date()
            except ValueError:
                check_in = None

    if isinstance(check_out, str):
        try:
            check_out = datetime.strptime(
                check_out,
                "%Y-%m-%d"
            ).date()
        except ValueError:
            try:
                check_out = datetime.strptime(
                    check_out,
                    "%d-%m-%Y"
                ).date()
            except ValueError:
                check_out = None

    # Default checkout = one night
    if check_in and not check_out:
        check_out = check_in + timedelta(days=1)

    # ---------------------------------------------------------
    # ROOM TYPE NORMALIZATION
    # ---------------------------------------------------------

    room_type = details.get("room_type")

    if room_type:
        room_type_clean = room_type.strip().lower()

        room_type_map = {
            "single": "Single",
            "single room": "Single",

            "deluxe": "Deluxe",
            "deluxe room": "Deluxe",

            "luxury": "Luxury",
            "luxury room": "Luxury",

            "executive": "Executive",
            "executive room": "Executive",

            "family suite": "Family Suite",
            "family suite room": "Family Suite",

            "presidential suite": "Presidential Suite",
            "presidential suite room": "Presidential Suite",

            # Generic terms
            "suite": "Family Suite",
            "suite room": "Family Suite",
        }

        room_type = room_type_map.get(
            room_type_clean,
            room_type.strip()
        )

    # ---------------------------------------------------------
    # ROOM NUMBER BOOKING
    # ---------------------------------------------------------

    room = None

    if details.get("room_number"):

        try:
            room = Room.objects.get(
                room_number=details["room_number"]
            )
        except Room.DoesNotExist:
            return "Sorry, I couldn't find that room number."

    # ---------------------------------------------------------
    # ROOM TYPE BOOKING
    # ---------------------------------------------------------

    elif room_type:

        # First try exact match
        rooms = Room.objects.filter(
            room_type__iexact=room_type,
            available=True
        ).order_by("price")

        # If no exact match, try partial match
        if not rooms.exists():
            rooms = Room.objects.filter(
                room_type__icontains=room_type,
                available=True
            ).order_by("price")

        # Generic Suite → Family Suite / Presidential Suite
        if not rooms.exists() and room_type.lower() == "suite":
            rooms = Room.objects.filter(
                room_type__in=[
                    "Family Suite",
                    "Presidential Suite"
                ],
                available=True
            ).order_by("price")

        # Find first room without booking conflict
        for candidate in rooms:

            if check_in and check_out:

                if is_room_available(
                    candidate,
                    check_in,
                    check_out
                ):
                    room = candidate
                    break

            else:
                room = candidate
                break

    # ---------------------------------------------------------
    # NO ROOM FOUND
    # ---------------------------------------------------------

    if not room:

        return (
            "Sorry, no matching room is available right now.\n\n"
            "Available room types are:\n\n"
            "• Single\n"
            "• Deluxe\n"
            "• Luxury\n"
            "• Executive\n"
            "• Family Suite\n"
            "• Presidential Suite"
        )

    # ---------------------------------------------------------
    # CHECK-IN REQUIRED
    # ---------------------------------------------------------

    if not check_in:

        return (
            f"I found a {room.room_type} room "
            f"(Room {room.room_number}).\n\n"
            "When is your check-in?\n"
            "Please say today or tomorrow."
        )

    # ---------------------------------------------------------
    # CHECK-OUT DEFAULT
    # ---------------------------------------------------------

    if not check_out:
        check_out = check_in + timedelta(days=1)

    # ---------------------------------------------------------
    # GUESTS
    # ---------------------------------------------------------

    guests = details.get("guests") or 1

    # ---------------------------------------------------------
    # PRICE CALCULATION
    # ---------------------------------------------------------

    nights = (check_out - check_in).days

    if nights <= 0:
        nights = 1

    total_price = room.price * nights

    # ---------------------------------------------------------
    # CREATE BOOKING
    # ---------------------------------------------------------

    booking = Booking.objects.create(
        user=user,
        room=room,
        check_in=check_in,
        check_out=check_out,
        guests=guests,
        total_price=total_price,
        status="Confirmed",
    )

    return (
        "🎉 Booking confirmed successfully!\n\n"
        f"🏨 Luxury Grand Hotel\n"
        f"Room: {room.room_type}\n"
        f"Room Number: {room.room_number}\n"
        f"Check-in: {check_in.strftime('%d %B %Y')}\n"
        f"Check-out: {check_out.strftime('%d %B %Y')}\n"
        f"Guests: {guests}\n"
        f"Nights: {nights}\n"
        f"Total Price: ₹{total_price}\n\n"
        "Your booking has been confirmed."
    )

def get_booking_session(request):
    if request is None:
        return {}

    return request.session.get("booking_state", {})


def save_booking_session(request, state):
    if request is None:
        return

    request.session["booking_state"] = state
    request.session.modified = True


def clear_booking_session(request):
    if request is None:
        return

    if "booking_state" in request.session:
        del request.session["booking_state"]
        request.session.modified = True
        
def get_chat_history(request):
    if request is None:
        return []

    return request.session.get("chat_history", [])


def save_chat_history(request, history):
    if request is None:
        return

    request.session["chat_history"] = history
    request.session.modified = True


def add_chat_message(request, role, content):
    history = get_chat_history(request)

    history.append({
        "role": role,
        "content": content
    })

    history = history[-12:]

    save_chat_history(request, history)
        
def booking_conversation(user, message, request):
    
    state = get_booking_session(request)
    
    print("=" * 50)
    print("BOOKING SESSION")
    print(state)
    print("=" * 50)

    message = message.strip().lower()
    
    # Reset conversation on greetings
    if message in [
         "hi",
         "hello",
         "hey",
         "good morning",
         "good afternoon",
         "good evening"
    ]:
         clear_booking_session(request)
         state = {}
    else:
         state = get_booking_session(request)
         print(request.session.items())
     
     
     # Reset booking conversation
    if message in [
          "cancel",
          "cancel booking",
          "reset",
          "start over"
    ]:
           clear_booking_session(request)
           return "✅ Booking conversation has been reset. How can I help you today?"

    # ------------------------
    # STEP 1
    # ------------------------

    if not state:

        if "book" in message or "reserve" in message:

            state = {
                "step": "room_type"
            }

            save_booking_session(request, state)

            return (
                "🏨 I'd be happy to help.\n\n"
                "Which room type would you like?\n\n"
                "• Single\n"
                "• Deluxe\n"
                "• Luxury\n"
                "• Executive\n"
                "• Family Suite\n"
                "• Presidential Suite"
            )

        return None

    # ------------------------
    # STEP 2
    # ------------------------

    if state["step"] == "room_type":

        room_types = [
                "Single",
                "Deluxe",
                "Luxury",
                "Executive",
                "Family Suite",
                "Presidential Suite"
            ]

        for room in room_types:

            if room.lower() in message.lower():

                state["room_type"] = room
                state["step"] = "check_in"

                save_booking_session(request, state)

                return (
                    f"Great choice! {room} room.\n\n"
                    "When is your check-in?\n"
                    "(today or tomorrow)"
                )

        return (
            "Please choose one of these room types:\n\n"
            "• Single\n"
            "• Deluxe\n"
            "• Luxury\n"
            "• Executive\n"
            "• Family Suite\n"
            "• Presidential Suite"
        )

    # ------------------------
    # STEP 3
    # ------------------------

    if state["step"] == "check_in":

        today = timezone.now().date()

        if "today" in message:
            state["check_in"] = today.isoformat()

        elif "tomorrow" in message:
            state["check_in"] = (
            today + timedelta(days=1)
            ).isoformat()
            
        else:
            return "Please enter today or tomorrow."

        state["step"] = "guests"

        save_booking_session(request, state)

        return "How many guests?"

    # ------------------------
    # STEP 4
    # ------------------------

    if state["step"] == "guests":

        guest_match = re.search(r"\d+", message)

        if not guest_match:
            return "Please tell me the number of guests."

        state["guests"] = int(guest_match.group())

        state["step"] = "confirm"

        save_booking_session(request, state)

        return (
            "Please confirm your booking.\n\n"
            f"Room Type: {state['room_type']}\n"
            f"Check-in: {state['check_in']}\n"
            f"Guests: {state['guests']}\n\n"
            "Reply YES to confirm."
        )

    # ------------------------
    # STEP 5
    # ------------------------

    if state["step"] == "confirm":

        if message.lower() not in ["yes", "confirm"]:

            clear_booking_session(request)

            return "Booking cancelled."

        booking_date = timezone.datetime.strptime(
           state["check_in"],
           "%Y-%m-%d"
        ).date()

        day_word = (
           "today"
           if booking_date == timezone.now().date()
           else "tomorrow"
        )

        booking_message = (
            f"Book {state['room_type']} room "
            f"{day_word} for {state['guests']} guests"
        )
        
        clear_booking_session(request)

        return ai_book_room(
            user,
            booking_message
        )

def detect_intent(message):
    message = message.lower()

    # Available Rooms
    if any(word in message for word in [
        "available room",
        "available rooms",
        "rooms available",
        "show rooms",
        "room list",
        "what rooms are available",
        "which rooms are available",
        "free room",
        "free rooms"
    ]):
        return "AVAILABLE_ROOMS"

    # Cheapest Room
    if any(word in message for word in [
        "cheapest",
        "lowest",
        "lowest price",
        "budget",
        "cheap",
        "least expensive"
    ]):
        return "CHEAPEST_ROOM"

    # My Bookings
    if any(word in message for word in [
        "my booking",
        "my bookings",
        "booking history",
        "show booking",
        "show my bookings",
        "do i have any bookings",
        "reservation history"
    ]):
        return "MY_BOOKINGS"

    # Next Booking
    if any(word in message for word in [
        "next booking",
        "upcoming booking",
        "future booking",
        "my next booking",
        "upcoming stay"
    ]):
        return "NEXT_BOOKING"
    
    if any(word in message for word in [
        "payment",
        "payments",
        "payment history",
        "my payment",
        "my payments",
        "paid amount",
        "how much have i paid"
    ]):
        return "PAYMENTS"
    
    if any(word in message for word in [
        "cancel booking",
        "cancel my booking",
        "cancel my latest booking",
        "cancel reservation",
        "cancel my reservation"
    ]):
        return "CANCEL_BOOKING"
    
    if any(word in message for word in [
        "recommend",
        "suggest",
        "best room",
        "which room",
        "family",
        "luxury",
        "budget",
        "honeymoon"
   ]):
        return "RECOMMEND_ROOM"
    
    if any(word in message for word in [
        "book room",
        "reserve room",
        "book",
        "reserve",
        "make booking"
    ]):
        return "BOOK_ROOM"

    return "GENERAL"

def build_conversation_prompt(user_message, request):

    history = get_chat_history(request)

    conversation = ""

    for item in history:
        conversation += f"{item['role']}: {item['content']}\n"

    conversation += f"User: {user_message}"

    return conversation

def get_gemini_response(user_message, user, request, conversation_context=None):
    import re

    message = user_message.lower()
    intent = detect_intent(message)

    # ---------------------------------
    # Save User Message
    # ---------------------------------
    add_chat_message(
        request,
        "User",
        user_message
    )

    # ---------------------------------
    # Booking Conversation
    # ---------------------------------
    conversation = booking_conversation(
        user,
        user_message,
        request
    )

    if conversation:
        add_chat_message(
            request,
            "Assistant",
            conversation
        )
        return conversation

    # ---------------------------------
    # Intent Routing
    # ---------------------------------

    if intent == "AVAILABLE_ROOMS":
        reply = available_rooms()
        add_chat_message(request, "Assistant", reply)
        return reply

    if intent == "CHEAPEST_ROOM":
        reply = cheapest_room()
        add_chat_message(request, "Assistant", reply)
        return reply

    if intent == "MY_BOOKINGS":
        reply = my_bookings(user)
        add_chat_message(request, "Assistant", reply)
        return reply

    if intent == "NEXT_BOOKING":
        reply = next_booking(user)
        add_chat_message(request, "Assistant", reply)
        return reply

    if intent == "PAYMENTS":
        reply = payment_history(user)
        add_chat_message(request, "Assistant", reply)
        return reply

    if intent == "CANCEL_BOOKING":
        reply = cancel_latest_booking(user)
        add_chat_message(request, "Assistant", reply)
        return reply

    if intent == "RECOMMEND_ROOM":
        reply = recommend_room(user_message)
        add_chat_message(request, "Assistant", reply)
        return reply

    if intent == "BOOK_ROOM":
        reply = ai_book_room(user, user_message)
        add_chat_message(request, "Assistant", reply)
        return reply

    # ---------------------------------
    # Room Number Lookup
    # ---------------------------------

    match = re.search(
        r"room\s*(\d+)",
        user_message.lower()
    )

    if match:

        result = room_by_number(match.group(1))

        if result:
            add_chat_message(
                request,
                "Assistant",
                result
            )
            return result

    # ---------------------------------
    # General AI Conversation
    # ---------------------------------

    try:

        hotel_data = get_room_information()

        # ---------------------------------
        # Conversation Memory
        # ---------------------------------

        memory_history = ""

        if conversation_context:

            # Keep only recent messages
            recent_messages = conversation_context[-12:]

            for msg in recent_messages:

                role = (
                    "Guest"
                    if msg["role"] == "user"
                    else "Assistant"
                )

                memory_history += (
                    f"{role}: {msg['content']}\n"
                )

        # ---------------------------------
        # Prompt
        # ---------------------------------

        prompt = f"""
You are the official AI Concierge for this hotel.

Conversation Memory:
{memory_history}

Previous Conversation:
{build_conversation_prompt(user_message, request)}

Hotel Information:
{HOTEL_INFORMATION}

Hotel Room Database:
{hotel_data}

Rules:

- You are the hotel's professional AI Concierge.
- Speak naturally like ChatGPT.
- Be warm, friendly and professional.
- Remember previous conversation.
- Answer follow-up questions naturally.
- Use previous messages to understand guest references like:
  "that room", "this one", "cheaper one", "same room", "the previous option".
- Remember guest requirements mentioned earlier in the conversation.
- Do not ask for information that the guest already provided.
- Use ONLY hotel information and room database for hotel-related facts.
- Never invent room names.
- Never invent prices.
- Never invent amenities.
- Never invent hotel policies.
- Never invent unavailable rooms.
- Recommend rooms ONLY from the database.
- If information is unavailable, politely say so.
- If the guest asks a normal question unrelated to the hotel, answer naturally.
- Keep answers concise unless more details are requested.
- Use bullet points whenever helpful.
- If the guest greets you, greet them warmly.

Guest Question:
{user_message}
"""

        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt
        )

        # ---------------------------------
        # Safe Reply
        # ---------------------------------

        reply = ""

        if hasattr(response, "text") and response.text:
            reply = response.text.strip()

        if not reply:
            reply = (
                "I'm sorry, I couldn't generate a response right now."
            )

        # ---------------------------------
        # Save Assistant Reply
        # ---------------------------------

        add_chat_message(
            request,
            "Assistant",
            reply
        )

        return reply

    except Exception as e:

        import traceback
        traceback.print_exc()

        error_reply = f"🤖 ERROR: {e}"

        add_chat_message(
            request,
            "Assistant",
            error_reply
        )

        return error_reply