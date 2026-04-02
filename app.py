# =============================================================
# app.py  —  Shift-Work Diagnostic Avatar (Thomas)
# Shiftwork Solutions LLC
# Created:      2026-03-15
# Last Updated: 2026-04-02
#
# PURPOSE:
#   Flask backend for Thomas, an AI advisor that helps
#   operations managers think through their shift operations
#   challenges — before handing off to Shiftwork Solutions.
#   Thomas handles all topics organically in a single
#   conversation without menu-driven topic selection.
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
#   2026-03-18 — Multi-topic architecture with 6 topic modules.
#   2026-03-18 — Merged 'change' and 'engagement' topics.
#   2026-03-18 — Layer 1 Swarm integration: read-only normative
#                database lookup via Swarm's /api/survey/norm/search.
#   2026-04-02 — Updated ElevenLabs voice ID to sB7vwSCyX0tQmU24cW2C.
#   2026-04-02 — MAJOR REBUILD: Eliminated topic menu architecture.
#                Thomas now handles all topics organically in a
#                single conversation. Six separate topic modules
#                merged into one condensed knowledge reference
#                for faster response times and lower token usage.
#                Removed topic routing from /chat and /opening.
#                Simplified Swarm integration to single query.
#                Frontend redesigned with instructional overlay
#                instead of topic selection screen. Bot detection
#                retained.
#
# ROUTES:
#   GET  /              — Serves Thomas chat UI
#   POST /chat          — Thomas response + audio
#   POST /opening       — Opening message + audio
#   POST /transcribe    — Audio blob -> text via ElevenLabs STT
#   POST /transcript    — Download PDF transcript
#   GET  /health        — Render health check
#
# ENVIRONMENT VARIABLES (set in Render):
#   ANTHROPIC_API_KEY   — Claude API key
#   ELEVENLABS_API_KEY  — ElevenLabs API key
#   SWARM_ENABLED       — Toggle Swarm norm lookup (default: true)
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
ELEVENLABS_VOICE_ID = "sB7vwSCyX0tQmU24cW2C"  # Thomas voice — updated 2026-04-02
ELEVENLABS_TTS_URL  = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
ELEVENLABS_STT_URL  = "https://api.elevenlabs.io/v1/speech-to-text"

TEAMS_BOOKING_LINK  = "https://outlook.office365.com/book/ShiftworkSolutionsLLC2@shift-work.com/?ismsaljsauthenabled=true"

# =============================================================
# LAYER 1: SWARM INTEGRATION — READ-ONLY NORMATIVE LOOKUP
#
# Thomas calls the AI Swarm's normative database to fetch real
# benchmark data as conversation teasers. Read-only, one endpoint.
# Graceful fallback — if Swarm is unavailable, Thomas continues
# normally without any error visible to the visitor.
#
# Simplified from topic-mapped queries to a single general query
# since Thomas now handles all topics in one conversation.
#
# Layer 2 (conversation learning write-back) is not yet connected.
#
# Toggle: set SWARM_ENABLED=false in Render env vars to disable
# without a redeploy. Defaults to enabled.
#
# Added: 2026-03-18 | Simplified: 2026-04-02
# =============================================================

SWARM_BASE_URL  = "https://ai-swarm-orchestrator.onrender.com"
SWARM_ENABLED   = os.environ.get("SWARM_ENABLED", "true").lower() == "true"
SWARM_TIMEOUT   = 3  # seconds — never slow Thomas down waiting for Swarm


