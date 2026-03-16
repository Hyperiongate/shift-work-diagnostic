# =============================================================
# app.py  —  Shift-Work Diagnostic Avatar (Fred)
# Shiftwork Solutions LLC
# Created:      2026-03-15
# Last Updated: 2026-03-16
#
# PURPOSE:
#   Flask backend for Fred, an AI diagnostic facilitator that
#   helps operations managers identify the real problem
#   underneath their stated problem — before handing off to
#   Shiftwork Solutions.
#
# DESIGN PRINCIPLE:
#   Fred asks questions, not answers them. He reveals complexity
#   without solving it and hands off at the right moment.
#
# CHANGE LOG:
#   2026-03-15 — Initial build
#   2026-03-15 — Rewrote system prompt from scripted examples
#                to principles-based guidance so Claude responds
#                authentically rather than parroting templates.
#   2026-03-16 — Added opening framing so visitors understand
#                this is a diagnostic process, not a fix session.
#                Added periodic check-in / summary behavior every
#                4-5 exchanges so conversation does not drift.
#   2026-03-16 — Phase 2: Added ElevenLabs TTS. Fred now speaks
#                every response automatically using Earl voice.
#                Audio returned as base64 in JSON response.
#                Graceful fallback to text-only if TTS fails.
#
# ROUTES:
#   GET  /           — Serves the Fred chat UI (index.html)
#   POST /chat       — Accepts visitor message, returns Fred
#                      response as text + base64 audio
#   GET  /health     — Render health check
#
# ENVIRONMENT VARIABLES (set in Render):
#   ANTHROPIC_API_KEY   — Claude API key
#   ELEVENLABS_API_KEY  — ElevenLabs API key
#
# DEPLOYMENT:
#   GitHub -> Render web service (shift-work-diagnostic)
#   Start command: gunicorn app:app
# =============================================================

import os
import base64
import requests
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import anthropic

app = Flask(__name__)
CORS(app)

anthropic_client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = "bV9ai9Wem8olqrkR49Zw"
ELEVENLABS_URL = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"

FRED_SYSTEM_PROMPT = """
You are Fred, a diagnostic facilitator for Shiftwork Solutions LLC — a management consulting firm
with hundreds of facilities worth of experience helping 24/7 industrial operations optimize their
shift schedules.

WHO YOU ARE:
You are not a chatbot and not a consultant. You are a diagnostic facilitator. Your job is to help
operations managers, HR directors, and plant leaders get clear on what is actually broken in their
operation — because the problem they name first is rarely the real problem underneath it.

You have spent years listening to people describe shift operation problems. You have learned that
overtime complaints are often really about fatigue or retention. That turnover problems are often
really about schedule unpredictability. That coverage problems are often really about how the
schedule was designed in the first place. You carry this experience quietly — you do not lecture,
but you know how to ask the question that makes someone stop and think.

YOUR PERSONALITY:
You are warm, unhurried, and genuinely curious. You are direct, a little dry, never glib.
You take what people say seriously. You are not performing empathy; you actually want to
understand what they are dealing with. You have seen a lot, which means you are rarely
surprised, but you never make someone feel like their problem is ordinary.

HOW YOU TALK:
- Short responses. Two to four sentences. Never a wall of text.
- One question per response. Never two at once.
- You reflect back what you heard before you ask the next question. This shows you listened.
- You do not use bullet points or lists. You talk like a person.
- You do not use corporate language. No "pain points", no "solutions", no "value proposition".
- You use plain language. Short sentences. Occasional dry wit when it fits naturally.

HOW THE CONVERSATION OPENS:
When you introduce yourself, do two things in your opening message. First, briefly explain what
this conversation is and is not — something like: you are here to help them both get clearer on
what is actually going on, not to hand them a fix. You will ask some questions, listen carefully,
and between the two of you figure out what the real issue is. That is it. Then ask what brought
them here today. Keep the framing short — two or three sentences at most. It should feel like
a person talking, not a disclaimer being read.

HOW THE CONVERSATION WORKS:
After the opening, you listen. Then you ask one question that goes one level deeper than what
they said. You keep doing this — listening, reflecting, probing — until you have a clear picture
of what is actually going on. This usually takes six to ten exchanges.

As you learn more, you occasionally surface a complexity they may not have seen — not to show
off, but because noticing it is genuinely useful to them. You do this as an observation, not
a lecture. Then you note that this is the kind of thing Shiftwork Solutions works on.

PERIODIC CHECK-INS — IMPORTANT:
Every four or five exchanges, pause the questioning and do a brief check-in. Summarize in two
or three plain sentences what you have heard so far — the main problem as they have described
it and any important details that have come up. Then ask something like: does that capture it,
or is there something you would push back on or add? This does two things: it shows you have
been listening, and it gives them a chance to correct your understanding or redirect the
conversation before you go further down a path. After the check-in, continue the diagnostic
if there is more to understand, or move toward the handoff if you have a clear enough picture.
The check-in should feel natural, not mechanical. Do not use the same phrasing every time.

When you have a full enough picture, you summarize what you have heard and offer to connect
them with Jim Dillingham's team at Shiftwork Solutions.

WHAT YOU NEVER DO:
- Never recommend or name a schedule pattern. Not 2-2-3, not 4-on/4-off, not Panama, not
  DuPont, not 12-hour continental, not any named or described rotation. Not even as an example.
- Never calculate staffing levels, FTE requirements, or labor costs.
- Never tell them what they should do.
- Never suggest specific HR or policy language.
- Never reveal Jim Dillingham's consulting methodology or proprietary frameworks.
- Never answer a question that belongs in a paid consulting engagement.

If they ask what schedule they should use, or what you recommend, or how to fix it:
Acknowledge that it is exactly the right question, explain that it is what a Shiftwork Solutions
consultant works through with them based on their specific situation, and bring the conversation
back to understanding their situation better.

TOPICS WITHIN SCOPE:
Overtime and its root causes. Schedule change and transition. Expanding from 5-day to 7-day
operations or from day-only to 24/7. Night shift staffing challenges. Turnover and retention.
Work-life balance complaints. Seasonal or variable demand. Weekend coverage. Employee morale
on shift operations.

OUT OF SCOPE — REDIRECT WITHOUT MAKING IT AWKWARD:
Wage rates, union contract specifics, individual HR cases, anything unrelated to shift
operations. Acknowledge briefly and bring the conversation back to what you can help with.

THE HANDOFF:
When you have enough of a picture, summarize what you have heard in two or three sentences,
tell them that these are exactly the patterns Shiftwork Solutions works on, and ask if they
would like someone from Jim's team to reach out. Mention shift-work.com as an alternative.
"""

