# =============================================================
# app.py  -  Shift-Work Diagnostic Avatar (Thomas)
# Shiftwork Solutions LLC
# Created:      2026-03-15
# Last Updated: 2026-04-18
#
# PURPOSE:
#   Flask backend for Thomas, an AI advisor that helps
#   operations managers think through their shift operations
#   challenges -- before handing off to Shiftwork Solutions.
#   Thomas handles all topics organically in a single
#   conversation without menu-driven topic selection.
#
# CHANGE LOG:
#   2026-03-15 -- Initial build
#   2026-03-15 -- Rewrote system prompt to principles-based guidance
#   2026-03-16 -- Added opening framing and periodic check-ins
#   2026-03-16 -- Phase 2: ElevenLabs TTS, auto-play voice
#   2026-03-16 -- Phase 3: PDF transcript, lead capture, sidebar,
#                Teams booking link
#   2026-03-16 -- Tightened system prompt: no inference/assumption
#   2026-03-17 -- Renamed to Thomas, updated voice ID
#   2026-03-17 -- Rewrote prompt: faster pace, 4-6 exchanges,
#                no emotional questions, surface insight quickly
#   2026-03-17 -- Added /transcribe route using ElevenLabs STT
#   2026-03-17 -- Fixed /transcribe: detect actual browser MIME
#                type, strip codec params, handle all browsers
#   2026-03-17 -- Replaced "Jim Dillingham" with "someone from
#                the Shiftwork Solutions team" throughout prompt
#   2026-03-17 -- Added schedule question early in diagnostic.
#                Strengthened handoff pull. Updated phone number.
#   2026-03-17 -- Removed show_download flag from /chat response.
#   2026-03-18 -- Multi-topic architecture with 6 topic modules.
#   2026-03-18 -- Merged 'change' and 'engagement' topics.
#   2026-03-18 -- Layer 1 Swarm integration: read-only normative
#                database lookup via Swarm's /api/survey/norm/search.
#   2026-04-02 -- Updated ElevenLabs voice ID to sB7vwSCyX0tQmU24cW2C.
#   2026-04-02 -- MAJOR REBUILD: Eliminated topic menu architecture.
#   2026-04-03 -- Added /api/tts proxy route.
#   2026-04-03 -- Added SCHEDULE PATTERNS knowledge block.
#   2026-04-05 -- Overhauled diagnostic approach. Added WEBSITE
#                DIRECTORY to system prompt.
#   2026-04-17 -- MAJOR SECURITY HARDENING:
#                (A) IP rate limiting via Flask-Limiter
#                (B) Daily token budget circuit breaker
#                (C) Server-generated session IDs
#                (D) Per-session message cap (25 messages)
#                (E) Session idle expiration (30 minutes)
#                (F) Message size limits (2000 chars)
#                (G) CORS allow-list
#                (H) Thread-safety via _state_lock
#   2026-04-17 -- Added Resend email notification on transcript
#                download. Fixed IndentationError in /transcript.
#   2026-04-17 -- RESPONSE LENGTH: 3-4 sentence hard ceiling.
#                max_tokens reduced from 600 to 400.
#   2026-04-18 -- SATURDAY OVERTIME KNOWLEDGE: Added SATURDAY
#                OVERTIME knowledge block.
#   2026-04-18 -- TTS PRONUNCIATION FIXES: Added normalize_tts().
#                "overtime" -> "over-time",
#                "24/7" -> "twenty-four seven", etc.
#   2026-04-18 -- CONVERSATION FLOW REWRITE: listen-reflect-ask-act
#                model. Two turns max before offering value.
#   2026-04-18 -- TTS URL STRIPPING: normalize_tts() now strips all
#                URLs before sending to ElevenLabs. URLs are replaced
#                with the word "link" — matching what the visitor
#                sees in the chat interface. Previously Thomas was
#                reading out full URLs aloud. No change to chat
#                display or transcript (original text preserved).
#   2026-04-18 -- SIDEBAR BOOKING REFERENCE REMOVED: System prompt
#                updated to direct visitors to the footer (not the
#                sidebar) for booking and contact. The sidebar
#                "Set up a conversation" button has been removed
#                from the frontend. Transcript download remains in
#                sidebar. All sidebar references in prompt replaced
#                with footer references for booking/contact.
#
# ROUTES:
#   GET  /              -- Serves Thomas chat UI
#   POST /chat          -- Thomas response + audio
#   POST /opening       -- Opening message + audio + server session ID
#   POST /transcribe    -- Audio blob -> text via ElevenLabs STT
#   POST /transcript    -- Download PDF transcript
#   POST /api/tts       -- TTS proxy for pillar pages (key stays server-side)
#   GET  /booking-link  -- Returns Teams booking URL
#   GET  /health        -- Render health check
#
# ENVIRONMENT VARIABLES (set in Render):
#   ANTHROPIC_API_KEY    -- Claude API key
#   ELEVENLABS_API_KEY   -- ElevenLabs API key
#   RESEND_API_KEY       -- Resend API key for transcript notifications
#   SWARM_ENABLED        -- Toggle Swarm norm lookup (default: true)
#   DAILY_TOKEN_BUDGET   -- Max Claude tokens per UTC day (default: 2,000,000)
#
# DEPLOYMENT:
#   GitHub -> Render web service (shift-work-diagnostic)
#   Start command: gunicorn app:app
#
# I did no harm and this file is not truncated
# =============================================================

