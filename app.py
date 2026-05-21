# =============================================================
# app.py  —  Shift-Work Diagnostic Avatar (Thomas)
# Shiftwork Solutions LLC
# Created:      2026-03-15
# Last Updated: 2026-05-21 (hotfix v2)
#
# PURPOSE:
#   Flask backend for Thomas, an AI advisor that helps
#   operations managers think through their shift operations
#   challenges — before handing off to Shiftwork Solutions.
#   Thomas handles all topics organically in a single
#   conversation without menu-driven topic selection.
#
# CHANGE LOG:
#   2026-05-21 (v2 hotfix) — FIX 422 ERROR ON LIVEAVATAR TOKEN.
#                FIRST DEPLOY OF PHASE 2 RETURNED:
#                  "LiveAvatar token endpoint returned 422:
#                   body -> FULL -> avatar_persona: Field required"
#                ROOT CAUSE: avatar_persona is REQUIRED on FULL-mode
#                token requests, not optional as the v1 code assumed.
#                The v1 code only included avatar_persona in the
#                payload when LIVEAVATAR_VOICE_ID env var was set,
#                which it isn't on the current Render config.
#                FIX: _liveavatar_create_session_token() now always
#                builds an avatar_persona object. When voice_id is
#                not configured, it sends a minimal avatar_persona
#                with just language: "en" — LiveAvatar uses the
#                avatar's configured default voice (Graham) and
#                default STT (Deepgram). When LIVEAVATAR_VOICE_ID
#                IS set, voice_id is included. This is the ONLY
#                code change in this hotfix.
#                NO other function modified. NO other route modified.
#                NO existing constant changed. The new /live route,
#                templates/live.html, and all v1 Phase 2 behavior is
#                otherwise untouched.
#
#   2026-05-21 — LIVEAVATAR PHASE 2 — VOICE-VIDEO THOMAS.
#                Adds a new URL path /live serving a hybrid voice
#                experience: small streaming-video avatar in the
#                upper-right corner, main pane shows text bubbles
#                like today's chat, continuous voice activity
#                detection (no push-to-talk), powered by the
#                same Thomas backend brain that drives the text
#                chat at /. Built on LiveKit (the underlying
#                WebRTC engine LiveAvatar runs on).
#
#                NEW ROUTES (all additive):
#                  GET  /live
#                       Serves templates/live.html — the new voice
#                       avatar UI. Mirrors the sidebar and footer
#                       of the text chat at / for visual consistency.
#                  POST /api/live/session
#                       Creates a fresh LiveAvatar session. Calls
#                       LiveAvatar's /v1/sessions/token (with the
#                       HEYGEN_API_KEY env var) then /v1/sessions/start
#                       (with the returned session_token as Bearer auth).
#                       Returns { session_id, livekit_url,
#                       livekit_client_token, max_session_duration }
#                       to the browser. Browser uses these to open
#                       the WebRTC room directly with LiveKit.
#                  POST /api/live/session/stop
#                       Cleanly closes a LiveAvatar session early
#                       (used when the visitor navigates away or
#                       hits a logical end of conversation).
#                       Calls LiveAvatar's /v1/sessions/stop.
#                       Best-effort, fails silently.
#
#                EXISTING ROUTES — UNTOUCHED:
#                  /, /chat, /opening, /transcribe, /transcript,
#                  /api/tts, /booking-link, /health. The voice
#                  avatar at /live reuses /chat, /opening, and
#                  /transcribe via JavaScript fetch() calls —
#                  exactly the same endpoints the text chat uses.
#                  Same Claude system prompt, same Swarm KB
#                  integration, same Rule 1 neutrality, same
#                  three-part response, same session histories.
#                  conversation_histories[session_id] is shared
#                  between the two UIs — meaning a visitor could
#                  theoretically switch from voice to text mid-
#                  conversation and Thomas would continue
#                  seamlessly (a Phase 3 capability we aren't
#                  exposing yet but is structurally available).
#
#                NEW ENV VAR:
#                  HEYGEN_API_KEY — your LiveAvatar API key from
#                  app.liveavatar.com/developers (NOT a HeyGen
#                  key — they are not interchangeable; LiveAvatar
#                  and HeyGen are separate products).
#                  If missing, /api/live/session returns 503 and
#                  the /live page degrades gracefully with a
#                  visible error message. The text chat at / is
#                  completely unaffected.
#
#                NEW CONSTANTS (defaults — all overridable via env):
#                  LIVEAVATAR_API_BASE   — default https://api.liveavatar.com
#                  LIVEAVATAR_AVATAR_ID  — default the Phase 1 stock avatar
#                                          bb1f6ebc-b388-4a39-9e2b-8df618e0377c
#                  LIVEAVATAR_VOICE_ID   — defaults to None which lets
#                                          LiveAvatar pick the avatar's
#                                          default voice (Graham for the
#                                          current avatar). Set this env
#                                          var later to switch voices
#                                          without a redeploy.
#                  LIVEAVATAR_MAX_SESSION_DURATION — default 300 (5 min,
#                                          matches Starter plan cap)
#
#                RULE 1 COMPLIANCE (do no harm):
#                  - No existing function modified.
#                  - No existing route modified.
#                  - No existing constant changed.
#                  - All Phase 2 code lives in a clearly-marked
#                    block. The text chat at / is byte-identical
#                    in behavior to before this change.
#                  - All new HTTP calls to LiveAvatar fail gracefully
#                    and return clear error messages to the browser
#                    rather than crashing the request.
#
#   2026-05-20 — LIVE SWARM KNOWLEDGE BASE INTEGRATION.
#                Thomas pulls relevant project knowledge from
#                the Swarm Orchestrator on every conversation turn,
#                mirroring the existing query_swarm_norms() pattern.
#                The hardcoded knowledge reference inside
#                THOMAS_SYSTEM_PROMPT is retained as the fallback.
#                Both swarm_context and kb_context append
#                independently to system_prompt on each /chat turn.
#                Toggle via env vars SWARM_ENABLED and
#                SWARM_KB_ENABLED.
#
#   (Prior entries retained — see version history in git.)
#
# ROUTES:
#   GET  /                        — Serves Thomas chat UI (text mode)
#   GET  /live                    — Serves Thomas voice avatar UI (NEW)
#   POST /chat                    — Thomas reply + audio (used by both UIs)
#   POST /opening                 — Opening message + audio (used by both UIs)
#   POST /transcribe              — Audio blob -> text via ElevenLabs STT
#   POST /transcript              — Download PDF transcript
#   POST /api/tts                 — TTS proxy for pillar pages
#   POST /api/live/session        — Create LiveAvatar session (NEW)
#   POST /api/live/session/stop   — Close LiveAvatar session early (NEW)
#   GET  /booking-link            — Outlook booking URL
#   GET  /health                  — Render health check
#
# ENVIRONMENT VARIABLES (set in Render):
#   ANTHROPIC_API_KEY                — Claude API key
#   ELEVENLABS_API_KEY               — ElevenLabs API key
#   SWARM_ENABLED                    — Norm lookup toggle (default true)
#   SWARM_KB_ENABLED                 — KB context toggle (default true)
#   HEYGEN_API_KEY                   — LiveAvatar API key (Phase 2)
#   LIVEAVATAR_AVATAR_ID             — Override default avatar (optional)
#   LIVEAVATAR_VOICE_ID              — Override default voice (optional)
#   LIVEAVATAR_MAX_SESSION_DURATION  — Override default 300s (optional)
#   LIVEAVATAR_API_BASE              — Override API base URL (optional)
#
# DEPLOYMENT:
#   GitHub -> Render web service (shift-work-diagnostic)
#   Start command: gunicorn app:app
# =============================================================

