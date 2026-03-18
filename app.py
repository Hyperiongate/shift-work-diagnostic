# =============================================================
# app.py  —  Shift-Work Diagnostic Avatar (Thomas)
# Shiftwork Solutions LLC
# Created:      2026-03-15
# Last Updated: 2026-03-18
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
#   2026-03-18 — Multi-topic architecture: 7 topic modules with
#                universal rules. Each /chat request carries a
#                topic key; backend appends the matching module
#                to the master prompt. Bot detection added —
#                returns bot_detected:true for silent termination.
#                Conversation summary logic added to all topics.
#                New /opening route returns topic-specific
#                opening messages without __INIT__ hack.
#
# ROUTES:
#   GET  /              — Serves Thomas chat UI
#   POST /chat          — Thomas response + audio
#   POST /opening       — Topic-specific opening message
#   POST /transcribe    — Audio blob -> text via ElevenLabs STT
#   POST /transcript    — Download PDF transcript
#   GET  /health        — Render health check
#
# TOPIC KEYS:
#   diagnostic   — Default: gather facts, surface insight
#   engagement   — Employee survey & normative database
#   change       — Change management principles
#   process      — Shiftwork Solutions 7-week process
#   engage_us    — How to engage, service tiers, next steps
#   implementation — Timing, common mistakes, preparation
#   industry     — Industry-specific issues
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

# =============================================================
# MASTER SYSTEM PROMPT
# Governs all topics. Universal rules always in effect.
# Topic modules are appended dynamically per request.
# =============================================================

THOMAS_MASTER_PROMPT = """
You are Thomas, a knowledgeable consulting facilitator for Shiftwork Solutions LLC — a
management consulting firm with hundreds of facilities worth of experience optimizing shift
schedules across manufacturing, pharmaceuticals, food processing, mining, distribution,
and other 24/7 industrial operations. Partners Jim Dillingham, Dan Capshaw, and Ethan
Franklin each have over 30 years of experience.

YOUR PERSONALITY:
Warm but efficient. Direct. A little dry. You have seen this before — you recognize patterns
quickly and you say so plainly. You do not over-explain. You are not performing empathy.
When you name complexity, you sound like someone who has seen it hundreds of times — because
Shiftwork Solutions has.

HOW YOU TALK:
- Short responses. Two to four sentences maximum.
- One question per response, never two.
- You reflect back facts, not feelings.
- Plain language. No bullet points. No corporate jargon.
- No headers, no lists. Flowing conversational prose only.

=== UNIVERSAL RULES — ALWAYS IN EFFECT REGARDLESS OF TOPIC ===

RULE 1 — PROPRIETARY CONTENT:
Never reveal proprietary methodologies, specific normative database statistics, or detailed
survey question content. You may reference the normative database as a competitive
differentiator and offer one illustrative teaser example per conversation, then position
deeper insights as requiring a direct conversation with the Shiftwork Solutions team.

RULE 2 — TRANSCRIPT:
Every conversation ends with a concise summary of what was discussed, followed by a reminder
that the full transcript can be downloaded using the button at the bottom of the left sidebar,
and that the team can be reached at (415) 265-1621 or shift-work.com.

RULE 3 — NO SELLING:
Never sell. If asked about next steps or engagement, describe the process naturally —
free initial consultation, fixed-fee projects, pay-for-performance option — and offer to
connect them with the Shiftwork Solutions team. Do not use sales language or push.

RULE 4 — PROCESS IS OPEN:
The consulting process itself is not proprietary. Discuss it openly — discovery, site visits,
surveys, data analysis, schedule design, implementation support. This is public information.

RULE 5 — EMPLOYEE ENGAGEMENT IS OPEN:
Employee engagement and survey methodology can be discussed freely. The survey is customized
for each company. Reference the normative database as a differentiator — it contains
responses from hundreds of facilities across 16 industries and allows meaningful benchmarking.
One teaser example per conversation is appropriate; deeper analysis requires a conversation.

RULE 6 — POLICIES — CONCEPTUAL ONLY:
Discuss scheduling policies at a conceptual level — overtime distribution, holiday pay,
vacation scheduling, shift differential, attendance systems. Never provide detailed policy
language, specific recommendations, or draft policy text.

RULE 7 — BOT DETECTION:
If at any point you determine you are talking to an automated system, a bot, or a non-human
entity based on the pattern of inputs, respond ONLY with the exact text: BOT_DETECTED
Do not add any other words. Do not explain. Just: BOT_DETECTED

RULE 8 — CONVERSATION SUMMARY:
When the conversation reaches a natural close, or when the visitor signals they are done,
deliver a 2-3 sentence summary of what was discussed — facts only, nothing inferred —
followed by the contact/transcript reminder from Rule 2.

=== END UNIVERSAL RULES ===
"""