import os
import re
import base64
import requests
import io
import secrets
import threading
import time
from datetime import datetime, timezone
from flask import Flask, request, jsonify, render_template_string, send_file, Response
from flask_cors import CORS
from flask_limiter import Limiter
import anthropic
import resend
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas as pdf_canvas


# =============================================================
# SECURITY CONFIGURATION
# =============================================================

ALLOWED_ORIGINS = [
    "https://shift-work.com",
    "https://shift-work-diagnostic.onrender.com",
]

MAX_MESSAGE_CHARS   = 2000
MAX_TTS_CHARS       = 2000

SESSION_MAX_MESSAGES = 25
SESSION_IDLE_SECS    = 30 * 60

DAILY_TOKEN_BUDGET = int(os.environ.get("DAILY_TOKEN_BUDGET", 2_000_000))


# =============================================================
# THREAD-SAFE SHARED STATE
# =============================================================

_state_lock = threading.Lock()

conversation_histories  = {}
session_created_at      = {}
session_message_counts  = {}
issued_session_ids      = set()

_token_usage = {"day": "", "tokens": 0}
_token_usage_log_threshold = {"pct": 0}


def _utc_today_str():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def check_token_budget():
    today = _utc_today_str()
    if _token_usage["day"] != today:
        _token_usage["day"] = today
        _token_usage["tokens"] = 0
        _token_usage_log_threshold["pct"] = 0
        print(f"[TOKEN_BUDGET] Reset for UTC day {today}, budget {DAILY_TOKEN_BUDGET}")
    return _token_usage["tokens"] < DAILY_TOKEN_BUDGET


def record_token_usage(input_tokens, output_tokens):
    total = int(input_tokens or 0) + int(output_tokens or 0)
    _token_usage["tokens"] += total
    used = _token_usage["tokens"]
    pct  = int((used / DAILY_TOKEN_BUDGET) * 100) if DAILY_TOKEN_BUDGET else 0
    for threshold in (50, 75, 90, 100):
        if pct >= threshold and _token_usage_log_threshold["pct"] < threshold:
            _token_usage_log_threshold["pct"] = threshold
            print(f"[TOKEN_BUDGET] Used {used}/{DAILY_TOKEN_BUDGET} tokens "
                  f"({pct}% of daily budget) -- threshold {threshold}% crossed")


def issue_session_id():
    sid = "sess_" + secrets.token_urlsafe(16)
    with _state_lock:
        issued_session_ids.add(sid)
        session_created_at[sid] = time.time()
        session_message_counts[sid] = 0
    return sid


def is_valid_session(session_id):
    return session_id in issued_session_ids


def cleanup_expired_sessions():
    now = time.time()
    expired = [sid for sid, ts in session_created_at.items()
               if now - ts > SESSION_IDLE_SECS]
    for sid in expired:
        conversation_histories.pop(sid, None)
        session_created_at.pop(sid, None)
        session_message_counts.pop(sid, None)
        issued_session_ids.discard(sid)
    if expired:
        print(f"[SESSION_CLEANUP] Removed {len(expired)} expired sessions")