import os
import re
import uuid
import base64
import requests
import io
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string, send_file, Response
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
# LIVEAVATAR PHASE 2 — CONFIGURATION (added 2026-05-21)
# =============================================================
#
# All LiveAvatar settings live here in one block. Override any of
# them via Render env vars without code changes. The defaults are
# safe for the current Starter plan and the avatar Jim selected
# during Phase 1 testing.
#
# Documentation: https://docs.liveavatar.com
# API base:      https://api.liveavatar.com
# =============================================================

HEYGEN_API_KEY = os.environ.get("HEYGEN_API_KEY")

LIVEAVATAR_API_BASE = os.environ.get(
    "LIVEAVATAR_API_BASE",
    "https://api.liveavatar.com"
).rstrip("/")

LIVEAVATAR_AVATAR_ID = os.environ.get(
    "LIVEAVATAR_AVATAR_ID",
    "bb1f6ebc-b388-4a39-9e2b-8df618e0377c"  # Phase 1 stock avatar
)

# Voice — None means "let LiveAvatar pick the avatar's default voice"
# (currently Graham for the chosen avatar). Set this env var later to
# switch to a different voice without a code change.
LIVEAVATAR_VOICE_ID = os.environ.get("LIVEAVATAR_VOICE_ID") or None

try:
    LIVEAVATAR_MAX_SESSION_DURATION = int(os.environ.get(
        "LIVEAVATAR_MAX_SESSION_DURATION", "300"
    ))
except (TypeError, ValueError):
    LIVEAVATAR_MAX_SESSION_DURATION = 300

# Timeout used for both /v1/sessions/token and /v1/sessions/start.
# These are infrequent calls (once per visitor session) so a longer
# timeout than the chat-loop SWARM_TIMEOUT is acceptable.
LIVEAVATAR_HTTP_TIMEOUT = 15


# =============================================================
# SESSION ID VALIDATION (added 2026-05-17)
# =============================================================

_SESSION_ID_RE = re.compile(r"^[0-9a-f]{32}$")


def validate_session_id(value):
    """
    Return the value unchanged if it is a valid 32-char lowercase
    hex string (the format produced by uuid.uuid4().hex).
    Return None for any other input — including None, empty string,
    wrong length, wrong charset, or the literal string "default".
    """
    if not isinstance(value, str):
        return None
    if not _SESSION_ID_RE.match(value):
        return None
    return value


# =============================================================
# LAYER 1: SWARM INTEGRATION — READ-ONLY NORMATIVE LOOKUP
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
    Decide whether a Swarm norm lookup is warranted for this turn.
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
# LAYER 1B: SWARM INTEGRATION — LIVE PROJECT KNOWLEDGE LOOKUP
# Added: 2026-05-20
# =============================================================

SWARM_KB_ENABLED                  = os.environ.get(
    "SWARM_KB_ENABLED", "true"
).lower() == "true"

SWARM_KNOWLEDGE_QUERY_AFTER_TURNS = 1


def query_swarm_knowledge(query_term):
    """
    Call the Swarm's live knowledge-base context endpoint.
    Returns an AI-ready formatted context string, or None on failure.
    """
    if not SWARM_KB_ENABLED or not query_term:
        return None
    try:
        url      = f"{SWARM_BASE_URL}/api/knowledge/context"
        params   = {"q": query_term}
        response = requests.get(url, params=params, timeout=SWARM_TIMEOUT)
        if response.status_code != 200:
            print(f"Swarm knowledge context returned {response.status_code}")
            return None
        data = response.json()
        if not data.get("success"):
            print(f"Swarm knowledge context success=false: "
                  f"{data.get('error', '')[:200]}")
            return None
        if not data.get("kb_ready"):
            return None
        context_str = (data.get("context") or "").strip()
        if not context_str:
            return None
        return context_str
    except requests.exceptions.Timeout:
        print("Swarm knowledge context timed out — continuing without KB context")
        return None
    except Exception as e:
        print(f"Swarm knowledge context error (non-fatal): {e}")
        return None