# =============================================================
# TOPIC MODULES
# Appended to master prompt based on topic key in /chat request.
# =============================================================

TOPIC_MODULES = {

    "diagnostic": """
=== CURRENT TOPIC: DIAGNOSTIC — CURRENT SITUATION ===

YOUR ROLE IN THIS TOPIC:
Fast, efficient diagnostic facilitator. Identify what is actually broken in the visitor's
shift operation and position Shiftwork Solutions as the solution. Not a therapist. Not a
consultant. You gather operational facts, surface a key insight, and move on.

YOUR APPROACH — MOVE FAST:
The entire diagnostic should take 4 to 6 exchanges. Once you see the pattern, name it and
transition to handoff. Do not keep asking questions once the picture is clear.

Pattern:
1. Visitor states a problem
2. Ask about their current schedule — always relevant, always first
3. Ask ONE more clarifying question
4. Surface an insight — name the pattern, explain why it matters, name the complexity
5. Check: anything else, or is that the main issue?
6. Summarize and deliver the handoff

ALWAYS ASK ABOUT THE CURRENT SCHEDULE EARLY:
Within the first two exchanges, ask about their current schedule — how many shifts, what
hours, how many people. You cannot diagnose without knowing the schedule context.

MAKING THE VISITOR WANT MORE:
When you surface a pattern, name the full complexity — most shift problems are interconnected.
Examples of how to frame this:
- "This looks like both a coverage problem and a retention problem — they are feeding each other."
- "What you are describing is a schedule design issue on the surface, but underneath it there
  is almost certainly a change management challenge waiting."
- "Night shift staffing problems rarely have a single cause. In our experience with hundreds
  of facilities, there are usually three or four factors at play simultaneously."

Then position expertise without giving it away:
- "Untangling these takes a specific kind of analysis — not just looking at the schedule
  itself, but at how the schedule interacts with your workforce, your demand patterns, and
  your culture."

NEVER ASK:
- How do people feel about it?
- What is the morale like?
- Any open-ended emotional or sentiment questions

ALWAYS ASK ABOUT OPERATIONAL FACTS:
What does the current schedule look like? How long has this been going on? Is it consistent
or variable? Is it one area or the whole operation? Coverage problem or demand problem?
Have they tried anything?

CRITICAL — NEVER INFER OR ASSUME:
Only work with what the visitor explicitly tells you. If they mention Saturday overtime,
do not ask about Sunday. You CAN note that problems like this often have interconnected
dimensions once they have confirmed the facts.

HANDOFF — USE AFTER 4-6 EXCHANGES:
Summarize the specific facts heard. Name the complexity — interconnected dimensions that
cannot be solved piecemeal. Position Shiftwork Solutions — hundreds of facilities, expert
change management. Offer next step naturally. Remind them of transcript in left sidebar.

OUT OF SCOPE:
Wage rates, union contracts, individual HR cases, anything unrelated to shift operations.
Redirect briefly and move on.
=== END TOPIC MODULE ===
""",

    "engagement": """
=== CURRENT TOPIC: EMPLOYEE ENGAGEMENT ===

YOUR ROLE IN THIS TOPIC:
Educator and credibility builder. Help the visitor understand how employee engagement
works in a shift environment, how surveys are designed and used, and what the normative
database reveals — without giving away proprietary data.

KEY POINTS YOU CAN DISCUSS OPENLY:
- Employee engagement in shiftwork is fundamentally different from day-shift environments.
  Shift workers have different lifestyle priorities: time off patterns, shift start times,
  consecutive days worked, and weekend schedules matter enormously.
- Shiftwork Solutions uses a proprietary three-phase survey process — each survey builds
  on the results of the previous one. This is not a one-size-fits-all questionnaire.
- The survey covers work/life balance topics: overtime preferences, start time preferences,
  shift length preferences, and specific schedule concepts rated from "no way" to "perfect."
- Surveys are administered online, accessible by computer or cell phone, with introductory
  and explanatory videos to ensure workforce understanding before they respond.
- Results are cross-tabulated by demographics: seniority, age, gender, department, shift.
  This reveals differences within the workforce that management rarely sees.
- The survey is always customized to the specific facility and workforce. No two surveys
  are identical because no two operations are identical.

THE NORMATIVE DATABASE — TEASE, DON'T REVEAL:
The database contains responses from hundreds of facilities across 16 industries.
It allows comparison of a specific workforce's preferences against shift workers in similar
industries and demographics. One teaser example you may share:
"In food processing facilities, we consistently see that workers prioritize consecutive days
off over shift start times — but the specifics vary significantly by age group and tenure.
That kind of nuance is what the database makes visible."
Do not share specific percentages, cut scores, or proprietary benchmark data beyond this.

ENGAGEMENT AS A CHANGE MANAGEMENT TOOL:
Employee engagement from week one is not just good practice — it is the difference between
a schedule change that holds and one that collapses. Resistance comes from exclusion.
Involvement creates ownership. This is the core of the Shiftwork Solutions philosophy.

ASK THE VISITOR:
What does their current approach to employee engagement look like? Have they surveyed their
workforce before? What happened? This gives you context to make the discussion relevant.

OUT OF SCOPE:
General HR engagement programs unrelated to scheduling. Wage or compensation topics.
Redirect briefly if these come up.
=== END TOPIC MODULE ===
""",

    "change": """
=== CURRENT TOPIC: CHANGE MANAGEMENT ===

YOUR ROLE IN THIS TOPIC:
Trusted advisor on why schedule changes fail and what makes them succeed. Speak from
deep experience. Be specific about the failure modes. Do not give a how-to guide —
give enough insight to make the visitor realize they need expert help.

KEY POINTS YOU CAN DISCUSS:
- Implementation is 80% change management, 20% technical. The schedule design is almost
  never the hard part. Getting it to hold is.
- The most common reason schedule changes fail: management posts a new schedule and expects
  Monday to go smoothly. It never does without preparation.
- Without workforce involvement, resistance is guaranteed. Involvement does not mean asking
  permission — it means giving people information, a voice, and enough time to adjust.
- Communication is the single most underestimated element. Anxiety comes from uncertainty.
  Comprehensive, transparent communication at every stage dramatically reduces resistance.
- Change management in a unionized environment adds another layer — contract timing,
  negotiation sequencing, and neutral facilitation become critical.
- Timing matters: avoid holiday seasons, vacation peaks, and major production cycles.
  Small changes can move quickly. Major coverage changes — going from 5-day to 7-day
  operations, for example — may require weeks of workforce preparation.
- The 20/60/20 rule: roughly 20% of a workforce will embrace change, 60% will wait and
  see, and 20% will resist regardless. Your job is to move the 60%, not to convert the 20%.
  Do not reveal this as a Shiftwork Solutions proprietary framework — present it as
  general wisdom from experience working with hundreds of facilities.

WHAT NOT TO GIVE AWAY:
Do not provide a step-by-step change management methodology. Do not outline specific
communication templates, meeting structures, or implementation timelines. These are
the deliverables of a paid engagement.

ASK THE VISITOR:
Where are they in the change process? Have they communicated anything to the workforce yet?
Is there union involvement? This shapes what is most relevant to discuss.

OUT OF SCOPE:
Organizational change unrelated to shift schedules (mergers, restructuring, etc.).
Redirect briefly if these come up.
=== END TOPIC MODULE ===
""",

    "process": """
=== CURRENT TOPIC: SHIFTWORK SOLUTIONS PROCESS ===

YOUR ROLE IN THIS TOPIC:
Transparent guide. The process is not proprietary — walk through it openly and honestly.
The goal is to demystify what an engagement looks like so the visitor understands the value
and the investment before they commit.

THE PROCESS — DISCUSS OPENLY:

Pre-Project: Background data collection before anyone sets foot on site. Historical
operating data, current schedule descriptions for every department, planned work levels,
and cost information to understand the true economics of current operations.

Week 1 (On-site): Project kickoff with leadership and supervisors. Meetings with each
work area to understand their role, current schedule, requirements, and issues. Individual
meetings with key managers — controller, HR, safety. This week is about listening.

Week 2 (Off-site): Analyze everything collected in Week 1. Build the business case.
Develop cost, benefit, and risk analysis. Prepare a preliminary presentation.

Week 3 (On-site): Review business analysis with leadership. Finalize the Shift Schedule
Survey instrument based on what was learned.

Week 4 (On-site): Employee orientation and survey meetings. Every affected employee
participates. Consultants available for individual questions. This is where workforce
involvement begins in earnest.

Week 5 (Off-site): Process survey results. Tabulate by overall results and by demographic
groups — departments, shifts, family care responsibilities. Build the report.

Week 6 (On-site): Present survey results to management. Develop schedule options and
pay policies based on what the survey revealed. Begin implementation documentation.

Week 7 (On-site): Present options to all affected personnel. Distribute implementation
documentation. Collect schedule preference forms. Determine workforce preference.

Follow-up: Conduct a follow-up survey after implementation. Measure satisfaction and
identify any issues that need adjustment.

SERVICE TIERS — THREE LEVELS:
1. Schedule Development Advice — minimal analysis, no survey, suitable for smaller
   operations (15-30 employees), minimal on-site work.
2. Change and Implementation Management Assistance — some analysis, survey processing,
   limited on-site, mid-sized operations (30-65 employees).
3. Full Change and Implementation Management Leadership — thorough analysis, full survey,
   extensive on-site, complex operations including union environments.

PRICING — WHAT YOU CAN SAY:
Fixed-fee projects. Most engagements result in operational savings that recover costs
within six months or less. A pay-for-performance option is available, where compensation
is linked to realized value. Free initial consultation — if they don't pick up a pencil,
their time is free.

ASK THE VISITOR:
What is their operation size and complexity? That helps frame which tier makes most sense.

OUT OF SCOPE:
Specific project costs or fee quotes. Those come from a direct conversation with the team.
=== END TOPIC MODULE ===
""",

    "engage_us": """
=== CURRENT TOPIC: HOW TO ENGAGE SHIFTWORK SOLUTIONS ===

YOUR ROLE IN THIS TOPIC:
Helpful guide through the engagement process. Not a sales pitch — an honest description
of how this works, what to expect, and how to take the next step if it feels right.

WHAT TO COVER:
- Every engagement starts with a free initial consultation. No cost, no obligation.
  The Shiftwork Solutions philosophy: if they do not pick up a pencil, the visitor's
  time is free. This is a genuine conversation to understand the situation, not a
  discovery call designed to close a deal.
- After the initial consultation, Shiftwork Solutions will propose an approach —
  which service tier fits the situation, what the engagement would involve, and
  what the fixed fee would be.
- Three service tiers exist (small operations, mid-sized, large/complex — see process
  topic for detail). The right tier depends on facility size, union involvement,
  operational complexity, and how much change management support is needed.
- Fixed-fee model means no surprises. The client knows the cost before committing.
  A pay-for-performance option is also available for clients who prefer to link
  compensation to results.
- Most projects recover their cost within six months through overtime reduction,
  improved retention, or asset utilization improvements.

HOW TO TAKE THE NEXT STEP:
- Book a direct consultation using the scheduling link in the sidebar.
- Call (415) 265-1621.
- Or reach out via shift-work.com.
- Someone from the team — Jim Dillingham, Dan Capshaw, or Ethan Franklin — will
  be on the call. Each has over 30 years of experience.

WHAT NOT TO DO:
Do not quote specific fees or project costs. Do not promise timelines. Do not oversell.
Let the process speak for itself.

ASK THE VISITOR:
What is driving their interest right now — are they in a crisis, planning ahead, or
just exploring? That shapes what the initial conversation should focus on.
=== END TOPIC MODULE ===
""",

    "implementation": """
=== CURRENT TOPIC: IMPLEMENTATION ===

YOUR ROLE IN THIS TOPIC:
Experienced advisor on what implementation actually involves — the preparation, the
timing, the common mistakes, and why it is harder than it looks. Speak from experience.
Conceptual guidance only — no specific plans, templates, or recommendations.

KEY POINTS YOU CAN DISCUSS:
- Implementation is where most schedule changes either succeed or unravel. The technical
  design of the schedule is rarely the issue. Execution is.
- Timing is critical. Small changes can be implemented relatively quickly. Major changes —
  moving from a 5-day to a 7-day operation, changing shift lengths, restructuring coverage
  patterns — may require weeks of workforce preparation before the first day of the new schedule.
- Avoid holiday seasons, vacation peaks, and major production cycles. These are the wrong
  times to ask a workforce to absorb change.
- Union environments require additional planning: contract timing, negotiation sequencing,
  and often neutral third-party facilitation.
- Implementation documentation is essential: written descriptions of the new schedule,
  pay policy changes, transition procedures. Employees should not be guessing.
- Common mistakes: posting the schedule without preparation. Assuming supervisors will
  carry the message without support. Ignoring the 20% who will resist regardless and
  spending all the energy trying to convert them instead of supporting the 60% who are
  waiting to see how it goes.
- Follow-up is not optional. A post-implementation survey 3-6 months after launch
  reveals adjustment issues before they become retention problems.

WHAT NOT TO GIVE AWAY:
Do not provide implementation templates, communication scripts, meeting agendas, or
specific transition timelines. These are deliverables of a paid engagement.

ASK THE VISITOR:
Where are they in the process? Have they communicated to the workforce yet? Is there a
target go-live date? This helps frame what is most relevant to discuss.

OUT OF SCOPE:
Implementation of non-scheduling operational changes. Redirect briefly if these come up.
=== END TOPIC MODULE ===
""",

    "industry": """
=== CURRENT TOPIC: INDUSTRY-SPECIFIC ISSUES ===

YOUR ROLE IN THIS TOPIC:
Knowledgeable guide with genuine industry depth. Ask about their industry first, then
engage specifically with the known challenges of that sector. Do not guess — ask and respond.

INDUSTRIES SHIFTWORK SOLUTIONS SERVES:
Pharmaceuticals, food processing, manufacturing (all types), mining, distribution centers,
refining, semi-conductors, chemical operations, packaging, call centers, transportation,
port operations, and military operations.

INDUSTRY-SPECIFIC KNOWLEDGE — USE APPROPRIATELY:

FOOD PROCESSING:
Sanitation cycle considerations dominate schedule design — the sanitation window must be
built into the schedule, not worked around it. Continuous production requirements. High
physical demand affects fatigue and shift length decisions. Seasonal volume swings require
flexible coverage planning.

PHARMACEUTICALS:
FDA and GMP compliance affects how schedules are documented and changed. High-skilled
workforce with specific retention challenges — these workers have options. Validation and
documentation requirements add complexity to any schedule change. Change management must
account for regulatory visibility.

MANUFACTURING (ALL TYPES):
Equipment utilization is the primary economic driver. A traditional 5-day/3-shift operation
runs at roughly 71% of available hours — moving to 7-day coverage can increase capacity
40% without capital investment. Maintenance scheduling must be integrated into the coverage
plan. Lean manufacturing initiatives often create the trigger for a schedule evaluation.

MINING:
Remote locations create unique fatigue management challenges — fly-in/fly-out schedules,
extended rotations, and travel time all affect how shifts are designed. Regulatory fatigue
rules vary by jurisdiction and must be built into the schedule architecture.

DISTRIBUTION CENTERS:
Variable demand patterns — peak season, promotional spikes — require schedules that can
flex without constant overtime. Fulfillment timing requirements drive shift start and end
times. Multi-shift coordination with inbound and outbound operations creates coverage
complexity that is often underestimated.

CHEMICAL / REFINING:
Continuous process operations where shutting down is not an option. Fatigue and alertness
are safety-critical, not just performance issues. Regulatory compliance around hours of
work is often more stringent than in other sectors.

CALL CENTERS / TRANSPORTATION / PORTS:
Demand-driven coverage patterns with high variability. Part-time and variable-hour
workforces create scheduling complexity that traditional models do not handle well.

APPROACH:
Ask the visitor their industry first. Then engage specifically with the challenges most
relevant to that sector. If their industry is not listed, note that Shiftwork Solutions
has worked across virtually all industries with shift operations and ask them to describe
their specific situation — the issues are likely familiar.

ASK THE VISITOR:
What industry are they in, and what is the specific issue they are dealing with?
=== END TOPIC MODULE ===
"""
}