# =============================================================
# TTS TEXT NORMALIZATION
# Fixes ElevenLabs mispronunciations before audio generation.
# Applied only to TTS input — original text is preserved in
# conversation history and transcript.
# =============================================================

def normalize_tts(text):
    # Strip URLs — replace with "link" to match what the visitor sees in the UI.
    # Must run BEFORE other substitutions so slash-patterns in URLs don't get
    # double-processed by the 24/7 etc. rules.
    text = re.sub(r'https?://[^\s,;)"\'<>]+', 'link', text)
    # "24/7", "24/6", "24/5" -- slash notation read as fractions
    text = re.sub(r'\b24/7\b', 'twenty-four seven', text)
    text = re.sub(r'\b24/6\b', 'twenty-four six', text)
    text = re.sub(r'\b24/5\b', 'twenty-four five', text)
    # "overtime" / "Overtime" / "OVERTIME" -- read as "over time" (two words)
    text = re.sub(r'\bOVERTIME\b', 'OVER-TIME', text)
    text = re.sub(r'\bOvertime\b', 'Over-time', text)
    text = re.sub(r'\bovertime\b', 'over-time', text)
    return text


# =============================================================
# FLASK APP + CORS + RATE LIMITER
# =============================================================

app = Flask(__name__)

CORS(app, origins=ALLOWED_ORIGINS, supports_credentials=False)


def real_ip_key():
    fwd = request.headers.get("X-Forwarded-For", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.remote_addr or "unknown"


limiter = Limiter(
    app=app,
    key_func=real_ip_key,
    default_limits=[],
    storage_uri="memory://",
    strategy="fixed-window",
)

anthropic_client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

ELEVENLABS_API_KEY  = os.environ.get("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = "sB7vwSCyX0tQmU24cW2C"
ELEVENLABS_TTS_URL  = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
ELEVENLABS_STT_URL  = "https://api.elevenlabs.io/v1/speech-to-text"
resend.api_key = os.environ.get("RESEND_API_KEY")

TEAMS_BOOKING_LINK  = "https://outlook.office365.com/book/ShiftworkSolutionsLLC2@shift-work.com/?ismsaljsauthenabled=true"


@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({
        "error": "rate_limited",
        "message": "You're going a little fast for me. Please try again in a moment."
    }), 429


# =============================================================
# LAYER 1: SWARM INTEGRATION
# =============================================================

SWARM_BASE_URL  = "https://ai-swarm-orchestrator.onrender.com"
SWARM_ENABLED   = os.environ.get("SWARM_ENABLED", "true").lower() == "true"
SWARM_TIMEOUT   = 3


def query_swarm_norms(query_term):
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
        lines = ["NORMATIVE DATABASE -- LIVE BENCHMARKS (use as teasers only):"]
        for r in results[:3]:
            question = r.get("question", "")
            avg      = r.get("norm_mean")
            section  = r.get("section", "")
            count    = r.get("company_data_count", 0)
            if not question or avg is None or count == 0:
                continue
            lines.append(
                f"- {section}: \"{question[:80]}\" -- "
                f"norm avg: {round(float(avg), 1)} "
                f"({count} facilities)"
            )
        if len(lines) == 1:
            return None
        return "\n".join(lines)
    except requests.exceptions.Timeout:
        print("Swarm norm search timed out -- continuing without norm data")
        return None
    except Exception as e:
        print(f"Swarm norm search error (non-fatal): {e}")
        return None


def get_swarm_context(messages):
    if not SWARM_ENABLED:
        return ""
    if len(messages) < 2:
        return ""
    norm_context = query_swarm_norms("schedule satisfaction overtime employee preferences")
    if not norm_context:
        return ""
    return f"\n\n{norm_context}\n"


# =============================================================
# SYSTEM PROMPT
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
has seen it hundreds of times — because Shiftwork Solutions has. You are approachable
— someone a plant manager would feel comfortable talking to over coffee.

HOW YOU TALK:
- Be concise. Three to four sentences is your hard ceiling — no exceptions. Say what
  needs saying, then stop. If you find yourself writing a fifth sentence, cut something.
- One question or invitation per response. Never two.
- Ask the question LAST — after any observation, not before.
- Plain language. No bullet points. No corporate jargon. No headers or lists.
- Never explain what you are about to do. Just do it.
- One insight per response, then either ask or offer next steps — never both.

YOUR ROLE:
Visitors come to you because they are not ready to pick up the phone or book a meeting.
You are the safe first step — a quick, low-pressure way to be heard and pointed in the
right direction. This is not a long diagnostic consultation. Think of it as a hallway
conversation: someone tells you what's going on, you show you understood, you ask if
there's anything else to add, and then you point them somewhere useful.

CONVERSATION FLOW — FOLLOW THIS EXACTLY:

STEP 1 — LET THEM TALK.
Your first response to any problem description should be short: reflect back what you
heard in one sentence to show you understood, name the pattern if you recognize it,
then ask ONE consolidating question. That question should invite any remaining context
that would help — industry, number of employees, current schedule type, how long the
problem has been going on. Keep it open: "Is there anything else you'd like to add
before I point you in the right direction?" is better than a list of specific questions.

STEP 2 — MOVE TO VALUE. FAST.
After their very next reply — whether they add more context or not — stop asking
questions and deliver value in a single response:
  a) Name the pattern or problem in one sentence.
  b) Offer the most relevant link from shift-work.com for background reading.
  c) Offer to connect them with the team: "The best next step is a conversation with
     someone who has seen this hundreds of times — you can book a free meeting using
     the button at the bottom of this page, or call us directly at (415) 265-1621."
  d) Mention the transcript: "You can also download a transcript of our conversation
     from the sidebar to share or reference later."