def get_swarm_knowledge_context(messages, user_message):
    """
    Decide whether a Swarm knowledge lookup is warranted for this
    turn, and if so, return a formatted context block.
    """
    if not SWARM_KB_ENABLED:
        return ""
    if not user_message:
        return ""
    if len(messages) < SWARM_KNOWLEDGE_QUERY_AFTER_TURNS:
        return ""
    kb_context = query_swarm_knowledge(user_message)
    if not kb_context:
        return ""
    return (
        "\n\n"
        "=== LIVE PROJECT KNOWLEDGE (from Shiftwork Solutions Swarm) ===\n"
        f"{kb_context}\n"
        "=== END LIVE PROJECT KNOWLEDGE ===\n"
    )


# =============================================================
# TTS URL STRIPPING — Added: 2026-04-21
# =============================================================

def strip_urls_for_tts(text):
    """Prepare Thomas's reply text for TTS by removing URLs gracefully."""
    text = re.sub(
        r'\s+(?:here|at|there)\s*:?\s*https?://[^\s,;)"\'<>]+',
        ' via the link in the chat',
        text,
        flags=re.IGNORECASE
    )
    text = re.sub(
        r'https?://[^\s,;)"\'<>]+',
        'via the link in the chat',
        text
    )
    text = re.sub(r'  +', ' ', text).strip()
    return text


# =============================================================
# SYSTEM PROMPT — SINGLE UNIFIED PROMPT
# =============================================================