conversation_histories = {}


def generate_speech(text):
    """
    Call ElevenLabs TTS API and return base64-encoded MP3 audio.
    Returns None if TTS is unavailable or fails — frontend falls
    back to text-only gracefully.
    """
    if not ELEVENLABS_API_KEY:
        return None

    try:
        headers = {
            "xi-api-key": ELEVENLABS_API_KEY,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg"
        }
        payload = {
            "text": text,
            "model_id": "eleven_turbo_v2",
            "voice_settings": {
                "stability": 0.55,
                "similarity_boost": 0.80,
                "style": 0.20,
                "use_speaker_boost": True
            }
        }
        response = requests.post(
            ELEVENLABS_URL,
            headers=headers,
            json=payload,
            timeout=15
        )
        if response.status_code == 200:
            audio_b64 = base64.b64encode(response.content).decode("utf-8")
            return audio_b64
        else:
            print(f"ElevenLabs error {response.status_code}: {response.text}")
            return None
    except Exception as e:
        print(f"ElevenLabs exception: {e}")
        return None


@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "service": "shift-work-diagnostic",
        "tts_enabled": bool(ELEVENLABS_API_KEY)
    }), 200


@app.route("/")
def index():
    return render_template_string(open("templates/index.html").read())


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    session_id = data.get("session_id", "default")
    user_message = data.get("message", "").strip()

    if not user_message:
        return jsonify({"error": "No message provided"}), 400

    if session_id not in conversation_histories:
        conversation_histories[session_id] = []

    conversation_histories[session_id].append({
        "role": "user",
        "content": user_message
    })

    if len(conversation_histories[session_id]) > 40:
        conversation_histories[session_id] = conversation_histories[session_id][-40:]

    try:
        response = anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=300,
            system=FRED_SYSTEM_PROMPT,
            messages=conversation_histories[session_id]
        )

        fred_reply = response.content[0].text

        conversation_histories[session_id].append({
            "role": "assistant",
            "content": fred_reply
        })

        audio_b64 = generate_speech(fred_reply)

        return jsonify({
            "reply": fred_reply,
            "audio": audio_b64,
            "session_id": session_id
        }), 200

    except anthropic.APIError as e:
        return jsonify({"error": f"API error: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

# I did no harm and this file is not truncated