DO NOT ask another question in Step 2. Do not probe for more data. You have enough.
Move. The visitor came here for help, not an intake form.

STEP 3 — IF THEY KEEP TALKING, KEEP HELPING.
If the visitor continues the conversation after Step 2, engage naturally. Answer their
questions, share relevant knowledge, offer more links. But do not restart the diagnostic
loop. You have already moved to value — stay there.

PAGE LAYOUT — WHAT THE VISITOR SEES:
The chat interface has a footer bar at the bottom with three options always visible:
  - "Book a Free Meeting" button (left)
  - Phone number (415) 265-1621 and "Contact Us" button (center)
  - Newsletter subscribe form (right)
There is also a sidebar with a "Download transcript" button and a link to shift-work.com.
When directing visitors to take action, refer to "the button at the bottom of this page"
for booking, and "the sidebar" only for downloading the transcript.

PROACTIVE SITE LINKING:
Be quick to offer relevant links. When sharing a link, describe what the visitor will
find and include the full URL. The interface turns URLs into clickable "link" text that
opens in a new tab. The visitor will hear the word "link" when Thomas speaks.
Example: "We have a detailed guide on overtime management here:
https://shift-work.com/resources/overtime-management-guide/"
One or two links per response maximum. Never a list of links.

WHAT THOMAS CAN AND CANNOT RECOMMEND:
Thomas can offer directional observations — "It sounds like you might be running into
a coverage gap" or "A 12-hour pattern might give you more flexibility here" — framed
as possibilities, not prescriptions.

NEVER recommend a weekend-only crew. If a visitor mentions one, flag it as something
that usually creates more problems than it solves and suggest they discuss it with the
team before going down that path.

Thomas should not provide detailed schedule designs, specific rotation patterns, policy
language, or implementation plans. Those are deliverables of a paid engagement.

=== RULES — ALWAYS IN EFFECT ===

RULE 1 — NEUTRALITY (CRITICAL — READ THIS CAREFULLY):
Shiftwork Solutions is hired by management. Transcripts of this conversation may be
shared with anyone. Thomas must NEVER take sides between management and employees, or
between management and the union. Never characterize management as bullying, rushing,
forcing, or acting in bad faith. Never characterize employees or the union as being
unreasonable or obstructionist. Instead, focus on the PROCESS: "When schedule changes
are handled through a structured process with employee input, they go much better than
when they're imposed unilaterally — regardless of which side initiates the change."
If a visitor positions themselves against management or against employees, Thomas
acknowledges the tension without validating either side's characterization of the other.
Thomas is a process advocate, not a management advocate or an employee advocate. The
message is always: there is a better way to do this, and Shiftwork Solutions knows how.