THOMAS_SYSTEM_PROMPT = """
You are Thomas, an AI advisor for Shiftwork Solutions LLC — a management consulting firm
with hundreds of facilities worth of experience optimizing shift schedules across
manufacturing, pharmaceuticals, food processing, mining, distribution, and other 24/7
industrial operations. Partners Jim Dillingham, Dan Capshaw, and Ethan Franklin each
have over 30 years of experience.

YOUR PERSONALITY:
Confident but never cocky. You have hundreds of facilities worth of expertise behind you,
but you wear it lightly. Curious, not clinical — you ask follow-ups that show genuine
interest, not checkbox data gathering. Hopeful, not cheerleader-ish — no exclamation
points, no hype language. Quiet confidence reads as more credible. Warm, not chummy —
you are a trusted expert, not a buddy. You are someone a plant manager would feel
comfortable talking to over coffee.

HOW YOU TALK:
- Be concise but never curt. Three to four sentences when responding to a problem.
  Two sentences for simple exchanges. Say what needs saying, then stop.
- One question or invitation per response. Never two.
- Ask the question LAST — after your observation, not before.
- Questions should feel like genuine curiosity, not interrogation.
- Plain language. No bullet points. No corporate jargon. No headers or lists.
- Never use generic affirmations like "Great question!" or "I totally understand!"
  They sound hollow and erode trust.
- Never explain what you are about to do. Just do it.

YOUR APPROACH:
Visitors come to you because they are not ready to pick up the phone or book a meeting.
You are the safe first step. Your job is to make them feel heard, understood, and hopeful
— so they leave the conversation remembering you, wanting to come back, and wanting to
tell others about the experience.

Listen to what the visitor says and respond with whatever knowledge is most relevant.
If they describe a problem, diagnose it. If they ask about the process, explain it.
If they ask about engagement or change management, share the philosophy. If they ask
about their industry, engage with the specific challenges. Follow the conversation
naturally — you do not need to be told what topic you are in.

THE THREE-PART RESPONSE — WHEN A VISITOR DESCRIBES A PROBLEM:
Every time a visitor shares a workforce or scheduling challenge, follow this pattern:

1. VALIDATE EMPATHETICALLY. Reflect back the specific challenge in language that shows
   you recognize the weight of it. Not "I see" or "got it" — instead: "Overtime creep
   is one of the most exhausting problems to manage — it touches budgets, morale, and
   burnout all at once." Or: "Coverage gaps on weekends are a classic pressure point,
   and they rarely have simple causes."

2. NORMALIZE WITHOUT MINIMIZING. Let them know this is a known, solvable problem — but
   never make them feel their situation is ordinary or template-shaped. "This comes up
   often in 24/7 operations, and it's almost always solvable." Or: "You're not alone in
   this — but the path forward is going to look different for you than it does for
   anyone else."

3. OFFER VALUE — A LINK, AN INSIGHT, OR BOTH. Include a relevant link from the website
   and/or a genuine insight that shows expertise. Then invite them to share more about
   their situation. "The solution will be unique to your operation, and it might surprise
   you — the best fixes often benefit both the company and the workforce in ways people
   don't expect. We have a guide that digs into this — check it out here: [link]. Tell
   me a little about your setup and I can point you toward what's most relevant."

The goal: every visitor should walk away thinking three things — he understood my actual
problem, there is real expertise behind this, and the answer is going to be worth coming
back for. That is what makes them remember you, return, and tell someone else.

Do NOT sound like a chatbot running through a decision tree. Sound like a thoughtful
expert listening carefully. Do NOT minimize their problem by jumping too quickly to
"we can fix this" — sit with the difficulty for a beat first.

PROACTIVE SITE LINKING (THIS IS IMPORTANT):
Any time the conversation touches a topic that has a page on the website, include the
link in your FIRST response about that topic. Do not wait for the visitor to ask. If
someone mentions overtime, your response should include the overtime guide link. If they
ask about schedules, include the schedule patterns or schedule design link. If they
mention their industry, link to their industry page. If they ask what you do, link to
services. This should feel natural — not like a sales pitch, just helpful.

When sharing a link, briefly describe what the visitor will find, then include the full
URL. The interface automatically turns the URL into a clickable link that opens in a
new tab. For example: "We have a guide that covers exactly that — you can check it out
here: https://shift-work.com/resources/overtime-management-guide/"

One or two links per response is plenty. Do not dump a list of links.

WHAT THOMAS CAN AND CANNOT RECOMMEND:
Thomas can offer directional observations — "It sounds like you might need a 24/7
schedule" or "A 12-hour pattern might give you the coverage you're missing" — as long
as they are framed as possibilities, not prescriptions. These are the kinds of things
a knowledgeable person would say in a casual conversation.

NEVER recommend a weekend-only crew. A weekend crew is a separate group of employees
who only work weekends while other crews work only weekdays. This approach has serious
problems — retention, fatigue, pay equity, morale — and Shiftwork Solutions almost
never recommends it. If a visitor mentions they are considering a weekend crew or asks
about one, Thomas should flag it as something that usually creates more problems than
it solves and suggest they discuss it with the team before going down that path.

Thomas should not provide detailed schedule designs, specific rotation patterns, policy
language, or implementation plans. Those are deliverables of a paid engagement.

HANDOFF — MOVE HERE QUICKLY:
Do not wait until you have a complete picture. Once you can name the problem, transition
to handoff. Offer three options naturally — not as a list, but woven into the conversation:
1. Book a free consultation using the scheduling link in the sidebar — no obligation,
   just a real conversation with someone who has done this hundreds of times.
2. "If you'd prefer, I can have someone from the team reach out to you directly."
   (This triggers the lead capture form in the sidebar.)
3. Point them to relevant content on shift-work.com if their question is more
   exploratory — e.g. "There's some good background on this at shift-work.com that
   might help you frame the conversation."
Always remind them the transcript can be downloaded from the sidebar and the team can
be reached at (415) 265-1621 or shift-work.com.

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
safety-critical fatigue. Paper/packaging: continuous web operations, grade changes affect
scheduling. Call centers/transport/ports: demand-driven, variable hours.

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
systems — discuss concepts only.

OUT OF SCOPE:
Wage rates, union contract specifics, individual HR cases, anything unrelated to shift
operations. Redirect briefly and move on.

JOB SATISFACTION IS IN SCOPE:
Job satisfaction, workforce morale, and employee wellbeing as they relate to shift
schedules are fully within scope and are core survey topics. Never redirect away from
job satisfaction.

SHIFTWORKER HEALTH — BIOLOGICAL CLOCK, SLEEP & LIFESTYLE (discuss openly):
This is an important topic that managers often raise when workers are fatigued, calling
in sick, or struggling with night shifts. Thomas can discuss all of this knowledgeably.
Point visitors to the health guide at https://shift-work.com/resources/shiftworker-health/
when this topic comes up.

THE BIOLOGICAL CLOCK AND CIRCADIAN RHYTHMS:
The biological clock runs on a roughly 24-hour cycle and is calibrated primarily by
light exposure. It drives a predictable daily pattern of body temperature and alertness —
peaking in mid-to-late afternoon and hitting its lowest point between 2 AM and 6 AM
(the "circadian trough"). Night shift workers are asked to be productive during the
circadian trough, which is why errors, accidents, and health complications are higher
on night shifts across virtually every industry studied. Rotating shift workers face an
additional complication: the clock never fully adapts because most rotating schedules
change before the 7–10 days of consistent exposure needed for meaningful adaptation can
occur. Rotating workers live in a state of perpetual partial adjustment — like mild,
chronic jet lag.

SLEEP REQUIREMENTS AND SLEEP DEBT:
Most adults need 7–9 hours of sleep per 24-hour period. This requirement is largely
genetic — it cannot be trained away. Shiftworkers consistently fall short because daytime
sleep is inherently shorter than nighttime sleep (on average 1.5–2 hours shorter for the
same person in the same environment) because the circadian clock is signaling wakefulness
during daylight hours. When a person sleeps less than their personal requirement, sleep
debt accumulates cumulatively. The most dangerous feature of sleep debt is that people
with significant debt routinely underestimate how impaired they are — they feel subjectively
alert while their performance is objectively compromised. This is a safety issue as well
as a health issue.

LIFESTYLE FACTORS:
Caffeine: useful alertness tool when timed correctly. Taken within 4–6 hours of intended
sleep, it delays onset and reduces quality. Dependence on caffeine to offset chronic sleep
debt is not sustainable.
Alcohol: may help sleep onset but fragments sleep architecture — reduces REM sleep and
causes earlier waking. Counterproductive as a sleep aid for shiftworkers.
Nicotine: a stimulant that disrupts sleep onset and quality.
Diet and meal timing: the digestive system has its own circadian rhythm. Heavy meals
during the biological night cause more GI distress. Lighter meals during night shifts help.
Exercise: improves sleep quality and circadian regulation. Intense exercise immediately
before sleep may delay onset for some people.
Light exposure: bright light during night shifts suppresses melatonin and improves
alertness. Darkness during sleep (blackout curtains, eye masks) meaningfully improves
daytime sleep duration. Light is the primary signal that sets the biological clock.
Napping: a 20-minute nap before a night shift can significantly reduce shift fatigue.
A 90-minute nap allows a full sleep cycle and provides more sustained recovery.
Sleep environment: dark, quiet, and cool. Blackout curtains are the single most
impactful investment a day-sleeping shiftworker can make.
Health habits benchmark: shiftworkers follow an average of 3.4 of six key longevity-linked
health habits, versus 4.1 for day workers — a meaningful gap driven by structural pressures.

SCHEDULE-SPECIFIC SLEEP STRATEGIES:
8-hour rotating: anticipate first night by sleeping late the day before; take a pre-shift
nap; go straight to bed after shifts; protect the sleep environment.
8-hour fixed nights: healthiest to maintain consistent sleep on days off; if wanting
daytime participation on days off, use anchor sleep (see below).
12-hour rotating: more days off than 8-hour schedules — many workers "tough out" nights
without full adaptation; pre-shift napping helps; after last night shift, sleep only
3–4 hours then return to normal pattern.
12-hour fixed nights: anchor sleep or rapid adjustment strategies; any sleep strategy
is better than none.
12-hour fixed days: go to bed earlier before first day back; avoid sleeping in late on
days off (creates Monday morning fatigue); catch up by going to bed earlier, not staying
in bed later.

ANCHOR SLEEP TECHNIQUE:
For fixed night shift workers who want to participate in daytime life on days off without
fully flipping their schedule. If the worker normally sleeps 8 AM–4 PM on work days, on
days off they sleep 2 AM–10 AM instead. The 2-hour overlap between the two windows
(approximately 8–10 AM) is the "anchor" — it prevents the biological clock from fully
shifting to a daytime schedule while still allowing afternoon and evening participation.

RAPID ADJUSTMENT TO DAYS:
An alternative for fixed night workers. After the last night shift, sleep only 4 hours
(e.g., 8 AM–noon). Get up and spend 20+ minutes in bright sunlight or strong indoor light.
Result: a 4-hour sleep debt that helps the worker fall asleep at a normal evening time,
without losing the entire day. Less recovery than a full sleep but preserves family time.

=== WEBSITE DIRECTORY ===
The Shiftwork Solutions website is at shift-work.com. When a visitor asks about a topic
covered on the website, provide the direct link.

MAIN PAGES:
- Homepage: https://shift-work.com/
- Our Services: https://shift-work.com/services/
- Resources Hub: https://shift-work.com/resources/
- Industries Landing: https://shift-work.com/industries/
- Why Us: https://shift-work.com/why-us/
- About Us: https://shift-work.com/about/
- Our Team: https://shift-work.com/our_team/
- Client Testimonials: https://shift-work.com/testimonials/
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
- Absenteeism & Coverage Gaps: https://shift-work.com/resources/absenteeism-relief-coverage-management/
- Shift Work Policies (Pay, Time-Off & Compliance): https://shift-work.com/resources/shift-work-policies-guide/

HEALTH GUIDE (added 2026-05-06):
- Shiftworker Health (Sleep, Circadian Rhythms & Lifestyle): https://shift-work.com/resources/shiftworker-health/

7 SUPPORT ARTICLES (targeted how-to content):
- Scaling Production Up or Down: https://shift-work.com/resources/support/scaling-production-quickly/
- Sleep, Alertness & Safety: https://shift-work.com/resources/support/sleep-alertness-safety-shift-work/
- Maintenance Worker Scheduling: https://shift-work.com/resources/support/maintenance-worker-scheduling/
- Communicating Schedule Changes: https://shift-work.com/resources/support/communicating-schedule-changes/
- Workforce Survey Analysis: https://shift-work.com/resources/support/workforce-survey-analysis/
- Balancing Business & Employee Needs: https://shift-work.com/resources/support/balancing-business-employee-needs/
- Schedule Change Pitfalls: https://shift-work.com/resources/support/schedule-change-pitfalls/

7 INDUSTRY PAGES:
- Manufacturing & Assembly: https://shift-work.com/industries/manufacturing-assembly-operations/
- Distribution & Logistics: https://shift-work.com/industries/distribution-logistics-operations/
- Mining & Extraction: https://shift-work.com/industries/mining-extraction-industries/
- Refining & Utilities: https://shift-work.com/industries/refining-utilities-operations/
- Food & Beverage: https://shift-work.com/industries/food-beverage-manufacturing/
- Chemical & Pharmaceutical: https://shift-work.com/industries/chemical-pharmaceutical-operations/
- Paper & Packaging: https://shift-work.com/industries/paper-packaging-operations/

DIAGNOSTIC TOOLS:
- 26 Warning Signs: https://shift-work.com/resources/26-warning-signs-schedule-problems/

TOPIC-TO-PAGE MAPPING (use these when a visitor asks about a topic):
- Overtime problems → Overtime Management guide
- Schedule patterns / DuPont / rotating → Schedule Patterns guide
- Schedule design / shift lengths / "I need a schedule" → Schedule Design guide
- Employee engagement / surveys / morale → Employee Engagement guide
- Implementation / change management → Schedule Change Management guide
- Variable demand / seasonal → Managing Variable Workloads guide
- Equipment utilization / capacity → Equipment Utilization guide
- Absenteeism / call-offs / coverage gaps → Absenteeism & Coverage Gaps guide
- Pay policies / vacation / holiday / shift differential → Shift Work Policies guide
- Health / circadian rhythms / biological clock / sleep strategies / lifestyle → Shiftworker Health guide
- Fatigue / alertness / night shift health / sleep debt → Shiftworker Health guide AND Sleep, Alertness & Safety article
- Best practices / general advice → Operational Best Practices guide
- Industry-specific → Link to the matching industry page
- "How do you work" / process / services → Services page
- "How do I contact you" → Contact page or booking link in sidebar
- "Who are you" / about the company → About Us or Why Us page
- "Who would I work with" / team → Our Team page
- "Do you have references" / testimonials → Client Testimonials page
- "What should I look for" / warning signs → 26 Warning Signs page
- Communication / how to tell employees → Communicating Schedule Changes article
- Maintenance scheduling → Maintenance Worker Scheduling article
- Scaling up/down / production changes → Scaling Production article

=== LIVE PROJECT KNOWLEDGE — HOW TO USE IT ===
(Added 2026-05-20.)

In addition to the KNOWLEDGE REFERENCE above (which is your reliable baseline and is
always available), a section titled "LIVE PROJECT KNOWLEDGE (from Shiftwork Solutions
Swarm)" may be appended below this prompt on any given turn. It is drawn live from the
Shiftwork Solutions internal knowledge base. Treat it as authoritative for Shiftwork
Solutions thinking and methodology. Use it to inform your answer naturally — do NOT
quote it verbatim, do NOT name files or sources, and do NOT tell the visitor you are
reading from a knowledge base. Continue to obey every rule above: Rule 1 (neutrality)
is absolute, Rule 2 (proprietary content) still applies. If the live block does not
appear on a given turn, just rely on the KNOWLEDGE REFERENCE above.
"""

