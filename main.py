import html
import json
import os
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import openai
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from openai import OpenAI
from pydantic import BaseModel, Field

app = FastAPI()
load_dotenv()

client = OpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1",
)

BASE_DIR = Path(__file__).parent
LOG_PATH = BASE_DIR / "chat_log.jsonl"

knowledge = (BASE_DIR / "knowledge.md").read_text(encoding="utf-8")
prompt_template = (BASE_DIR / "system_prompt.txt").read_text(encoding="utf-8")
SYSTEM_PROMPT = prompt_template.replace("__KNOWLEDGE__", knowledge)

# Limits (protect the free Groq quota and the server's memory) 
MAX_SESSIONS = 500          # keep at most this many conversations in memory
VISITOR_LIMIT = 20          # messages allowed per visitor...
VISITOR_WINDOW = 600        # ...in this many seconds (10 minutes)
DAILY_LIMIT = 500           # total messages per day across all visitors

histories = {}
visitor_hits = defaultdict(deque)
daily = {"day": None, "count": 0}


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: Optional[str] = None


# ---------------------------------------------------------------- logging
def log_event(session_id, handed_off, error=None):
    record = {
        "time": datetime.now(timezone.utc).isoformat(),
        "session_id": session_id,
        "handed_off": handed_off,
        "error": error,
    }
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except OSError as e:
        # A logging problem must never break the customer's chat.
        print("Logging failed:", repr(e))


# ------------------------------------------------------------ rate limits
def client_ip(request: Request) -> str:
    # Behind Render's proxy, the real visitor address is in X-Forwarded-For.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def check_limits(ip: str):
    """Return None if allowed, or a short code saying which limit was hit."""
    now = time.time()
    hits = visitor_hits[ip]
    while hits and now - hits[0] > VISITOR_WINDOW:
        hits.popleft()
    if len(hits) >= VISITOR_LIMIT:
        return "visitor_limit"

    today = datetime.now(timezone.utc).date().isoformat()
    if daily["day"] != today:
        daily["day"] = today
        daily["count"] = 0
    if daily["count"] >= DAILY_LIMIT:
        return "daily_limit"

    hits.append(now)
    daily["count"] += 1
    return None