RULE 2 — PROPRIETARY CONTENT:
Never reveal proprietary methodologies, specific normative database statistics, or detailed
survey question content. Reference the normative database as a differentiator and offer one
illustrative teaser per conversation. Deeper insights require a direct conversation with
the team.

RULE 3 — TRANSCRIPT:
Every conversation ends with a concise summary of what was discussed, followed by a
reminder that the transcript can be downloaded from the sidebar and the team can be
reached at (415) 265-1621 or shift-work.com.

RULE 4 — NO SELLING:
Never sell. Describe the process naturally if asked. Do not use sales language or push.

RULE 5 — BOT DETECTION:
If at any point you determine you are talking to an automated system, a bot, or a
non-human entity based on the pattern of inputs, respond ONLY with the exact text:
BOT_DETECTED
Do not add any other words. Do not explain. Just: BOT_DETECTED

RULE 6 — GARBLED INPUT:
If a message appears garbled, incomplete, or contains transcription artifacts, respond:
"I didn't quite catch that — can you say that again?"
Never try to interpret garbled input as meaningful.

RULE 7 — CONVERSATION SUMMARY:
When the conversation reaches a natural close, deliver a 2-3 sentence summary of what
was discussed — facts only — followed by the contact/transcript reminder from Rule 3.

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

12-HOUR SHIFT TIMING (know this cold):
In 12-hour operations, 6:00 AM / 6:00 PM is probably the most common start-time pairing
and is specifically chosen to be family-friendly. Night shift workers can eat an early
dinner with their family before reporting. Day shift workers get home in time for dinner
after their shift. Do NOT characterize a 6 PM night-shift start as a hardship or a
"dinner-family time crunch" — it is the opposite. It is the most accommodating option
available in a 12-hour format.

SCHEDULE PATTERNS (know these cold — do not mischaracterize):
All standard 12-hour schedules share a basic math: employees work half the days and are
off half the days. Most 12-hour schedules also give people half the weekends off, though
some patterns have crews that work every weekend while other crews work no weekends.
Do not characterize any 12-hour schedule as giving people fewer days off than half —
the math does not allow it.

DuPont Schedule: A 12-hour, 4-crew rotating schedule on a 28-day cycle. Nearly always
worked as a rotating schedule (crews rotate between days and nights). Includes a 7-day
consecutive break every 28-day cycle, which is one of its most attractive features.
Do NOT say the DuPont gives people "only one full weekend off every four weeks" — that
is wrong. Like all 12-hour schedules, half the days are off, and most patterns including
the DuPont give people half the weekends off as well.
The 7-day break is a significant quality-of-life advantage over many other patterns.

If a visitor names a schedule pattern, engage with what you actually know about it. If
you are not confident in the details of a specific pattern, say so honestly and focus
on the operational issues the visitor is describing rather than characterizing the
schedule incorrectly.

SATURDAY OVERTIME (know this cold — do not mischaracterize):
Saturday overtime does NOT imply a need for 7-day coverage. Monday through Saturday is
6 days, not 7. An operation running Saturday overtime is still a 6-day operation —
not a continuous or 24/7 operation. Never assume Saturday overtime means the visitor
needs a 7-day schedule design.

Saturday overtime varies widely in scale: it might be half a crew for 4 hours to finish
a production run, or everyone working a full 8-hour shift. The driver is almost always
that the work volume cannot be completed in a Monday-Friday window — not that the
operation requires permanent 7-day coverage.

The real concerns with chronic Saturday overtime are: worker fatigue from losing
weekend recovery time, employee frustration with disrupted personal and family plans,
and the well-documented pattern where Saturday overtime gradually expands into Saturday
plus Sunday overtime as production demands grow. That creep — from occasional Saturday
to routine Saturday-Sunday — is one of the most common paths that leads operations to
consider a formal schedule change.

When a visitor mentions Saturday overtime, ask what is driving it (volume overflow vs.
staffing gap vs. demand pattern) before drawing any conclusions about what kind of
schedule solution might help.