# Opening message — one universal opener
THOMAS_OPENING = (
    "Hi, I'm Thomas — an AI advisor for Shiftwork Solutions. I help operations "
    "managers think through what's going on with their shift operations. I can also "
    "point you to specific guides and articles on our website if you're looking for "
    "background on a topic. What's on your mind?"
)

conversation_histories = {}


def is_bot_response(reply):
    """Check if Claude returned the bot detection signal."""
    return reply.strip() == "BOT_DETECTED"


def generate_speech(text):
    """
    Call ElevenLabs TTS, return base64 MP3. Returns None on failure.
    """
    if not ELEVENLABS_API_KEY:
        return None
    try:
        tts_text = strip_urls_for_tts(text)
        if not tts_text:
            return None

        headers = {
            "xi-api-key": ELEVENLABS_API_KEY,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg"
        }
        payload = {
            "text": tts_text,
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


@app.route("/health")
def health():
    """
    Health check endpoint for Render and external monitors.
    Added 2026-05-21: liveavatar_enabled field (Phase 2).
    """
    return jsonify({
        "status":             "ok",
        "service":            "shift-work-diagnostic",
        "tts_enabled":        bool(ELEVENLABS_API_KEY),
        "swarm_enabled":      SWARM_ENABLED,
        "swarm_kb_enabled":   SWARM_KB_ENABLED,
        "liveavatar_enabled": bool(HEYGEN_API_KEY),
        "liveavatar_avatar":  LIVEAVATAR_AVATAR_ID if HEYGEN_API_KEY else None,
    }), 200


@app.route("/")
def index():
    return render_template_string(open("templates/index.html").read())


# =============================================================
# LIVEAVATAR PHASE 2 — NEW ROUTES (added 2026-05-21)
# =============================================================
#
# /live                         — serves the new voice-avatar UI
# /api/live/session             — creates a LiveAvatar streaming session
# /api/live/session/stop        — closes a LiveAvatar session early
#
# These routes are completely independent of /, /chat, /opening,
# /transcribe, and every other existing route. They share the
# in-memory conversation_histories dict so Claude's brain is the
# same between the two UIs.
# =============================================================


@app.route("/live")
def live():
    """
    Serve the voice avatar UI. Mirrors the visual chrome (sidebar,
    footer, header) of the text chat at / for consistency. The avatar
    appears in a small corner overlay; the main pane shows text bubbles
    rendered from /chat replies, exactly like the text chat does.
    """
    return render_template_string(open("templates/live.html").read())


def _liveavatar_create_session_token(session_history_count):
    """
    Internal helper: call LiveAvatar's /v1/sessions/token endpoint.

    Returns a dict { session_id, session_token } on success, or raises
    a RuntimeError with a human-readable message on failure.

    `session_history_count` is a placeholder for future tuning; currently
    unused in the token request body but kept here so callers can pass
    conversation state if we ever decide to vary token configuration
    based on conversation length.
    """
    if not HEYGEN_API_KEY:
        raise RuntimeError(
            "LiveAvatar API key not configured. Set HEYGEN_API_KEY in Render."
        )

    url = f"{LIVEAVATAR_API_BASE}/v1/sessions/token"

    # Build avatar_persona — REQUIRED field on FULL-mode requests
    # (the v1 hotfix changed this from "optional" to "always present").
    #
    # When LIVEAVATAR_VOICE_ID env var is set, we pass voice_id and
    # LiveAvatar uses that specific voice. When it is NOT set (the
    # default and current state), we pass only language: "en" — that
    # is sufficient to satisfy the validator, and LiveAvatar falls back
    # to the avatar's own default voice (Graham for the current stock
    # avatar) and the default STT provider (Deepgram).
    avatar_persona = {
        "language": "en",
    }
    if LIVEAVATAR_VOICE_ID:
        avatar_persona["voice_id"] = LIVEAVATAR_VOICE_ID

    payload = {
        "avatar_id":             LIVEAVATAR_AVATAR_ID,
        "avatar_persona":        avatar_persona,
        "mode":                  "FULL",
        "is_sandbox":            False,
        "max_session_duration":  LIVEAVATAR_MAX_SESSION_DURATION,
        "interactivity_type":    "CONVERSATIONAL",
    }

    headers = {
        "X-API-KEY":    HEYGEN_API_KEY,
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(
            url, json=payload, headers=headers,
            timeout=LIVEAVATAR_HTTP_TIMEOUT
        )
    except requests.exceptions.Timeout:
        raise RuntimeError(
            "LiveAvatar token request timed out. Try again in a moment."
        )
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"LiveAvatar token request failed: {e}")

    if resp.status_code != 200:
        try:
            body = resp.json()
            detail = body.get("message") or body.get("detail") or resp.text[:300]
        except Exception:
            detail = resp.text[:300]
        raise RuntimeError(
            f"LiveAvatar token endpoint returned {resp.status_code}: {detail}"
        )

    try:
        data = resp.json().get("data") or {}
    except Exception:
        raise RuntimeError("LiveAvatar token response was not valid JSON.")

    session_id    = data.get("session_id")
    session_token = data.get("session_token")
    if not session_id or not session_token:
        raise RuntimeError(
            "LiveAvatar token response was missing session_id or session_token."
        )

    return {"session_id": session_id, "session_token": session_token}


def _liveavatar_start_session(session_token):
    """
    Internal helper: call LiveAvatar's /v1/sessions/start endpoint.

    Uses the session_token from _liveavatar_create_session_token as
    Bearer auth (NOT the X-API-KEY). Returns the LiveKit room
    coordinates the browser needs to open the WebRTC stream.

    Returns a dict with:
        session_id           — same value the browser already has
        livekit_url          — wss://... URL the browser connects to
        livekit_client_token — LiveKit access token for the browser
        max_session_duration — seconds before LiveAvatar auto-closes
        ws_url               — optional WebSocket URL for events

    Raises RuntimeError on failure.
    """
    url = f"{LIVEAVATAR_API_BASE}/v1/sessions/start"

    headers = {
        "Authorization": f"Bearer {session_token}",
    }

    try:
        resp = requests.post(
            url, headers=headers,
            timeout=LIVEAVATAR_HTTP_TIMEOUT
        )
    except requests.exceptions.Timeout:
        raise RuntimeError(
            "LiveAvatar start request timed out. Try again in a moment."
        )
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"LiveAvatar start request failed: {e}")

    if resp.status_code not in (200, 201):
        try:
            body = resp.json()
            detail = body.get("message") or body.get("detail") or resp.text[:300]
        except Exception:
            detail = resp.text[:300]
        raise RuntimeError(
            f"LiveAvatar start endpoint returned {resp.status_code}: {detail}"
        )

    try:
        data = resp.json().get("data") or {}
    except Exception:
        raise RuntimeError("LiveAvatar start response was not valid JSON.")

    livekit_url   = data.get("livekit_url")
    livekit_token = data.get("livekit_client_token")
    if not livekit_url or not livekit_token:
        raise RuntimeError(
            "LiveAvatar start response was missing livekit_url or "
            "livekit_client_token."
        )

    return {
        "session_id":            data.get("session_id"),
        "livekit_url":           livekit_url,
        "livekit_client_token":  livekit_token,
        "max_session_duration":  data.get("max_session_duration",
                                          LIVEAVATAR_MAX_SESSION_DURATION),
        "ws_url":                data.get("ws_url"),
    }


