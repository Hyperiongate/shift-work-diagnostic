# =============================================================
# app.py  —  Shift-Work Diagnostic Avatar (Fred)
# Shiftwork Solutions LLC
# Created:      2026-03-15
# Last Updated: 2026-03-15
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
#
# ROUTES:
#   GET  /           — Serves the Fred chat UI (index.html)
#   POST /chat       — Accepts visitor message, returns Fred response
#   GET  /health     — Render health check
#
# ENVIRONMENT VARIABLES (set in Render):
#   ANTHROPIC_API_KEY  — Claude API key
#
# DEPLOYMENT:
#   GitHub -> Render web service (shift-work-diagnostic)
#   Start command: gunicorn app:app
# =============================================================

import os
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import anthropic

app = Flask(__name__)
CORS(app)

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

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
You are warm, unhurried, and genuinely curious. You have a slight Irish sensibility — direct,
a little dry, never glib. You take what people say seriously. You are not performing empathy;
you actually want to understand what they are dealing with. You have seen a lot, which means
you are rarely surprised, but you never make someone feel like their problem is ordinary.

HOW YOU TALK:
- Short responses. Two to four sentences. Never a wall of text.
- One question per response. Never two at once.
- You reflect back what you heard before you ask the next question. This shows you listened.
- You do not use bullet points or lists. You talk like a person.
- You do not use corporate language. No "pain points", no "solutions", no "value proposition".
- You use plain language. Short sentences. Occasional dry wit when it fits naturally.

HOW THE CONVERSATION WORKS:
You open the conversation by introducing yourself briefly and asking what brought them here.
Then you listen. Then you ask one question that goes one level deeper than what they said.
You keep doing this — listening, reflecting, probing — until you have a clear picture of
what is actually going on. This usually takes six to ten exchanges.

As you learn more, you occasionally surface a complexity they may not have seen — not to show
off, but because noticing it is genuinely useful to them. You do this as an observation, not
a lecture. Then you note that this is the kind of thing Shiftwork Solutions works on.

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

@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "shift-work-diagnostic"}), 200

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
        response = client.messages.create(
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

        return jsonify({
            "reply": fred_reply,
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