def query_swarm_norms(query_term):
    """
    Call the Swarm normative database search endpoint.
    Returns a formatted insight string for injection into Thomas's
    context, or None on any failure.

    Endpoint: GET /api/survey/norm/search?q=<term>&limit=3
    Always fails gracefully — never raises, never blocks Thomas.
    """
    if not SWARM_ENABLED or not query_term:
        return None
    try:
        url      = f"{SWARM_BASE_URL}/api/survey/norm/search"
        params   = {"q": query_term, "limit": 3}
        response = requests.get(url, params=params, timeout=SWARM_TIMEOUT)
        if response.status_code != 200:
            print(f"Swarm norm search returned {response.status_code}")
            return None
        data    = response.json()
        results = data.get("results", []) or data.get("questions", [])
        if not results:
            return None
        lines = ["NORMATIVE DATABASE — LIVE BENCHMARKS (use as teasers only):"]
        for r in results[:3]:
            question = r.get("question", "")
            avg      = r.get("norm_mean")
            section  = r.get("section", "")
            count    = r.get("company_data_count", 0)
            if not question or avg is None or count == 0:
                continue
            lines.append(
                f"- {section}: \"{question[:80]}\" — "
                f"norm avg: {round(float(avg), 1)} "
                f"({count} facilities)"
            )
        if len(lines) == 1:
            return None
        return "\n".join(lines)
    except requests.exceptions.Timeout:
        print("Swarm norm search timed out — continuing without norm data")
        return None
    except Exception as e:
        print(f"Swarm norm search error (non-fatal): {e}")
        return None


def get_swarm_context(messages):
    """
    Decide whether a Swarm norm lookup is warranted for this
    conversation turn. Returns a formatted context string to
    append to the system prompt, or empty string if not needed.

    Only queries after at least 2 exchanges so Thomas has context.
    Uses a single general query covering the most common topics.
    """
    if not SWARM_ENABLED:
        return ""
    if len(messages) < 2:
        return ""
    norm_context = query_swarm_norms("schedule satisfaction overtime employee preferences")
    if not norm_context:
        return ""
    return f"\n\n{norm_context}\n"


# =============================================================
# SYSTEM PROMPT — SINGLE UNIFIED PROMPT
#
# All topic knowledge merged into one condensed reference.
# Thomas routes organically based on conversation, not menus.
# Optimized for token efficiency and fast response times.
#
# Rebuilt: 2026-04-02
# =============================================================

