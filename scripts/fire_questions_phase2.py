"""Fire the first 10 questions from evals/eval_set.jsonl through the agent.

Usage:
    python scripts/fire_questions.py

The agent server must be running:
    uv run uvicorn agent.server:app --host 0.0.0.0 --port 8001
"""

import json
import time
from pathlib import Path

import requests

AGENT_URL = "http://localhost:8001/answer"
EVAL_FILE = Path(__file__).parent.parent / "evals" / "eval_set.jsonl"
N = 10


def main() -> None:
    questions = []
    with open(EVAL_FILE) as f:
        for line in f:
            line = line.strip()
            if line:
                questions.append(json.loads(line))
            if len(questions) == N:
                break

    print(f"Firing {len(questions)} questions at {AGENT_URL}\n")
    print("=" * 60)

    for i, item in enumerate(questions, 1):
        payload = {
            "question": item["question"],
            "db": item["db_id"],
            "tags": {"phase": "baseline_h100", "source": "eval_set"},
        }

        t0 = time.time()
        try:
            resp = requests.post(AGENT_URL, json=payload, timeout=120)
            resp.raise_for_status()
            data = resp.json()
            elapsed = time.time() - t0

            status = "✅" if data["ok"] else "❌"
            print(f"[{i:02d}] {status}  {item['db_id']}  ({elapsed:.1f}s)")
            print(f"     Q: {item['question'][:80]}")
            print(f"     SQL: {data['sql'][:100].replace(chr(10), ' ')}")
            print(f"     rows={data['rows'][:3]}  iterations={data['iterations']}")
        except Exception as e:
            elapsed = time.time() - t0
            print(f"[{i:02d}] 💥  {item['db_id']}  ({elapsed:.1f}s)")
            print(f"     Q: {item['question'][:80]}")
            print(f"     ERROR: {e}")

        print()

    print("=" * 60)
    print("Done. Check http://localhost:3001 for traces.")


if __name__ == "__main__":
    main()
