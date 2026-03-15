# shift-work-diagnostic
<!-- Created: 2026-03-15 | Last Updated: 2026-03-15 -->

**Fred** — AI Diagnostic Avatar for Shiftwork Solutions LLC

## What This Is

Fred is a conversational diagnostic facilitator, not a chatbot.
He asks questions, listens, reflects back, and helps operations managers
get clear on their real problem — before handing off to Shiftwork Solutions.

## Build Phases

- [x] Phase 1 — Text prototype with Claude backend (current)
- [ ] Phase 2 — ElevenLabs voice
- [ ] Phase 3 — HeyGen avatar video
- [ ] Phase 4 — Email/phone verification gate

## File Structure
```
shift-work-diagnostic/
├── app.py                  # Flask backend — Fred conversation engine
├── requirements.txt        # Python dependencies
├── render.yaml             # Render deployment config
├── .gitignore
├── README.md
└── templates/
    └── index.html          # Fred chat UI
```

## Environment Variables

Set these in the Render dashboard — never commit them to GitHub:

| Variable | Description |
|---|---|
| ANTHROPIC_API_KEY | Claude API key (from Anthropic console) |

## Deployment

1. Push to GitHub (main branch)
2. Render auto-deploys via GitHub integration
3. Set ANTHROPIC_API_KEY in Render environment variables
4. Health check: GET /health

## Guardrails

Fred will never:
- Recommend a schedule pattern
- Calculate costs or staffing levels
- Suggest policy language
- Give away Jim Dillingham's methodology

## Local Development
```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=your_key_here
python app.py
```

Visit http://localhost:5000

<!-- I did no harm and this file is not truncated -->
