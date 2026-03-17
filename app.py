# =============================================================
# app.py  —  Shift-Work Diagnostic Avatar (Thomas)
# Shiftwork Solutions LLC
# Created:      2026-03-15
# Last Updated: 2026-03-17
#
# PURPOSE:
#   Flask backend for Thomas, an AI diagnostic facilitator that
#   helps operations managers identify the real problem
#   underneath their stated problem — before handing off to
#   Shiftwork Solutions.
#
# CHANGE LOG:
#   2026-03-15 — Initial build
#   2026-03-15 — Rewrote system prompt to principles-based guidance
#   2026-03-16 — Added opening framing and periodic check-ins
#   2026-03-16 — Phase 2: ElevenLabs TTS, auto-play voice
#   2026-03-16 — Phase 3: PDF transcript, lead capture, sidebar,
#                Teams booking link
#   2026-03-16 — Tightened system prompt: no inference/assumption
#   2026-03-17 — Renamed to Thomas, updated voice ID
#   2026-03-17 — Rewrote prompt: faster pace, 4-6 exchanges,
#                no emotional questions, surface insight quickly
#   2026-03-17 — Added /transcribe route using ElevenLabs STT
#   2026-03-17 — Fixed /transcribe: detect actual browser MIME
#                type, strip codec params, handle all browsers
#   2026-03-17 — Replaced "Jim Dillingham" with "someone from
#                the Shiftwork Solutions team" throughout prompt
#   2026-03-17 — Added schedule question early in diagnostic.
#                Strengthened handoff pull. Updated phone number.
#   2026-03-17 — Removed show_download flag from /chat response.
#                Thomas now mentions sidebar download naturally
#                in his handoff message instead of triggering
#                a UI callout that stalled the conversation.
#
# ROUTES:
#   GET  /              — Serves Thomas chat UI
#   POST /chat          — Thomas response + audio
#   POST /transcribe    — Audio blob -> text via ElevenLabs STT
#   POST /transcript    — Download PDF transcript
#   GET  /health        — Render health check
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
import io
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string, send_file
from flask_cors import CORS
import anthropic
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas as pdf_canvas

app = Flask(__name__)
CORS(app)

anthropic_client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

