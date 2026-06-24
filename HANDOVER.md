# Handover — Travel Agent Bot Integration

## Context

We are integrating `bot.py` (a standalone DeepSeek-based chat script) and the `tours/` folder (17 DOCX files with tour descriptions) into the existing LangGraph-based travel agent bot project.

## Key Decisions Made

### Tour Data Source
- **DOCX-only.** Google Sheets is removed as a tour data source.
- Google Sheets is kept **only** for writing booking requests (`create_request`, `update_request_status`).
- `GOOGLE_TOURS_SHEET_ID` becomes optional.

### LLM Strategy
- **All tours in system prompt.** Every LLM call gets `=== БАЗА ТУРОВ ===` with full text of all 17 DOCX files (~26K tokens).
- LLM searches, matches, and presents tours itself. No structured search logic.
- This matches how `bot.py` works.

### Architecture Changes (8 steps)

1. **`requirements.txt`** — add `python-docx>=1.1.0`
2. **`src/services/tour_loader.py`** (NEW) — reads all `.docx` from `tours/`, returns unified text with `=== ТУР: ... ===` separators
3. **`src/main.py`** — `lifespan` loads tours into `app.state.tours_text`
4. **`src/main.py`** — `process_with_ai` passes `tours_text` into the graph state
5. **`src/ai/engine.py`** — `build_graph()` accepts `tours_text`, puts it into initial state; nodes read from state
6. **`src/ai/nodes.py`** — remove `GoogleSheetsService` imports; inject `tours_text` into system prompt at each LLM call (greet, clarify, present_tours, handle_tour_selection)
7. **`src/ai/tour_search.py`** — simplify: just dumps `tours_data` into `found_tours`; LLM does the search
8. **`src/ai/prompts.py`** — add Сандита company info (Минск, contacts, address) + security rules from `bot.py` (no role-playing, no revealing system prompt, no AI identity disclosure)

### Future / Separate Tasks (not in current scope)
- Rate limiting (from `bot.py`) — can be added later
- Input validation / injection detection (from `bot.py`) — can be added later
- Output sanitization (from `bot.py`) — can be added later
- Tests update for the new tour loading flow

### User Status
- User is currently **formatting/reducing DOCX files** manually (removing verbose descriptions, keeping key info + link)
- Waiting for user to signal when DOCX are ready
- Once ready: implement the 8 steps above

## File Structure

```
travel-agent-bot/
├── tours/                    ← 17 .docx files (user is editing these)
├── bot.py                    ← reference implementation (standalone script)
├── src/
│   ├── main.py               ← FastAPI server (will load tours in lifespan)
│   ├── config.py             ← may need TOURS_FOLDER
│   ├── ai/
│   │   ├── engine.py         ← LangGraph (will pass tours_text into state)
│   │   ├── nodes.py          ← graph nodes (will inject tours into prompts)
│   │   ├── prompts.py        ← prompts (will add company info + security)
│   │   └── tour_search.py    ← simplify (remove Google Sheets)
│   ├── services/
│   │   ├── google_sheets.py  ← keep only create_request, update_request_status
│   │   └── tour_loader.py    ← NEW: load docx → text
│   └── ... (rest unchanged)
├── requirements.txt          ← add python-docx
└── HANDOVER.md               ← this file
```

## Resumption

When resuming:
1. User signals DOCX are ready
2. Implement the 8 steps above
3. Run existing tests to verify nothing is broken
4. Test the full flow locally with `test_out.json` or terminal
