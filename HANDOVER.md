# DeepPrep System Handover

> Updated: 2026-07-19

## Quick Start

```bash
cd "c:\Users\Administrator\Desktop\DeepPrep - 智能备考平台"
streamlit run app.py
```

Open http://localhost:8501 in browser.

## Demo Accounts for Interviewers

| Username | Password | What's Inside |
|----------|----------|---------------|
| `demo` | `demo123` | 5 questions (Math x2, English x1, Physics x1, Chemistry x1), 3 mastered knowledge points, varied mastery levels |

Interviewers can experience every feature without registering or uploading images.

## Production URL

https://deepprep.streamlit.app (auto-deploys from GitHub when pushed)

## Git Status

9 commits ahead of origin/main. Push blocked by firewall — run when network is available:

```bash
git push origin main
```

## Project Structure

```
├── app.py              # Main application (~2850 lines, refactored)
│   ├── render_dashboard()     # Homepage dashboard
│   ├── render_login_view()    # Login / Register
│   ├── render_smart_upload()  # Photo-based problem solving
│   ├── render_mistake_vault() # Mistake bank
│   ├── render_review_mode()   # Spaced repetition review
│   ├── render_knowledge_graph()# Knowledge mastery graph
│   └── render_learning_stats()# Learning statistics
├── ai_utils.py         # AI module (OCR, solving, judging, similar questions, Q&A)
├── db_manager.py       # Database layer (SQLite, context manager pattern)
├── requirements.txt    # Python dependencies
├── mistakes.db         # SQLite database (gitignored)
├── .env                # API Key (gitignored)
└── CLAUDE.md           # Project collaboration guidelines
```

## Key Technical Decisions

- **AI Backend**: SiliconFlow API (Qwen series), with Chinese-friendly error messages
- **State Management**: Streamlit session_state, dual-stage state machine (answering / feedback)
- **Review Algorithm**: SM-2 variant: wrong → 10min, correct x1 → 1 day, correct x2 → 7 days, correct x3 → 15 days archive
- **Data Isolation**: Multi-user data isolation via user_id

## Roadmap

| Stage | Tasks | Status |
|-------|-------|--------|
| Stage 1 | Deploy + Core Flow Testing | Done |
| Stage 2 | Product Polish (Dashboard, Sidebar, Login, AI Error Handling) | Done (pending push) |
| Stage 3 | Documentation (PRD, User Stories, Competitive Analysis, Demo Video) | Next |
| Stage 4 | Final Checks (Public Repo, Resume, Interview Prep) | Planned |