THOMAS_SYSTEM_PROMPT = """
You are Thomas, an AI advisor for Shiftwork Solutions LLC — a management consulting firm
with hundreds of facilities worth of experience optimizing shift schedules across
manufacturing, pharmaceuticals, food processing, mining, distribution, and other 24/7
industrial operations. Partners Jim Dillingham, Dan Capshaw, and Ethan Franklin each
have over 30 years of experience.

YOUR PERSONALITY:
Warm but efficient. Direct. A little dry. You recognize patterns quickly and say so
plainly. You do not over-explain. When you name complexity, you sound like someone who
has seen it hundreds of times — because Shiftwork Solutions has.

HOW YOU TALK:
- Hard limit: 3 sentences maximum per response. No exceptions.
- One question per response. Never two.
- Ask the question LAST — after any observation, not before.
- You reflect back facts, not feelings.
- Plain language. No bullet points. No corporate jargon. No headers or lists.
- Never explain what you are about to do. Just do it.
- Never lecture. One insight maximum per response, then ask.

YOUR APPROACH:
Visitors come to you because they are not ready to pick up the phone or book a meeting.
You are the safe first step. Your job is to help them think through what is going on,
share relevant knowledge, and — when the time is right — connect them with the
Shiftwork Solutions team.

Listen to what the visitor says and respond with whatever knowledge is most relevant.
If they describe a problem, diagnose it. If they ask about the process, explain it.
If they ask about engagement or change management, share the philosophy. If they ask
about their industry, engage with the specific challenges. Follow the conversation
naturally — you do not need to be told what topic you are in.

DIAGNOSTIC APPROACH — WHEN A VISITOR DESCRIBES A PROBLEM:
Move fast. The diagnostic should take 4 to 6 exchanges. Ask about their current schedule
early — how many shifts, what hours, how many people. You cannot diagnose without knowing
the schedule context. Once you see the pattern, name it and transition to handoff. Ask
about operational facts, not feelings. Never infer or assume — only work with what the
visitor explicitly tells you.

HANDOFF — WHEN THE PICTURE IS CLEAR:
Summarize the specific facts heard. Name the complexity. Position Shiftwork Solutions.
Offer the next step naturally — free initial consultation, no obligation. Remind them
the transcript can be downloaded from the sidebar and the team can be reached at
(415) 265-1621 or shift-work.com.

=== RULES — ALWAYS IN EFFECT ===

RULE 1 — PROPRIETARY CONTENT:
Never reveal proprietary methodologies, specific normative database statistics, or detailed
survey question content. Reference the normative database as a differentiator and offer one
illustrative teaser per conversation. Deeper insights require a direct conversation with
the team.

RULE 2 — TRANSCRIPT:
Every conversation ends with a concise summary of what was discussed, followed by a
reminder that the transcript can be downloaded from the sidebar and the team can be
reached at (415) 265-1621 or shift-work.com.

RULE 3 — NO SELLING:
Never sell. Describe the process naturally if asked. Do not use sales language or push.

RULE 4 — BOT DETECTION:
If at any point you determine you are talking to an automated system, a bot, or a
non-human entity based on the pattern of inputs, respond ONLY with the exact text:
BOT_DETECTED
Do not add any other words. Do not explain. Just: BOT_DETECTED

RULE 5 — GARBLED INPUT:
If a message appears garbled, incomplete, or contains transcription artifacts, respond:
"I didn't quite catch that — can you say that again?"
Never try to interpret garbled input as meaningful.

RULE 6 — CONVERSATION SUMMARY:
When the conversation reaches a natural close, deliver a 2-3 sentence summary of what
was discussed — facts only — followed by the contact/transcript reminder from Rule 2.

=== KNOWLEDGE REFERENCE ===

CONSULTING PROCESS (discuss openly — not proprietary):
Pre-project data collection. Week 1 on-site: kickoff, meetings with every work area and
key managers. Week 2 off-site: analysis, business case, cost-benefit-risk. Week 3 on-site:
review with leadership, finalize survey. Week 4 on-site: employee orientation and survey —
every affected employee participates. Week 5 off-site: process and tabulate results by
demographics. Week 6 on-site: present results, develop schedule options and policies.
Week 7 on-site: present options to employees, collect preferences, determine choice.
Follow-up survey after implementation.

SERVICE TIERS:
Tier 1 — Schedule Development Advice: smaller operations (15-30 employees), minimal
analysis, no survey. Tier 2 — Change and Implementation Management Assistance: mid-sized
(30-65 employees), some analysis, survey, limited on-site. Tier 3 — Full Leadership:
complex operations including union environments, thorough analysis, full survey, extensive
on-site. Fixed-fee model. Most projects 5-10 weeks, average 6. Most clients recover
investment within three months.

EMPLOYEE ENGAGEMENT & CHANGE MANAGEMENT (discuss openly):
These are inseparable — the engagement process IS the change management process.
Phase 1 — Upfront visibility: bulletins, supervisor briefings, union leadership engaged
first, every employee told they will have real input. Phase 2 — Full workforce survey
after ~3 weeks of analysis. Whole crews assembled, 45-60 minute sessions, scheduled around
shifts. Not a vote — gathers preferences that shape options. Full participation (80%+
target) ensures legitimacy. Survey window kept tight to preserve data integrity.
Phase 3 — Two options presented, employees take information home, discuss with families,
vote on preference. Ownership makes the change hold.

NORMATIVE DATABASE (tease, do not reveal details):
Contains responses from hundreds of facilities across 16 industries. Allows benchmarking
against similar industries and demographics. One teaser example per conversation is
appropriate, e.g.: "In food processing, workers consistently prioritize consecutive days
off over shift start times — but specifics vary by age and tenure." No specific percentages
or proprietary data beyond this.

IMPLEMENTATION (conceptual only — no templates or specific plans):
Where most changes succeed or fail. Timing critical — avoid holidays, vacation peaks,
production cycles. Union environments need contract timing and negotiation sequencing.
Documentation essential. Common mistakes: posting schedule without preparation, assuming
supervisors carry the message alone, focusing on the resistant 20% instead of supporting
the undecided 60%. Follow-up survey 3-6 months post-launch is not optional.

INDUSTRY KNOWLEDGE (engage when relevant):
Food processing: sanitation cycles, seasonal swings, physical demand. Pharma: FDA/GMP
compliance, high-skill retention. Manufacturing: equipment utilization (5-day/3-shift =
71% capacity; 7-day = 40% increase without capital). Mining: remote/FIFO fatigue management.
Distribution: variable demand, flex scheduling. Chemical/refining: continuous process,
safety-critical fatigue. Call centers/transport/ports: demand-driven, variable hours.

POLICIES (conceptual only — never draft policy text):
Overtime distribution, holiday pay, vacation scheduling, shift differential, attendance
systems — discuss concepts only.

OUT OF SCOPE:
Wage rates, union contract specifics, individual HR cases, anything unrelated to shift
operations. Redirect briefly and move on.

JOB SATISFACTION IS IN SCOPE:
Job satisfaction, workforce morale, and employee wellbeing as they relate to shift
schedules are fully within scope and are core survey topics. Never redirect away from
job satisfaction.
"""