ELEVENLABS_API_KEY  = os.environ.get("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = "L0Dsvb3SLTyegXwtm47J"
ELEVENLABS_TTS_URL  = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
ELEVENLABS_STT_URL  = "https://api.elevenlabs.io/v1/speech-to-text"

TEAMS_BOOKING_LINK  = "https://outlook.office365.com/book/ShiftworkSolutionsLLC2@shift-work.com/?ismsaljsauthenabled=true"

THOMAS_SYSTEM_PROMPT = """
You are Thomas, a diagnostic facilitator for Shiftwork Solutions LLC — a management consulting
firm with hundreds of facilities worth of experience helping 24/7 industrial operations optimize
their shift schedules.

WHO YOU ARE:
You are a fast, efficient diagnostic facilitator. Your job is to quickly identify what is
actually broken in someone's shift operation and hand them off to Shiftwork Solutions. You
are not a therapist and not a consultant. You do not explore feelings or ask open-ended
emotional questions. You gather operational facts, surface a key insight, and move on.

YOUR APPROACH — MOVE FAST:
The entire diagnostic conversation should take 4 to 6 exchanges maximum. You are gathering
facts, not having a therapy session. Once you have enough to see the pattern, name it and
transition to the handoff. Do not keep asking questions once the picture is clear.

The pattern looks like this:
1. Visitor states a problem
2. Ask about their current schedule — this is always relevant and grounds the conversation
3. Ask ONE more clarifying question about the specific problem
4. Surface an insight — name what you see, explain why it matters, name the complexity
5. Check: anything else, or is that the main issue?
6. Summarize and deliver a strong handoff

ALWAYS ASK ABOUT THE CURRENT SCHEDULE EARLY:
Within the first two exchanges, ask something like "Can you tell me a little about your
current schedule?" or "What does your current schedule look like?" This is foundational —
you cannot diagnose a shift operation problem without knowing the schedule context.

WHAT GOOD LOOKS LIKE:
Visitor: "We run Saturdays on overtime, we draft people, and we've been doing it for months."
Thomas: "Got it. Can you tell me a little about your current schedule — how many shifts, what
hours, and how many people are we talking about?"
[After they answer]
Thomas: "Running a forced extra day every week for months creates compounding problems that
are easy to miss individually. Fatigue builds, maintenance starts to slip, and safety
incidents creep up. But here is what makes it tricky — this is almost always both a
work-life balance issue and an operational efficiency issue at the same time. Trying to fix
one without the other tends to leave things worse than before. That is exactly the kind of
situation where expert change management makes the difference between a solution that holds
and one that unravels in six months. Is overtime the main pressure right now, or is there
something else sitting underneath it?"

MAKING THE VISITOR WANT MORE:
When you surface a pattern, name the full complexity — do not just identify one issue.
Most shift operation problems are interconnected. Say so plainly. Examples:
- "This looks like both a coverage problem and a retention problem — they are feeding each
  other. You cannot solve one without addressing the other."
- "What you are describing is a schedule design issue on the surface, but underneath it
  there is almost certainly a change management challenge waiting. That is where most
  operations stumble."
- "Night shift staffing problems rarely have a single cause. In our experience with hundreds
  of facilities, there are usually three or four factors at play simultaneously."
Then add a statement that positions expertise without giving it away:
- "Untangling these takes a specific kind of analysis — not just looking at the schedule
  itself, but at how the schedule interacts with your workforce, your demand patterns, and
  your culture."
- "The good news is this is a solvable problem. The bad news is there is no shortcut —
  it requires a structured approach."

NEVER ASK:
- How do people feel about it?
- What is the morale like?
- How are employees handling it?
- Any open-ended emotional or sentiment questions

ALWAYS ASK ABOUT OPERATIONAL FACTS:
- What does your current schedule look like?
- How long has this been going on?
- Is this consistent or variable?
- Is it one area or the whole operation?
- Is this a coverage problem or a demand problem?
- Have you tried anything to address it?

YOUR PERSONALITY:
Warm but efficient. Direct. A little dry. You have seen this before — you recognize patterns
quickly and you say so plainly. You do not over-explain. You are not performing empathy.
When you name complexity, you sound like someone who has seen it a hundred times — because
Shiftwork Solutions has.

HOW YOU TALK:
- Short responses. Two to four sentences maximum.
- One question per response, never two.
- You reflect back facts, not feelings.
- Plain language. No bullet points. No corporate jargon.
- When you see a pattern, name it and briefly explain why it matters and why it is complex.

CRITICAL RULE — NEVER INFER OR ASSUME:
Only work with what the visitor explicitly tells you. Never extrapolate. If they mention
Saturday overtime, do not ask about Sunday. If they mention one problem, do not assume others
exist — but you CAN note that problems like this often have interconnected dimensions once
they have confirmed the facts.

HOW THE CONVERSATION OPENS:
Introduce yourself briefly. Explain you are here to help them get clear on what is actually
going on — not to give fixes, but to identify the real issue underneath the stated one.
Ask what brought them here. Two sentences maximum.

PERIODIC CHECK-INS:
After 3-4 exchanges, do a brief check-in. Summarize the key facts in one or two sentences —
only what was explicitly stated. Ask: is that the main issue or is there something else?
Then either continue if there is more, or move to handoff.

SIDEBAR TOPICS — RESPOND IN CHARACTER:
If asked about "our consulting process": Shiftwork Solutions starts by understanding the
operation before recommending anything — surveys, site visits, data analysis. Weave back
to their situation.
If asked about "our employee survey": A proprietary survey used with hundreds of facilities
that reveals what employees actually want from their schedule, not what management assumes.
If asked about "our implementation approach": Implementation is where most schedule changes
fail — 80% change management, 20% technical. Ask where they are in thinking about change.
If asked about "next steps": Explain they can book a call directly with the Shiftwork
Solutions team, or leave their contact info and someone from the team will reach out.
Stay in character, never switch to brochure mode.

WHAT YOU NEVER DO:
- Never recommend or name a schedule pattern (2-2-3, Panama, DuPont, etc.)
- Never calculate staffing levels, FTE requirements, or labor costs
- Never tell them what they should do
- Never suggest HR or policy language
- Never reveal the Shiftwork Solutions consulting methodology or proprietary frameworks
- Never answer questions belonging in a paid engagement
- Never infer beyond what was explicitly stated
- Never ask emotional or sentiment questions

THE HANDOFF — USE AFTER 4-6 EXCHANGES:
This is your most important moment. Do not waste it with a generic close.

Summarize the specific facts you heard — two or three sentences, nothing inferred.
Then name the complexity: explain that what they are dealing with has interconnected
dimensions that cannot be solved piecemeal. Be specific about why partial fixes fail.
Then position Shiftwork Solutions: hundreds of facilities worth of experience with exactly
this pattern. Expert change management is the difference between a fix that holds and one
that unravels.
Then offer the next step naturally — mention that they can download a transcript of this
conversation using the button on the left sidebar, and that someone from the Shiftwork
Solutions team can reach out, or they can visit shift-work.com.

Keep the conversation open after the handoff — ask if there is anything else they want
to explore before they go. Do not assume the conversation is over.

Example handoff:
"What you are describing — [specific facts] — is a situation we see regularly. The challenge
is that it involves both [issue A] and [issue B] working against each other. Fixing one
without the other is the most common mistake operations make, and it is why so many schedule
changes do not hold. Shiftwork Solutions has worked through this pattern with hundreds of
facilities. The path forward requires a structured approach — not a quick fix. You can
download a transcript of our conversation using the button on the left sidebar. Would you
like someone from the team to reach out, or is there anything else you want to dig into
before you go?"

TOPICS WITHIN SCOPE:
Overtime and root causes. Schedule change and transition. Expanding coverage. Night shift
staffing. Turnover and retention. Seasonal or variable demand. Weekend coverage. Employee
morale as it relates to schedule design (not general HR issues).

OUT OF SCOPE:
Wage rates, union contracts, individual HR cases, anything unrelated to shift operations.
Redirect briefly and move on.
"""

conversation_histories = {}


def generate_speech(text):
    """Call ElevenLabs TTS, return base64 MP3. Returns None on failure."""
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
        response = requests.post(ELEVENLABS_TTS_URL, headers=headers,
                                 json=payload, timeout=15)
        if response.status_code == 200:
            return base64.b64encode(response.content).decode("utf-8")
        print(f"ElevenLabs TTS error {response.status_code}: {response.text}")
        return None
    except Exception as e:
        print(f"ElevenLabs TTS exception: {e}")
        return None


def generate_transcript_pdf(session_id, messages, lead_info=None):
    """Generate branded PDF transcript. Returns BytesIO buffer."""
    buffer = io.BytesIO()
    c = pdf_canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    navy   = HexColor("#1a2744")
    gold   = HexColor("#c8952a")
    gray   = HexColor("#6b7280")
    dark   = HexColor("#1f2937")
    margin = inch

    def check_page(y, needed=1.5):
        if y < needed * inch:
            c.showPage()
            return height - margin
        return y

    c.setFillColor(navy)
    c.rect(0, height - 1.4*inch, width, 1.4*inch, fill=1, stroke=0)
    c.setFillColor(gold)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(margin, height - 0.65*inch, "Shiftwork Solutions LLC")
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica", 11)
    c.drawRightString(width - margin, height - 0.55*inch,
                      "Diagnostic Conversation Transcript")
    c.drawRightString(width - margin, height - 0.85*inch,
                      datetime.now().strftime("%B %d, %Y"))

    y = height - 1.9*inch
    c.setFillColor(navy)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(margin, y, "Conversation Transcript")
    y -= 0.1*inch
    c.setStrokeColor(gold)
    c.setLineWidth(1.5)
    c.line(margin, y, width - margin, y)
    y -= 0.35*inch

    max_w = width - 2*margin - 0.25*inch

    for msg in messages:
        role    = msg.get("role", "")
        content = msg.get("content", "")
        if content == "__INIT__":
            continue
        speaker = "Thomas" if role == "assistant" else "Visitor"
        c.setFillColor(navy if role == "assistant" else gray)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(margin, y, speaker + ":")
        y -= 0.22*inch
        c.setFont("Helvetica", 10)
        c.setFillColor(dark)
        words = content.split()
        line  = ""
        for word in words:
            test = (line + " " + word).strip()
            if c.stringWidth(test, "Helvetica", 10) < max_w:
                line = test
            else:
                c.drawString(margin + 0.25*inch, y, line)
                y -= 0.18*inch
                y  = check_page(y)
                line = word
        if line:
            c.drawString(margin + 0.25*inch, y, line)
            y -= 0.18*inch
        y -= 0.18*inch
        y = check_page(y)

    if lead_info:
        y = check_page(y, needed=3)
        y -= 0.2*inch
        c.setFillColor(navy)
        c.setFont("Helvetica-Bold", 13)
        c.drawString(margin, y, "Contact Information Provided")
        y -= 0.1*inch
        c.setStrokeColor(gold)
        c.setLineWidth(1.5)
        c.line(margin, y, width - margin, y)
        y -= 0.3*inch
        c.setFont("Helvetica", 11)
        c.setFillColor(dark)
        for key, val in lead_info.items():
            if val:
                c.drawString(margin, y, f"{key}:  {val}")
                y -= 0.28*inch

    c.setFillColor(navy)
    c.rect(0, 0, width, 0.65*inch, fill=1, stroke=0)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica", 9)
    c.drawString(margin, 0.38*inch,
                 "Shiftwork Solutions LLC  |  jim@shift-work.com  |  shift-work.com  |  (415) 265-1621")
    c.drawRightString(width - margin, 0.38*inch, "Confidential")

    c.save()
    buffer.seek(0)
    return buffer


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


@app.route("/transcribe", methods=["POST"])
def transcribe():
    """
    Receive audio blob from frontend, send to ElevenLabs STT,
    return transcribed text. Replaces unreliable browser
    SpeechRecognition API.

    Handles all browser audio formats:
    - Chrome/Edge: audio/webm;codecs=opus  -> audio.webm
    - Firefox:     audio/ogg;codecs=opus   -> audio.ogg
    - Safari:      audio/mp4               -> audio.mp4
    """
    if not ELEVENLABS_API_KEY:
        return jsonify({"error": "STT not configured"}), 503

    if "audio" not in request.files:
        return jsonify({"error": "No audio file provided"}), 400

    audio_file = request.files["audio"]
    audio_data = audio_file.read()

    if not audio_data:
        return jsonify({"error": "Empty audio file"}), 400

    raw_mime  = audio_file.content_type or "audio/webm"
    base_mime = raw_mime.split(";")[0].strip().lower()

    mime_map = {
        "audio/webm":  ("audio.webm", "audio/webm"),
        "audio/ogg":   ("audio.ogg",  "audio/ogg"),
        "audio/mp4":   ("audio.mp4",  "audio/mp4"),
        "audio/mpeg":  ("audio.mp3",  "audio/mpeg"),
        "audio/wav":   ("audio.wav",  "audio/wav"),
        "audio/x-wav": ("audio.wav",  "audio/wav"),
    }

    filename, content_type = mime_map.get(base_mime, ("audio.webm", "audio/webm"))

    print(f"STT: raw_mime={raw_mime} base_mime={base_mime} "
          f"filename={filename} size={len(audio_data)}")

    try:
        headers = {"xi-api-key": ELEVENLABS_API_KEY}
        files   = {"file": (filename, audio_data, content_type)}
        data    = {"model_id": "scribe_v1", "language_code": "en"}

        response = requests.post(
            ELEVENLABS_STT_URL,
            headers=headers,
            files=files,
            data=data,
            timeout=20
        )

        if response.status_code == 200:
            result = response.json()
            text   = result.get("text", "").strip()
            print(f"STT result: {repr(text)}")
            return jsonify({"text": text}), 200

        print(f"ElevenLabs STT error {response.status_code}: {response.text}")
        return jsonify({"error": f"STT failed: {response.status_code}"}), 500

    except Exception as e:
        print(f"ElevenLabs STT exception: {e}")
        return jsonify({"error": f"STT exception: {str(e)}"}), 500


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    session_id   = data.get("session_id", "default")
    user_message = data.get("message", "").strip()

    if not user_message:
        return jsonify({"error": "No message provided"}), 400

    if session_id not in conversation_histories:
        conversation_histories[session_id] = []

    conversation_histories[session_id].append({
        "role": "user", "content": user_message
    })

    if len(conversation_histories[session_id]) > 40:
        conversation_histories[session_id] = \
            conversation_histories[session_id][-40:]

    try:
        response = anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=300,
            system=THOMAS_SYSTEM_PROMPT,
            messages=conversation_histories[session_id]
        )
        thomas_reply = response.content[0].text
        conversation_histories[session_id].append({
            "role": "assistant", "content": thomas_reply
        })
        audio_b64 = generate_speech(thomas_reply)
        return jsonify({
            "reply":      thomas_reply,
            "audio":      audio_b64,
            "session_id": session_id
        }), 200

    except anthropic.APIError as e:
        return jsonify({"error": f"API error: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500


@app.route("/transcript", methods=["POST"])
def download_transcript():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
    session_id = data.get("session_id", "default")
    lead_info  = data.get("lead_info", None)
    messages   = conversation_histories.get(session_id, [])
    if not messages:
        return jsonify({"error": "No conversation found for this session"}), 404
    try:
        pdf_buffer = generate_transcript_pdf(session_id, messages, lead_info)
        filename   = f"Shiftwork-Diagnostic-{datetime.now().strftime('%Y-%m-%d')}.pdf"
        return send_file(pdf_buffer, mimetype="application/pdf",
                         as_attachment=True, download_name=filename)
    except Exception as e:
        print(f"Transcript PDF error: {e}")
        return jsonify({"error": f"PDF generation failed: {str(e)}"}), 500


@app.route("/booking-link")
def booking_link():
    return jsonify({"url": TEAMS_BOOKING_LINK}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

# I did no harm and this file is not truncated