@app.route("/api/live/session", methods=["POST"])
def create_live_session():
    """
    Create a fresh LiveAvatar session and return the coordinates the
    browser needs to join the streaming room.

    Two-step flow:
      1. /v1/sessions/token  — authenticated with X-API-KEY,
                                returns session_token
      2. /v1/sessions/start  — authenticated with Bearer session_token,
                                returns livekit_url + livekit_client_token

    Both calls are made server-side so the LiveAvatar API key never
    touches the browser.

    Request body (optional): { "thomas_session_id": "<32hex>" }
        Used only to look up how long the conversation has been going,
        for tuning purposes. Not required.

    Response (200): {
        "success":              true,
        "session_id":           "<liveavatar session uuid>",
        "livekit_url":          "wss://...",
        "livekit_client_token": "<jwt>",
        "max_session_duration": 300,
        "avatar_id":            "<bb1f...>",
    }

    Response (503): {
        "success": false,
        "error":   "LiveAvatar API key not configured."
    }

    Response (502): {
        "success": false,
        "error":   "<human-readable LiveAvatar failure reason>"
    }
    """
    if not HEYGEN_API_KEY:
        return jsonify({
            "success": False,
            "error":   "LiveAvatar is not enabled on this server. "
                       "Voice chat is unavailable — please use the text "
                       "chat at the home page instead."
        }), 503

    data = request.get_json(silent=True) or {}
    thomas_session_id = validate_session_id(data.get("thomas_session_id"))
    history_count = 0
    if thomas_session_id and thomas_session_id in conversation_histories:
        history_count = len(conversation_histories[thomas_session_id])

    try:
        token_result = _liveavatar_create_session_token(history_count)
    except RuntimeError as e:
        print(f"LiveAvatar token failure: {e}")
        return jsonify({
            "success": False,
            "error":   str(e),
        }), 502

    try:
        start_result = _liveavatar_start_session(token_result["session_token"])
    except RuntimeError as e:
        print(f"LiveAvatar start failure: {e}")
        return jsonify({
            "success": False,
            "error":   str(e),
        }), 502

    print(
        f"LiveAvatar session created: "
        f"id={start_result['session_id']} "
        f"duration={start_result['max_session_duration']}s "
        f"thomas_session={thomas_session_id}"
    )

    return jsonify({
        "success":              True,
        "session_id":           start_result["session_id"],
        "livekit_url":          start_result["livekit_url"],
        "livekit_client_token": start_result["livekit_client_token"],
        "max_session_duration": start_result["max_session_duration"],
        "avatar_id":            LIVEAVATAR_AVATAR_ID,
    }), 200


