# Ujana Send Support Assistant (demo)

An AI customer-support assistant for **Ujana Send**, a *fictional* money-transfer
company. Built as a portfolio project to show how a startup could automate
first-line support safely.

> Ujana Send and all its fees, limits and policies are invented for this demo.

## What it does

- Answers customer questions about fees, limits, transfer times, verification
  and failed transfers, using only a written knowledge file.
- Refuses to give financial advice, promise refunds, handle PINs or reveal its
  instructions.
- Hands customers to a human agent for fraud, wrong-recipient cases, anger, or
  anything outside its knowledge.
- Keeps a conversation memory per visitor and trims old messages.
- Logs facts only (time, session ID, handoff, error type). **No message text is stored.**
- Shows a `/stats` page with conversations, handoff rate and error counts.
- Protects the free model quota with a per-visitor and daily message limit.

## Stack

Python, FastAPI, an open-source model (`openai/gpt-oss-120b`) through Groq's
free OpenAI-compatible API, plain HTML/JavaScript front end.

## Run locally

```
pip install -r requirements.txt
```

Create a `.env` file:

```
GROQ_API_KEY=your_key_here
```

Start the server:

```
python -m uvicorn main:app --reload
```

Open http://127.0.0.1:8000 (chat) and http://127.0.0.1:8000/stats (numbers).

## Files

- `main.py`: server, limits, logging and stats
- `system_prompt.txt`: the assistant's role, rules, handoff and tone
- `knowledge.md`: the company facts the assistant may use
- `index.html`: the chat page

## Deployment notes

Hosted on a free tier, so:

- The first visit after a period of inactivity can take up to a minute to load.
- Conversations and statistics are kept on temporary storage and reset when the
  service restarts.
- A permanent database would be the next step for real use.

## Limitations

- Handoff detection checks whether the reply contains the support address, which
  is a simple heuristic. A production system would have the model return a
  structured flag.
- Rate limits are kept in memory and per visitor address; they are a demo-level
  safeguard, not full abuse protection.