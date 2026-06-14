# MLOps Assignment Report

---

## Phase 1 — Serving Configuration

**Local development:** Nebius Token Factory API (OpenAI-compatible endpoint)
using `Qwen/Qwen3-30B-A3B-Instruct-2507` as a hosted backend.
**Production target:** vLLM on 1× H100 80GB.

### vLLM flags (H100 configuration — `scripts/start_vllm.sh`)

| Flag | Value | Reason |
|---|---|---|
| `--dtype` | `bfloat16` | H100 native format; no quality loss vs fp32 for SQL generation |
| `--max-model-len` | `8192` | Prompts are 1.5–3K tokens (schema + question); capping context frees KV cache headroom for concurrency |
| `--gpu-memory-utilization` | `0.92` | Leaves ~6GB headroom for model weights; gives KV cache maximum VRAM |
| `--max-num-seqs` | `64` | Qwen3-30B-A3B is MoE (~3B active params per forward pass); compute per token is low so higher concurrency is affordable vs a dense 30B |
| `--enable-prefix-caching` | on | Every query against the same DB shares an identical schema preamble — avoids re-prefilling those tokens on each request |
| `--enable-chunked-prefill` | on | Prevents long schema prefills from blocking decode steps of concurrent requests |
| `--trust-remote-code` | on | Required for Qwen3 MoE architecture |
| `--disable-log-requests` | on | Removes per-request stdout overhead under load |

**Note:** Flags were chosen based on workload analysis (MoE architecture,
1.5–3K token prompts, short structured outputs, 2–3 sequential LLM calls per
request) but could not be validated locally without GPU hardware. They will be
exercised and iterated on during Phase 6 load testing on the real H100 endpoint.

### Manual query results (5 questions from `evals/eval_set.jsonl`)

Schema was injected at runtime via `render_schema()` which reads real CREATE TABLE
statements directly from the SQLite files.

| # | Question | DB | Outcome | Notes |
|---|---|---|---|---|
| 1 | Australian GP coordinates | formula_1 | ✅ Near-correct | Missing `DISTINCT` → 11 duplicate rows instead of 1 |
| 2 | Ajax superpowers | superhero | ✅ Correct | 5 rows returned, matches gold |
| 3 | Top 5 schools by enrollment | california_schools | ✅ Correct | Correct JOIN and ORDER BY |
| 4 | Average crimes 1995 | financial | ❌ Wrong | Used `A14` instead of `A15` → returned NULL |
| 5 | Male clients in Praha | financial | ❌ Wrong | Used lowercase `'m'` instead of `'M'` → returned 0 instead of 339 |

**Key observations:**

3/5 queries correct or near-correct with schema injection. Two failure modes
worth noting:

- **NULL result (Q4):** model picked the wrong column (`A14` vs `A15`). A verify
  node should flag a NULL aggregate as implausible.
- **Zero rows (Q5):** case-sensitive string comparison (`'m'` vs `'M'`) returned
  0 when rows clearly exist. Zero rows on a counting question is a strong signal
  for the verifier to trigger a revise.
- **Duplicate rows (Q1):** missing `DISTINCT` returns 11 identical coordinate
  pairs. Also detectable — 11 rows all identical is suspicious for a coordinates
  lookup.

All three failure modes are detectable signals the verify node can act on,
which directly motivates the agent loop in Phase 3.