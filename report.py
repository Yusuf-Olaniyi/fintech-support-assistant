import json
from pathlib import Path

LOG_PATH = Path(__file__).parent / "chat_log.jsonl"

total = 0
handoffs = 0
errors = 0
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
            except json.JSONDecodeError as e:
                print("Skipping unreadable line:", repr(e))
                continue

            total += 1
            sessions.add(record["session_id"])

            if record["error"] is not None:
                errors += 1
                error_types[record["error"]] = error_types.get(record["error"], 0) + 1
            elif record["handed_off"]:
                handoffs += 1
                handoff_sessions.add(record["session_id"])
except FileNotFoundError:
    print("No log file yet. Chat with the bot first, then run this again.")
    raise SystemExit

answered = total - errors

if total == 0:
    print("No conversations logged yet.")
else:
    print(f"Conversations: {len(sessions)}")
    print(f"Conversations with a handoff: {len(handoff_sessions)}")
    print(f"Total messages: {total}")
    print(f"Answered by the bot: {answered}")
    print(f"Errors: {errors}")
    for name, count in error_types.items():
        print(f"  - {name}: {count}")
    if answered > 0:
        print(f"Handoff rate (of answered messages): {handoffs / answered * 100:.1f}%")