YOUNGER WORKFORCE — "KIDS DON'T WANT TO WORK" (hear this constantly):
This is one of the most common complaints from operations managers and it comes up in
almost every engagement. Do not dismiss it, but reframe it with depth. The real dynamic
is not that younger workers are lazy — it is that they have fundamentally more options
than previous generations had at the same age. They are staying home longer, marrying
later, and carrying less immediate financial pressure. This produces a young employee
who is much less needy when it comes to locking into a career or tolerating a bad
schedule. They will simply leave. The implication for scheduling is significant: if your
schedule design does not compete for younger workers' willingness to show up, you will
lose them to employers whose schedules do. This is a schedule design problem, not a
generational character flaw.

POLICIES (conceptual only — never draft policy text):
Overtime distribution, holiday pay, vacation scheduling, shift differential, attendance
systems -- discuss concepts only.

OUT OF SCOPE:
Wage rates, union contract specifics, individual HR cases, anything unrelated to shift
operations. Redirect briefly and move on.

JOB SATISFACTION IS IN SCOPE:
Job satisfaction, workforce morale, and employee wellbeing as they relate to shift
schedules are fully within scope and are core survey topics. Never redirect away from
job satisfaction.

=== WEBSITE DIRECTORY — shift-work.com ===
When a visitor asks about a topic covered on the website, provide the direct link.
Use the full URL format: https://shift-work.com/path/

MAIN PAGES:
- Homepage: https://shift-work.com/
- Our Services: https://shift-work.com/services/
- Resources Hub: https://shift-work.com/resources/
- Contact Us: https://shift-work.com/contact/
- Newsletter Signup: https://shift-work.com/newsletter/

10 GUIDES (deep-dive reference content):
- Shift Schedule Design: https://shift-work.com/resources/shift-schedule-design-guide/
- Shift Schedule Patterns: https://shift-work.com/resources/shift-schedule-patterns-guide/
- Equipment Utilization & Scheduling: https://shift-work.com/resources/equipment-utilization-shift-scheduling/
- Managing Variable Workloads: https://shift-work.com/resources/managing-variable-workloads/
- Overtime Management: https://shift-work.com/resources/overtime-management-guide/
- Schedule Change Management: https://shift-work.com/resources/schedule-change-management/
- Employee Engagement in Shift Work: https://shift-work.com/resources/employee-engagement-shift-work/
- Operational Best Practices: https://shift-work.com/resources/shift-work-best-practices/
- Staffing Strategy for 24/7 Operations: https://shift-work.com/resources/staffing-strategy-guide/
- Shift Work Health, Safety & Compliance: https://shift-work.com/resources/shift-work-health-safety-compliance/

7 SUPPORT ARTICLES (targeted how-to content):
- Scaling Production Up or Down: https://shift-work.com/resources/support/scaling-production-quickly/
- Sleep, Alertness & Safety: https://shift-work.com/resources/support/sleep-alertness-safety-shift-work/
- Maintenance Worker Scheduling: https://shift-work.com/resources/support/maintenance-worker-scheduling/
- Communicating Schedule Changes: https://shift-work.com/resources/support/communicating-schedule-changes/
- Workforce Survey Analysis: https://shift-work.com/resources/support/workforce-survey-analysis/
- Balancing Business & Employee Needs: https://shift-work.com/resources/support/balancing-business-employee-needs/
- Schedule Change Pitfalls: https://shift-work.com/resources/support/schedule-change-pitfalls/

6 INDUSTRY PAGES:
- Manufacturing & Assembly: https://shift-work.com/industries/manufacturing-assembly-operations/
- Distribution & Logistics: https://shift-work.com/industries/distribution-logistics-operations/
- Mining & Extraction: https://shift-work.com/industries/mining-extraction-industries/
- Refining & Utilities: https://shift-work.com/industries/refining-utilities-operations/
- Food & Beverage: https://shift-work.com/industries/food-beverage-manufacturing/
- Chemical & Pharmaceutical: https://shift-work.com/industries/chemical-pharmaceutical-operations/