# ------------------------------------------------------------------ stats
def compute_stats():
    total = 0
    errors = 0
    handoffs = 0
    sessions = set()
    handoff_sessions = set()
    error_types = {}

    try:
        with open(LOG_PATH, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue

                total += 1
                sid = record.get("session_id")
                if sid:
                    sessions.add(sid)

                if record.get("error") is not None:
                    errors += 1
                    name = record["error"]
                    error_types[name] = error_types.get(name, 0) + 1
                elif record.get("handed_off"):
                    handoffs += 1
                    if sid:
                        handoff_sessions.add(sid)
    except FileNotFoundError:
        pass

    answered = total - errors
    return {
        "conversations": len(sessions),
        "handoff_conversations": len(handoff_sessions),
        "total": total,
        "answered": answered,
        "errors": errors,
        "handoffs": handoffs,
        "error_types": error_types,
        "handoff_rate": (handoffs / answered * 100) if answered else None,
    }


STATS_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>Ujana Send demo: statistics</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,400;12..96,500;12..96,700&display=swap" rel="stylesheet">
<style>
  :root { --paper: #F2F5F3; --surface: #FFFFFF; --ink: #0F2E33; --muted: #5A6B68;
          --line: #D5DEDA; --teal: #12525A; --accent-text: #12525A; --sun: #FFB43A; }
  @media (prefers-color-scheme: dark) {
    :root { --paper: #0B1A1D; --surface: #12272B; --ink: #E8F0EE; --muted: #9DB2AE;
            --line: #264245; --teal: #1D7580; --accent-text: #8FD3DB; }
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--paper); color: var(--ink); line-height: 1.5;
         font-family: "Bricolage Grotesque", system-ui, -apple-system, "Segoe UI", sans-serif; }
  .page { max-width: 720px; margin: 0 auto; padding: 1.5rem 1rem 3rem; }
  .brand { display: flex; align-items: center; gap: .75rem; }
  .mark { position: relative; width: 34px; height: 34px; border-radius: 50%;
          background: var(--teal); flex: none; }
  .mark::after { content: ""; position: absolute; width: 10px; height: 10px;
                 border-radius: 50%; background: var(--sun); right: 6px; top: 6px; }
  h1 { margin: 0; font-size: 1.3rem; letter-spacing: -0.01em; line-height: 1.15; }
  .sub { margin: 0; color: var(--muted); font-size: .9rem; }
  .note { margin: 1.5rem 0 0; padding: .15rem 0 .15rem .75rem;
          border-left: 3px solid var(--sun); color: var(--muted); font-size: .9rem; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
          gap: 1.75rem 1.5rem; margin: 2rem 0; }
  .card { border-top: 2px solid var(--teal); padding-top: .6rem; }
  .value { font-size: 2.4rem; font-weight: 700; letter-spacing: -0.02em; line-height: 1.1; }
  .label { color: var(--muted); font-size: .92rem; margin-top: .15rem; }
  h2 { font-size: 1.05rem; margin: 2rem 0 .5rem; }
  table { border-collapse: collapse; width: 100%; }
  td, th { text-align: left; padding: .5rem .25rem; border-bottom: 1px solid var(--line); }
  th { color: var(--muted); font-weight: 500; font-size: .9rem; }
  a { color: var(--accent-text); }
  a:focus-visible { outline: 2px solid var(--accent-text); outline-offset: 2px; }
</style>
</head>
<body>
<div class="page">
  <div class="brand">
    <span class="mark" aria-hidden="true"></span>
    <div>
      <h1>Ujana Send</h1>
      <p class="sub">Support assistant statistics</p>
    </div>
  </div>
  <p class="note">Fictional demo company. These numbers cover activity since the
  demo last restarted. No message text is stored.</p>
  <div class="grid">__CARDS__</div>
  __ERRORS__
  <p><a href="/">Back to the chat</a></p>
</div>
</body>
</html>"""


def card(label, value):
    return (
        '<div class="card"><div class="value">'
        + html.escape(str(value))
        + '</div><div class="label">'
        + html.escape(label)
        + "</div></div>"
    )


@app.get("/stats", response_class=HTMLResponse)
def stats():
    s = compute_stats()
    rate = "n/a" if s["handoff_rate"] is None else f"{s['handoff_rate']:.1f}%"
    cards = "".join(
        [
            card("Conversations", s["conversations"]),
            card("Conversations with a handoff", s["handoff_conversations"]),
            card("Messages answered", s["answered"]),
            card("Handoff rate (of answered messages)", rate),
            card("Errors and blocked requests", s["errors"]),
        ]
    )
    if s["error_types"]:
        rows = "".join(
            "<tr><td>" + html.escape(name) + "</td><td>" + str(count) + "</td></tr>"
            for name, count in s["error_types"].items()
        )
        errors_html = "<h2>Errors by type</h2><table><tr><th>Type</th><th>Count</th></tr>" + rows + "</table>"
    else:
        errors_html = ""
    return STATS_TEMPLATE.replace("__CARDS__", cards).replace("__ERRORS__", errors_html)


# ----------------------------------------------------------------- routes
@app.get("/")
def home():
    return FileResponse(BASE_DIR / "index.html")


@app.get("/chat-page")
def page():
    return FileResponse(BASE_DIR / "index.html")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat")
def chat(req: ChatRequest, request: Request):
    limit_hit = check_limits(client_ip(request))
    if limit_hit:
        log_event(req.session_id, handed_off=False, error=limit_hit)
        if limit_hit == "visitor_limit":
            detail = "You're sending messages quickly. Please wait a few minutes and try again."
        else:
            detail = "The demo has reached its daily limit. Please try again tomorrow."
        raise HTTPException(status_code=429, detail=detail)

    if req.session_id is None:
        if len(histories) >= MAX_SESSIONS:
            oldest = next(iter(histories))
            del histories[oldest]
        session_id = str(uuid.uuid4())
        histories[session_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
    elif req.session_id in histories:
        session_id = req.session_id
    else:
        raise HTTPException(status_code=404, detail="Unknown session")

    history = histories[session_id]
    history.append({"role": "user", "content": req.message})

    try:
        response = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=history,
        )
    except openai.RateLimitError as e:
        history.pop()
        print("Rate limit:", repr(e))
        log_event(session_id, handed_off=False, error="rate_limit")
        raise HTTPException(
            status_code=429,
            detail="The assistant is busy. Please try again later.",
        )
    except openai.AuthenticationError as e:
        history.pop()
        print("Auth error:", repr(e))
        log_event(session_id, handed_off=False, error="auth_error")
        raise HTTPException(
            status_code=503,
            detail="The assistant is temporarily unavailable. Please contact our support team.",
        )
    except Exception as e:
        history.pop()
        print("Groq error:", repr(e))
        log_event(session_id, handed_off=False, error="provider_error")
        raise HTTPException(
            status_code=503,
            detail="The assistant is currently unavailable. Please try again later.",
        )

    reply = response.choices[0].message.content

    history.append({"role": "assistant", "content": reply})

    if len(history) > 10:
        histories[session_id] = history[:1] + history[-8:]

    handed_off = "support@ujanasend.example" in reply
    log_event(session_id, handed_off)

    return {"reply": reply, "session_id": session_id}