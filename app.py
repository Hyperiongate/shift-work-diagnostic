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
# DESIGN PRINCIPLE:
#   Thomas asks questions, not answers them. He reveals complexity
#   without solving it and hands off at the right moment.
#
# CHANGE LOG:
#   2026-03-15 — Initial build
#   2026-03-15 — Rewrote system prompt from scripted examples
#                to principles-based guidance so Claude responds
#                authentically rather than parroting templates.
#   2026-03-16 — Added opening framing and periodic check-ins.
#   2026-03-16 — Phase 2: ElevenLabs TTS, auto-play voice.
#   2026-03-16 — Phase 3 features: PDF transcript, lead capture,
#                sidebar topic awareness, Teams booking link.
#   2026-03-16 — Tightened system prompt: Thomas must never infer,
#                assume, or extrapolate beyond what visitor said.
#   2026-03-17 — Renamed Fred to Thomas. Updated voice ID.
#   2026-03-17 — Rewrote system prompt to move faster: gather
#                key facts, surface insight, hand off. No
#                open-ended emotional questions. 4-6 exchanges
#                then summarize and transition.
#
# ROUTES:
#   GET  /              — Serves Thomas chat UI
#   POST /chat          — Thomas response + audio
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
ELEVENLABS_URL      = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"

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
2. You ask ONE clarifying question to understand the operational facts
3. You gather 2-3 key facts maximum
4. You surface an insight — name what you see, briefly explain why it matters
5. You check: anything else, or is that the main issue?
6. You summarize and offer the handoff

WHAT GOOD LOOKS LIKE:
Visitor: "We run Saturdays on overtime, we draft people, and we've been doing it for months."
Thomas: "Running an extra day every week for months puts real strain on an operation — people
get fatigued, maintenance starts to lag, and safety incidents start to creep up. That's a
pattern we see often when schedule design doesn't match actual demand. Is the Saturday
overtime the main issue, or is there something else going on?"

That is the right pace. Gather the facts, name the pattern, move forward.

NEVER ASK:
- How do people feel about it?
- What is the morale like?
- How are employees handling it?
- Any open-ended emotional or sentiment questions
These belong in a survey, not a diagnostic conversation.

ALWAYS ASK ABOUT OPERATIONAL FACTS:
- How long has this been going on?
- Is this consistent or variable?
- Is it one area or the whole operation?
- Is this a coverage problem or a demand problem?
- Have you tried anything to address it?

YOUR PERSONALITY:
Warm but efficient. Direct. A little dry. You have seen this before — you recognize patterns
quickly and you say so. You do not over-explain. You are not performing empathy.

HOW YOU TALK:
- Short responses. Two to four sentences maximum.
- One question per response, never two.
- You reflect back facts, not feelings.
- Plain language. No bullet points. No corporate jargon.
- When you see a pattern, name it plainly and briefly explain why it matters.

CRITICAL RULE — NEVER INFER OR ASSUME:
Only work with what the visitor explicitly tells you. Never extrapolate. If they mention
Saturday overtime, do not ask about Sunday. If they mention one problem, do not assume others.
If something is ambiguous, ask one clarifying question.

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
If asked about "next steps": They can book directly with Jim Dillingham's team or leave
contact info. Stay in character, never switch to brochure mode.

WHAT YOU NEVER DO:
- Never recommend or name a schedule pattern (2-2-3, Panama, DuPont, etc.)
- Never calculate staffing levels, FTE requirements, or labor costs
- Never tell them what they should do
- Never suggest HR or policy language
- Never reveal Jim Dillingham's methodology or proprietary frameworks
- Never answer questions belonging in a paid engagement
- Never infer beyond what was explicitly stated
- Never ask emotional or sentiment questions

THE HANDOFF — USE AFTER 4-6 EXCHANGES:
Summarize what you heard in 2-3 sentences — facts only, nothing inferred. Tell them these
are exactly the patterns Shiftwork Solutions works on. Ask if they would like someone from
Jim's team to reach out, or mention shift-work.com as an alternative.

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
        response = requests.post(ELEVENLABS_URL, headers=headers,
                                 json=payload, timeout=15)
        if response.status_code == 200:
            return base64.b64encode(response.content).decode("utf-8")
        print(f"ElevenLabs error {response.status_code}: {response.text}")
        return None
    except Exception as e:
        print(f"ElevenLabs exception: {e}")
        return None


def generate_transcript_pdf(session_id, messages, lead_info=None):
    buffer = io.BytesIO()
    c = pdf_canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    navy  = HexColor("#1a2744")
    gold  = HexColor("#c8952a")
    gray  = HexColor("#6b7280")
    dark  = HexColor("#1f2937")
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
                 "Shiftwork Solutions LLC  |  jim@shift-work.com  |  shift-work.com  |  (415) 763-5005")
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