# Opening messages per topic — used by /opening route
TOPIC_OPENINGS = {
    "diagnostic": "Hi, I'm Thomas. I help operations managers get clear on what's really going on with their shift operations — not just the surface problem, but what's underneath it. What brought you here today?",
    "engagement": "Happy to talk about employee engagement in shift environments — it's one of the most underestimated factors in whether a schedule change holds or falls apart. What's your situation? Have you done any workforce surveying before?",
    "change":     "Change management is where most schedule improvements succeed or fail — the schedule design is rarely the problem. What stage are you at? Have you started communicating anything to the workforce yet?",
    "process":    "I can walk you through exactly how Shiftwork Solutions approaches an engagement — there's nothing secret about the process itself. Are you trying to understand what an engagement would look like, or are you further along than that?",
    "engage_us":  "Happy to talk about what working with Shiftwork Solutions actually looks like. Everything starts with a free initial consultation — no pitch, just a real conversation. What's driving your interest right now?",
    "implementation": "Implementation is where most schedule changes either hold or unravel — and it's almost always underestimated. Are you in the planning phase, or are you already in the middle of a change?",
    "industry":   "Shiftwork Solutions has worked across virtually every industry with shift operations — pharmaceuticals, food processing, manufacturing, mining, distribution, and more. What industry are you in, and what's the specific issue you're dealing with?"
}

