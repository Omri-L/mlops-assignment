"""Eval runner using execution accuracy.

Reads evals/eval_set.jsonl, calls the agent at AGENT_URL on each question,
then compares the agent's SQL output to the gold SQL by *executed rows*
(canonicalized: sorted, stringified, None-coerced to empty).

Helpers (run_sql / canonicalize / matches) are provided. You implement
eval_one() and summarize().

Run:
    uv run python evals/run_eval.py --out results/eval_baseline.json
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EVAL_FILE = ROOT / "evals" / "eval_set.jsonl"
DEFAULT_OUT_FILE = ROOT / "results" / "eval_baseline.json"
DB_DIR = ROOT / "data" / "bird"
AGENT_URL_DEFAULT = "http://localhost:8001/answer"


# ---------- Helpers (provided) -----------------------------------------

def run_sql(db_id: str, sql: str, timeout: float = 5.0) -> tuple[bool, list[tuple] | None, str | None]:
    """Run sql against db_id in read-only mode. Returns (ok, rows, error)."""
    path = DB_DIR / f"{db_id}.sqlite"
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=timeout) as conn:
            cur = conn.execute(sql)
            rows = cur.fetchall()
            return True, rows, None
    except Exception as e:  # noqa: BLE001
        return False, None, f"{type(e).__name__}: {e}"


def canonicalize(rows: list[tuple] | None) -> list[tuple] | None:
    """Sort rows; coerce cells to str; None -> ''."""
    if rows is None:
        return None
    return sorted(tuple("" if c is None else str(c) for c in row) for row in rows)


def matches(gold_rows: list[tuple] | None, pred_rows: list[tuple] | None) -> bool:
    if gold_rows is None or pred_rows is None:
        return False
    return canonicalize(gold_rows) == canonicalize(pred_rows)


# ---------- Implement these (Phase 5) ----------------------------------

MAX_EVAL_ITERATIONS = 3  # must match MAX_ITERATIONS in agent/graph.py


def eval_one(question: dict, agent_url: str) -> dict:
    """Score one question. Return a dict capturing per-iteration correctness.

    For each of the MAX_EVAL_ITERATIONS slots we record whether the SQL the
    agent had at that point (after carry-forward) produced the correct rows.
    """
    q = question["question"]
    db_id = question["db_id"]
    gold_sql = question["gold_sql"]

    # Run the gold SQL once to get the reference row set.
    gold_ok, gold_rows, gold_err = run_sql(db_id, gold_sql)

    # Call the agent.
    try:
        resp = httpx.post(
            agent_url,
            json={"question": q, "db": db_id},
            timeout=120.0,
        )
        resp.raise_for_status()
        agent_resp = resp.json()
    except Exception as e:  # noqa: BLE001
        return {
            "question": q,
            "db_id": db_id,
            "gold_sql": gold_sql,
            "gold_ok": gold_ok,
            "gold_error": gold_err,
            "agent_iterations": 0,
            "agent_ok": False,
            "iter_results": [],
            "error": str(e),
        }

    # history: [{"node": "generate_sql"|"revise", "sql": "..."}, ...]
    history = agent_resp.get("history", [])
    iter_sqls = [entry["sql"] for entry in history]

    # Apply carry-forward: fill up to MAX_EVAL_ITERATIONS slots.
    # If the agent stopped early (verify said ok at iter j < MAX), we reuse
    # that SQL for all later slots.
    filled_sqls: list[str] = []
    for k in range(MAX_EVAL_ITERATIONS):
        if k < len(iter_sqls):
            filled_sqls.append(iter_sqls[k])
        else:
            filled_sqls.append(filled_sqls[-1] if filled_sqls else "")

    # Evaluate each slot against the gold row set.
    iter_results = []
    for k, sql in enumerate(filled_sqls, 1):
        pred_ok, pred_rows, pred_err = run_sql(db_id, sql)
        correct = matches(gold_rows, pred_rows) if (gold_ok and pred_ok) else False
        iter_results.append({
            "iter": k,
            "sql": sql,
            "correct": correct,
            "sql_ok": pred_ok,
            "error": pred_err,
        })

    return {
        "question": q,
        "db_id": db_id,
        "gold_sql": gold_sql,
        "gold_ok": gold_ok,
        "gold_error": gold_err,
        "agent_iterations": agent_resp.get("iterations", 0),
        "agent_ok": agent_resp.get("ok", False),
        "iter_results": iter_results,
        "error": None,
    }


def summarize(results: list[dict]) -> dict:
    """Aggregate per-question results.

    Per-iteration carry-forward: if the agent terminated at iteration j < k
    (verify said ok at j, or it hit MAX_ITERATIONS at j < k), treat the
    question's iteration-k result as identical to its iteration-j result.
    The agent stopped emitting; whatever it had at termination is what
    would have been served had we polled at iteration k.
    """
    total = len(results)
    if total == 0:
        return {"total": 0}

    # Per-iteration pass rate.
    per_iter: dict[str, float] = {}
    for k in range(1, MAX_EVAL_ITERATIONS + 1):
        correct = sum(
            1 for r in results
            if any(ir["iter"] == k and ir["correct"] for ir in r.get("iter_results", []))
        )
        per_iter[f"iter_{k}"] = round(correct / total, 4)

    # Overall = final iteration (the SQL that was actually served).
    overall = per_iter.get(f"iter_{MAX_EVAL_ITERATIONS}", 0.0)

    # How many questions triggered at least one revise.
    revise_count = sum(1 for r in results if r.get("agent_iterations", 0) > 1)

    avg_iterations = sum(r.get("agent_iterations", 0) for r in results) / total

    return {
        "total": total,
        "overall_pass_rate": overall,
        "per_iter_pass_rate": per_iter,
        "revise_triggered_count": revise_count,
        "revise_triggered_rate": round(revise_count / total, 4),
        "avg_iterations": round(avg_iterations, 2),
    }


# ---------- Main (provided) --------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval-set", type=Path, default=DEFAULT_EVAL_FILE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT_FILE)
    parser.add_argument("--agent-url", default=AGENT_URL_DEFAULT)
    args = parser.parse_args()

    questions = [json.loads(line) for line in args.eval_set.read_text().splitlines() if line.strip()]
    print(f"Loaded {len(questions)} eval questions from {args.eval_set}")

    results: list[dict] = []
    t0 = time.monotonic()
    for i, q in enumerate(questions, 1):
        print(f"[{i}/{len(questions)}] {q['db_id']}: {q['question'][:60]}...", flush=True)
        results.append(eval_one(q, args.agent_url))
    elapsed = time.monotonic() - t0

    summary = summarize(results)
    out = {
        "summary": summary,
        "wall_clock_seconds": elapsed,
        "results": results,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2))
    print(f"Wrote {args.out}")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