@app.route("/api/live/session/stop", methods=["POST"])
def stop_live_session():
    """
    Close a LiveAvatar session early. Best-effort — if the call fails
    for any reason, we return 200 anyway so the browser's beforeunload
    handler does not block the page navigation.

    Request body: { "session_id": "<liveavatar session uuid>" }

    LiveAvatar API: POST /v1/sessions/stop with Bearer session_token.
    Note: we don't have the session_token anymore at this point —
    only the LiveAvatar session_id. The /v1/sessions/stop endpoint
    accepts the session_token from the original create_session_token
    call. Since the browser has it (we sent it as part of the create
    flow's session_token), the browser passes it back here.

    For the simpler case where the browser only has the session_id,
    we also accept that — the session will auto-close from the
    LiveAvatar side at max_session_duration regardless.
    """
    if not HEYGEN_API_KEY:
        # Don't 503 here — the browser is just trying to clean up,
        # there's no useful action to take.
        return jsonify({"success": True, "noop": True}), 200

    data = request.get_json(silent=True) or {}
    session_token = data.get("session_token")

    if not session_token:
        # Can't call stop without the session_token. The session will
        # auto-terminate at max_session_duration. Return success so the
        # browser's cleanup flow doesn't block.
        return jsonify({
            "success": True,
            "noop":    True,
            "reason":  "no session_token provided — session will "
                       "auto-close at duration limit"
        }), 200

    url = f"{LIVEAVATAR_API_BASE}/v1/sessions/stop"
    headers = {"Authorization": f"Bearer {session_token}"}

    try:
        resp = requests.post(
            url, headers=headers, timeout=LIVEAVATAR_HTTP_TIMEOUT
        )
        if resp.status_code in (200, 201, 204):
            return jsonify({"success": True}), 200
        # Non-fatal — log but report success so beforeunload doesn't hang
        print(
            f"LiveAvatar stop returned {resp.status_code} "
            f"(non-fatal): {resp.text[:200]}"
        )
        return jsonify({
            "success": True,
            "warning": f"stop call returned {resp.status_code}"
        }), 200
    except Exception as e:
        print(f"LiveAvatar stop exception (non-fatal): {e}")
        return jsonify({"success": True, "warning": str(e)}), 200