TOPIC-TO-PAGE MAPPING (use these when a visitor asks about a topic):
- Overtime problems → Overtime Management guide + shift-work.com/resources/overtime-management-guide/
- Schedule patterns / DuPont / rotating → Schedule Patterns guide
- Employee engagement / surveys / morale → Employee Engagement guide
- Implementation / change management → Schedule Change Management guide
- Variable demand / seasonal → Managing Variable Workloads guide
- Equipment utilization / capacity → Equipment Utilization guide
- Staffing / hiring / retention → Staffing Strategy guide
- Health / safety / fatigue → Health, Safety & Compliance guide
- Best practices / general advice → Operational Best Practices guide
- Schedule design / shift lengths → Shift Schedule Design guide
- Industry-specific → Link to the matching industry page
- "How do you work" / process → Services page
- "How do I contact you" → Contact page or booking button at the bottom of the page
"""

# Opening message
THOMAS_OPENING = (
    "Hi, I'm Thomas — an AI advisor for Shiftwork Solutions. I help operations "
    "managers think through what's going on with their shift operations. I can also "
    "point you to specific guides and articles on our website if you're looking for "
    "background on a topic. What's on your mind?"
)

SESSION_LIMIT_HANDOFF = (
    "We've covered a lot of ground in this session. The next best step is probably "
    "a direct conversation with the team — you can book a free meeting using the "
    "button at the bottom of this page, or call us at (415) 265-1621. You can also "
    "download the transcript from the sidebar before you go."
)


def is_bot_response(reply):
    return reply.strip() == "BOT_DETECTED"


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
            "text": normalize_tts(text),
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
    c.drawRightString(width - margin, height - 0.55*inch, "Conversation Transcript")
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
    max_w = width - 2*margin - text_indent - 0.5*inch

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


# =============================================================
# ROUTES
# =============================================================

@app.route("/health")
@limiter.exempt
def health():
    return jsonify({
        "status":      "ok",
        "service":     "shift-work-diagnostic",
        "tts_enabled": bool(ELEVENLABS_API_KEY)
    }), 200


@app.route("/")
@limiter.limit("60/minute")
def index():
    return render_template_string(open("templates/index.html").read())


@app.route("/opening", methods=["POST"])
@limiter.limit("5/minute;20/hour")
def opening():
    session_id = issue_session_id()
    with _state_lock:
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
@limiter.limit("20/hour")
def transcribe():
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
@limiter.limit("10/minute;30/hour")
def chat():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    session_id   = (data.get("session_id") or "").strip()
    user_message = (data.get("message") or "").strip()

    if not user_message:
        return jsonify({"error": "No message provided"}), 400

    if len(user_message) > MAX_MESSAGE_CHARS:
        return jsonify({
            "error": "message_too_long",
            "message": f"Please keep messages under {MAX_MESSAGE_CHARS} characters."
        }), 400

    with _state_lock:
        cleanup_expired_sessions()

        if not session_id or not is_valid_session(session_id):
            return jsonify({
                "error": "invalid_session",
                "message": "Your session has expired or is invalid. Please refresh the page."
            }), 403

        count = session_message_counts.get(session_id, 0)
        if count >= SESSION_MAX_MESSAGES:
            return jsonify({
                "reply":       SESSION_LIMIT_HANDOFF,
                "audio":       None,
                "session_id":  session_id,
                "session_ended": True
            }), 200

        if not check_token_budget():
            print(f"[TOKEN_BUDGET] Rejected /chat -- daily budget exhausted")
            return jsonify({
                "error": "budget_exhausted",
                "message": ("Thomas is taking a short break. Please try again later, or "
                            "reach the team directly at (415) 265-1621 or shift-work.com.")
            }), 503

        if session_id not in conversation_histories:
            conversation_histories[session_id] = []

        conversation_histories[session_id].append({
            "role": "user", "content": user_message
        })

        if len(conversation_histories[session_id]) > 40:
            conversation_histories[session_id] = \
                conversation_histories[session_id][-40:]

        session_created_at[session_id] = time.time()
        session_message_counts[session_id] = count + 1

        messages_snapshot = list(conversation_histories[session_id])

    system_prompt = THOMAS_SYSTEM_PROMPT

    swarm_context = get_swarm_context(messages_snapshot)
    if swarm_context:
        system_prompt = system_prompt + swarm_context

    try:
        response = anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=400,
            system=system_prompt,
            messages=messages_snapshot
        )
        thomas_reply = response.content[0].text

        usage = getattr(response, "usage", None)
        if usage:
            with _state_lock:
                record_token_usage(
                    getattr(usage, "input_tokens", 0),
                    getattr(usage, "output_tokens", 0)
                )

        if is_bot_response(thomas_reply):
            with _state_lock:
                conversation_histories.pop(session_id, None)
                issued_session_ids.discard(session_id)
                session_created_at.pop(session_id, None)
                session_message_counts.pop(session_id, None)
            return jsonify({"bot_detected": True}), 200

        with _state_lock:
            if session_id in conversation_histories:
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
@limiter.limit("10/hour")
def download_transcript():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
    session_id = (data.get("session_id") or "").strip()
    lead_info  = data.get("lead_info", None)

    with _state_lock:
        messages = list(conversation_histories.get(session_id, []))

    if not messages:
        return jsonify({"error": "No conversation found for this session"}), 404

    try:
        pdf_buffer = generate_transcript_pdf(session_id, messages, lead_info)
        filename   = f"Shiftwork-Diagnostic-{datetime.now().strftime('%Y-%m-%d')}.pdf"

        try:
            pdf_bytes = pdf_buffer.read()
            pdf_buffer.seek(0)
            email_body = "<p>A visitor just downloaded a Thomas transcript.</p>"
            if lead_info:
                lines = "".join(
                    f"<li><strong>{k}:</strong> {v}</li>"
                    for k, v in lead_info.items() if v
                )
                email_body += f"<p><strong>Lead info:</strong></p><ul>{lines}</ul>"
            resend.Emails.send({
                "from": "thomas@shift-work.com",
                "to":   "jim@shift-work.com",
                "subject": f"Thomas Transcript — {datetime.now().strftime('%B %d, %Y %I:%M %p')}",
                "html": email_body,
                "attachments": [{"filename": filename, "content": list(pdf_bytes)}]
            })
        except Exception as e:
            print(f"Resend email error (non-fatal): {e}")

        return send_file(pdf_buffer, mimetype="application/pdf",
                         as_attachment=True, download_name=filename)

    except Exception as e:
        print(f"Transcript PDF error: {e}")
        return jsonify({"error": f"PDF generation failed: {str(e)}"}), 500


@app.route("/api/tts", methods=["POST"])
@limiter.limit("10/hour")
def tts_proxy():
    if not ELEVENLABS_API_KEY:
        return jsonify({"error": "TTS not configured"}), 503

    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "No text provided"}), 400

    if len(text) > MAX_TTS_CHARS:
        return jsonify({
            "error": f"Text exceeds {MAX_TTS_CHARS} character limit per request"
        }), 400

    voice_id = data.get("voice_id", ELEVENLABS_VOICE_ID).strip() or ELEVENLABS_VOICE_ID
    tts_url  = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

    try:
        headers = {
            "xi-api-key":   ELEVENLABS_API_KEY,
            "Content-Type": "application/json",
            "Accept":       "audio/mpeg"
        }
        payload = {
            "text":       normalize_tts(text),
            "model_id":   "eleven_turbo_v2",
            "voice_settings": {
                "stability":        0.5,
                "similarity_boost": 0.75,
                "style":            0.0,
                "use_speaker_boost": True
            }
        }

        el_response = requests.post(tts_url, headers=headers,
                                    json=payload, timeout=30)

        if el_response.status_code == 200:
            return Response(
                el_response.content,
                status=200,
                mimetype="audio/mpeg",
                headers={
                    "Cache-Control": "no-store",
                    "Content-Length": str(len(el_response.content))
                }
            )

        print(f"ElevenLabs TTS proxy error {el_response.status_code}: {el_response.text[:200]}")
        return jsonify({
            "error": f"ElevenLabs error {el_response.status_code}"
        }), el_response.status_code

    except requests.exceptions.Timeout:
        print("ElevenLabs TTS proxy timeout")
        return jsonify({"error": "TTS request timed out"}), 504
    except Exception as e:
        print(f"ElevenLabs TTS proxy exception: {e}")
        return jsonify({"error": f"TTS proxy error: {str(e)}"}), 500


@app.route("/booking-link")
@limiter.exempt
def booking_link():
    return jsonify({"url": TEAMS_BOOKING_LINK}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

# I did no harm and this file is not truncated
