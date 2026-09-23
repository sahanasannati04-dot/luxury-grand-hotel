from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
from .memory import guest_memory

from .services import get_gemini_response


# ==========================================
# Part 39 - Step 7.1
# AI Conversation Memory Storage
# ==========================================

conversation_memory = {}


@csrf_exempt
def chatbot_api(request):

    if request.method == "POST":

        try:

            data = json.loads(request.body)

            user_message = data.get(
                "message",
                ""
            ).strip()

            if not user_message:

                return JsonResponse({
                    "reply": "Please enter a message."
                })

            # ==========================================
            # Part 39 - Step 7.2
            # Create/Get User Session ID
            # ==========================================

            session_id = request.session.session_key

            if not session_id:

                request.session.create()

                session_id = request.session.session_key

            # Create memory for new user
            if session_id not in conversation_memory:

                conversation_memory[session_id] = []
                
                # ==========================================
                # Part 39 - Step 7.5
                # Initialize Guest Memory
                # ==========================================

                if session_id not in guest_memory:

                    guest_memory[session_id] = {

                        "name": None,
  
                        "room_type": None,

                        "check_in": None,

                        "check_out": None,

                        "guests": 1

                    }

            # Store user message
            conversation_memory[session_id].append({

                "role": "user",

                "content": user_message

            })

            # ==========================================
            # Part 39 - Step 7.3
            # Send Conversation History To Gemini
            # ==========================================

            conversation_context = conversation_memory[session_id]

            reply = get_gemini_response(

                user_message,

                request.user,

                request,

                conversation_context

            )

            # Store AI reply
            conversation_memory[session_id].append({

                "role": "assistant",

                "content": reply

            })

            # ==========================================
            # Part 39 - Step 7.4
            # Keep Only Recent Conversation
            # ==========================================

            MAX_HISTORY = 20

            if len(conversation_memory[session_id]) > MAX_HISTORY:

                conversation_memory[session_id] = conversation_memory[session_id][-MAX_HISTORY:]

            return JsonResponse({

                "reply": reply

            })

        except Exception as e:

            return JsonResponse({

                "reply": f"ERROR: {str(e)}"

            })

    return JsonResponse({

        "reply": "Invalid request."

    })