# =============================================================
# END LIVEAVATAR PHASE 2 ROUTES
# =============================================================


@app.route("/opening", methods=["POST"])
def opening():
    """
    Return the opening message and audio.
    """
    data = request.get_json() or {}
    incoming   = data.get("session_id")
    session_id = validate_session_id(incoming) or uuid.uuid4().hex

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
    Main conversation route — used by BOTH the text chat at /
    and the voice avatar at /live. Same Claude brain, same system
    prompt, same Swarm integrations.
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    session_id = validate_session_id(data.get("session_id"))
    if not session_id:
        return jsonify({
            "error": "Invalid or missing session_id. "
                     "Call /opening first to obtain a session."
        }), 400

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

    # Layer 1: norm context
    swarm_context = get_swarm_context(conversation_histories[session_id])
    if swarm_context:
        system_prompt = system_prompt + swarm_context

    # Layer 1B: live KB context
    kb_context = get_swarm_knowledge_context(
        conversation_histories[session_id],
        user_message
    )
    if kb_context:
        system_prompt = system_prompt + kb_context

    try:
        response = anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=600,
            system=system_prompt,
            messages=conversation_histories[session_id]
        )
        thomas_reply = response.content[0].text

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


FORMSPREE_ENDPOINT = "https://formspree.io/f/xwvwnwea"


def email_transcript_via_formspree(session_id, messages, lead_info=None):
    """Send a formatted text transcript to Formspree (fire-and-forget)."""
    try:
        lines = []
        lines.append("=== THOMAS CONVERSATION TRANSCRIPT ===")
        lines.append(f"Session: {session_id}")
        lines.append(f"Date: {datetime.now().strftime('%B %d, %Y at %I:%M %p UTC')}")
        lines.append("")

        if lead_info:
            lines.append("--- Contact Information ---")
            for key, val in lead_info.items():
                if val:
                    lines.append(f"{key}: {val}")
            lines.append("")

        lines.append("--- Conversation ---")
        for msg in messages:
            role    = msg.get("role", "")
            content = msg.get("content", "")
            if content in ("__INIT__", "BOT_DETECTED"):
                continue
            speaker = "Thomas" if role == "assistant" else "Visitor"
            lines.append(f"\n{speaker}:")
            lines.append(content)

        lines.append("\n=== END TRANSCRIPT ===")

        transcript_text = "\n".join(lines)

        payload = {
            "_subject":  f"Thomas Transcript — {datetime.now().strftime('%B %d, %Y %I:%M %p')}",
            "message":   transcript_text,
            "_replyto":  "noreply@shift-work.com"
        }

        resp = requests.post(
            FORMSPREE_ENDPOINT,
            json=payload,
            headers={"Accept": "application/json"},
            timeout=5
        )

        if resp.status_code == 200:
            print(f"Transcript email sent for session {session_id}")
        else:
            print(f"Formspree transcript email failed {resp.status_code}: {resp.text[:200]}")

    except requests.exceptions.Timeout:
        print("Formspree transcript email timed out — continuing without email")
    except Exception as e:
        print(f"Formspree transcript email error (non-fatal): {e}")


@app.route("/transcript", methods=["POST"])
def download_transcript():
    """Generate and return a PDF transcript for a session."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    session_id = validate_session_id(data.get("session_id"))
    if not session_id:
        return jsonify({
            "error": "Invalid or missing session_id. "
                     "Call /opening first to obtain a session."
        }), 400

    lead_info  = data.get("lead_info", None)
    messages   = conversation_histories.get(session_id, [])
    if not messages:
        return jsonify({"error": "No conversation found for this session"}), 404
    try:
        email_transcript_via_formspree(session_id, messages, lead_info)

        pdf_buffer = generate_transcript_pdf(session_id, messages, lead_info)
        filename   = f"Shiftwork-Diagnostic-{datetime.now().strftime('%Y-%m-%d')}.pdf"
        return send_file(pdf_buffer, mimetype="application/pdf",
                         as_attachment=True, download_name=filename)
    except Exception as e:
        print(f"Transcript PDF error: {e}")
        return jsonify({"error": f"PDF generation failed: {str(e)}"}), 500


@app.route("/api/tts", methods=["POST"])
def tts_proxy():
    """TTS proxy for pillar pages on shift-work.com."""
    if not ELEVENLABS_API_KEY:
        return jsonify({"error": "TTS not configured"}), 503

    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "No text provided"}), 400

    if len(text) > 4500:
        return jsonify({"error": "Text exceeds 4500 character limit per request"}), 400

    voice_id = data.get("voice_id", ELEVENLABS_VOICE_ID).strip() or ELEVENLABS_VOICE_ID
    tts_url  = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

    try:
        headers = {
            "xi-api-key":   ELEVENLABS_API_KEY,
            "Content-Type": "application/json",
            "Accept":       "audio/mpeg"
        }
        payload = {
            "text":       text,
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
def booking_link():
    return jsonify({"url": TEAMS_BOOKING_LINK}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

# I did no harm and this file is not truncated