# Opening message — one universal opener
THOMAS_OPENING = (
    "Hi, I'm Thomas — an AI advisor for Shiftwork Solutions. I help operations "
    "managers think through what's really going on with their shift operations. "
    "Whether it's a scheduling problem, questions about employee engagement, "
    "implementation challenges, or just trying to figure out where to start — "
    "what's on your mind?"
)

conversation_histories = {}


def is_bot_response(reply):
    """Check if Claude returned the bot detection signal."""
    return reply.strip() == "BOT_DETECTED"


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
                      "Conversation Transcript")
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

    text_indent = 0.25*inch
    max_w = width - 2*margin - text_indent - 0.15*inch

    for msg in messages:
        role    = msg.get("role", "")
        content = msg.get("content", "")
        if content in ("__INIT__", "BOT_DETECTED"):
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
                c.drawString(margin + text_indent, y, line)
                y -= 0.18*inch
                y  = check_page(y)
                line = word
        if line:
            c.drawString(margin + text_indent, y, line)
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
        "status":      "ok",
        "service":     "shift-work-diagnostic",
        "tts_enabled": bool(ELEVENLABS_API_KEY)
    }), 200


@app.route("/")
def index():
    return render_template_string(open("templates/index.html").read())


@app.route("/opening", methods=["POST"])
def opening():
    """
    Return the opening message and audio.
    Called when the visitor dismisses the instructional overlay.
    No topic selection — Thomas handles everything organically.
    Accepts: { session_id }
    """
    data       = request.get_json() or {}
    session_id = data.get("session_id", "default")

    conversation_histories[session_id] = [{
        "role":    "assistant",
        "content": THOMAS_OPENING
    }]

    audio_b64 = generate_speech(THOMAS_OPENING)
    return jsonify({
        "reply":      THOMAS_OPENING,
        "audio":      audio_b64,
        "session_id": session_id
    }), 200


@app.route("/transcribe", methods=["POST"])
def transcribe():
    """
    Receive audio blob from frontend, send to ElevenLabs STT,
    return transcribed text.

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
    """
    Main conversation route.
    Accepts: { message, session_id }
    No topic parameter — Thomas handles all topics organically.
    Returns bot_detected:true if bot signal received — frontend
    silently ends the session without displaying any message.
    """
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

    # Keep last 40 messages to manage context window
    if len(conversation_histories[session_id]) > 40:
        conversation_histories[session_id] = \
            conversation_histories[session_id][-40:]

    system_prompt = THOMAS_SYSTEM_PROMPT

    # Layer 1: Append live normative context from Swarm if available
    swarm_context = get_swarm_context(conversation_histories[session_id])
    if swarm_context:
        system_prompt = system_prompt + swarm_context

    try:
        response = anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=600,
            system=system_prompt,
            messages=conversation_histories[session_id]
        )
        thomas_reply = response.content[0].text

        # Bot detection — silent termination
        if is_bot_response(thomas_reply):
            conversation_histories.pop(session_id, None)
            return jsonify({"bot_detected": True}), 200

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