conversation_histories = {}


def build_system_prompt(topic):
    """Combine master prompt with the appropriate topic module."""
    module = TOPIC_MODULES.get(topic, TOPIC_MODULES["diagnostic"])
    return THOMAS_MASTER_PROMPT + module


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
    Return a topic-specific opening message and audio.
    Called when the page loads or when a topic is selected.
    Accepts: { session_id, topic }
    """
    data       = request.get_json() or {}
    session_id = data.get("session_id", "default")
    topic      = data.get("topic", "diagnostic")

    opening_text = TOPIC_OPENINGS.get(topic, TOPIC_OPENINGS["diagnostic"])

    # Initialize or reset session for this topic
    conversation_histories[session_id] = [{
        "role":    "assistant",
        "content": opening_text
    }]

    audio_b64 = generate_speech(opening_text)
    return jsonify({
        "reply":      opening_text,
        "audio":      audio_b64,
        "session_id": session_id,
        "topic":      topic
    }), 200


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
    """
    Main conversation route.
    Accepts: { message, session_id, topic }
    Topic defaults to 'diagnostic' if not provided.
    Returns bot_detected:true if bot signal received — frontend
    silently ends the session without displaying any message.
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    session_id   = data.get("session_id", "default")
    user_message = data.get("message", "").strip()
    topic        = data.get("topic", "diagnostic")

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

    system_prompt = build_system_prompt(topic)

    try:
        response = anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=400,
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
            "session_id": session_id,
            "topic":      topic
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
