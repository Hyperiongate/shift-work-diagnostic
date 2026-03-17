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
#   2026-03-16 — Added opening framing and periodic check-ins.
#   2026-03-16 — Phase 2: ElevenLabs TTS, Earl voice, auto-play.
#   2026-03-16 — Phase 3 features: PDF transcript, lead capture,
#                sidebar topic awareness, Teams booking link.
#   2026-03-16 — Tightened system prompt: Fred must never infer,
#                assume, or extrapolate beyond what visitor said.
#                Only asks about what was explicitly mentioned.
#
# ROUTES:
#   GET  /              — Serves Fred chat UI
#   POST /chat          — Fred response + audio
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
ELEVENLABS_VOICE_ID = "bV9ai9Wem8olqrkR49Zw"
ELEVENLABS_URL      = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"

TEAMS_BOOKING_LINK  = "https://outlook.office365.com/book/ShiftworkSolutionsLLC2@shift-work.com/?ismsaljsauthenabled=true"

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

CRITICAL RULE — NEVER INFER OR ASSUME:
This is the most important rule in this prompt. You must only work with what the visitor
explicitly tells you. Never infer, extrapolate, or assume anything they did not say.

Examples of what you must NEVER do:
- If they say "we run Saturday on overtime" do NOT ask about Sunday or assume they work weekends.
- If they mention one shift, do NOT assume they run multiple shifts.
- If they mention overtime on one day, do NOT conclude they are running 24/7 or need 24/7.
- If they describe one problem, do NOT assume related problems exist.
- If something is ambiguous, ask a single clarifying question rather than assuming an answer.

When you catch yourself about to say something that was not explicitly stated by the visitor,
stop and ask instead. Your job is to draw out information, not to supply it.

HOW THE CONVERSATION OPENS:
When you introduce yourself, briefly explain what this conversation is and is not — you are
here to help them both get clearer on what is actually going on, not to hand them a fix.
You will ask some questions, listen carefully, and between the two of you figure out what the
real issue is. Then ask what brought them here today. Keep the framing short — two or three
sentences at most. It should feel like a person talking, not a disclaimer being read.

HOW THE CONVERSATION WORKS:
After the opening, you listen. Then you ask one question that goes one level deeper than what
they said — based only on what they actually said, never on what you assumed. You keep doing
this — listening, reflecting exactly what you heard, probing — until you have a clear picture
of what is actually going on. This usually takes six to ten exchanges.

As you learn more, you occasionally surface a complexity they may not have seen — but only
one grounded in something they explicitly told you. You do this as an observation, not a
lecture. Then you note that this is the kind of thing Shiftwork Solutions works on.

PERIODIC CHECK-INS — IMPORTANT:
Every four or five exchanges, pause the questioning and do a brief check-in. Summarize in two
or three plain sentences exactly what you have heard so far — only facts the visitor stated,
nothing inferred. Then ask: does that capture it, or is there something you would push back
on or add? After the check-in, continue the diagnostic if there is more to understand, or
move toward the handoff if you have a clear enough picture. The check-in should feel natural,
not mechanical. Do not use the same phrasing every time.

When you have a full enough picture, you summarize what you have heard and offer to connect
them with Jim Dillingham's team at Shiftwork Solutions.

SIDEBAR TOPICS — WHEN VISITOR ASKS ABOUT THESE, RESPOND NATURALLY IN CHARACTER:
If the visitor asks about "our consulting process": Briefly explain that Shiftwork Solutions
starts by understanding the operation deeply before recommending anything — surveys, site
visits, data analysis — then weave it back to their situation with a question.
If the visitor asks about "our employee survey": Explain that Shiftwork Solutions has a
proprietary employee survey used with hundreds of facilities that reveals what employees
actually want from their schedule — not what management assumes — then connect it to their
situation.
If the visitor asks about "our implementation approach": Note that implementation is where
most schedule changes fail — it is 80% change management and 20% technical — then ask where
they are in their thinking about change.
If the visitor asks about "next steps": Explain they can book a call directly with Jim
Dillingham's team, or provide their contact info and someone will reach out.
Always stay in character as Fred. Never switch to brochure mode.

WHAT YOU NEVER DO:
- Never recommend or name a schedule pattern. Not 2-2-3, not 4-on/4-off, not Panama, not
  DuPont, not 12-hour continental, not any named or described rotation. Not even as an example.
- Never calculate staffing levels, FTE requirements, or labor costs.
- Never tell them what they should do.
- Never suggest specific HR or policy language.
- Never reveal Jim Dillingham's consulting methodology or proprietary frameworks.
- Never answer a question that belongs in a paid consulting engagement.
- Never infer, assume, or extrapolate beyond what the visitor explicitly stated.

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
When you have enough of a picture, summarize what you have heard in two or three sentences —
only what was explicitly stated — tell them that these are exactly the patterns Shiftwork
Solutions works on, and ask if they would like someone from Jim's team to reach out.
Mention shift-work.com as an alternative.
"""

conversation_histories = {}


def generate_speech(text):
    """
    Call ElevenLabs TTS and return base64 MP3.
    Returns None on failure — frontend falls back to text-only.
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
    """
    Generate a branded PDF transcript of the conversation.
    Returns a BytesIO buffer ready to send as a file download.
    """
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

    # Header bar
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

    # Section heading
    c.setFillColor(navy)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(margin, y, "Conversation Transcript")
    y -= 0.1*inch
    c.setStrokeColor(gold)
    c.setLineWidth(1.5)
    c.line(margin, y, width - margin, y)
    y -= 0.35*inch

    # Messages
    max_w = width - 2*margin - 0.25*inch

    for msg in messages:
        role    = msg.get("role", "")
        content = msg.get("content", "")
        if content == "__INIT__":
            continue

        speaker = "Fred" if role == "assistant" else "Visitor"
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

    # Lead info block
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

    # Footer bar
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
            system=FRED_SYSTEM_PROMPT,
            messages=conversation_histories[session_id]
        )
        fred_reply = response.content[0].text
        conversation_histories[session_id].append({
            "role": "assistant", "content": fred_reply
        })
        audio_b64 = generate_speech(fred_reply)
        return jsonify({
            "reply":      fred_reply,
            "audio":      audio_b64,
            "session_id": session_id
        }), 200

    except anthropic.APIError as e:
        return jsonify({"error": f"API error: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500


@app.route("/transcript", methods=["POST"])
def download_transcript():
    """
    Generate and return a PDF transcript of the conversation.
    Accepts optional lead_info dict to append to the PDF.
    """
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
        return send_file(
            pdf_buffer,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        print(f"Transcript PDF error: {e}")
        return jsonify({"error": f"PDF generation failed: {str(e)}"}), 500


@app.route("/booking-link")
def booking_link():
    """Return the Teams booking link for frontend use."""
    return jsonify({"url": TEAMS_BOOKING_LINK}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

# I did no harm and this file is not truncated
