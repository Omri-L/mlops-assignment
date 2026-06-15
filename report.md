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

### Screenshot - TBD

---

## Phase 2: Observability Dashboard

The dashboard is organized around three questions a person on call needs to answer immediately:
**Is the system slow? Is it keeping up? Is memory OK?**

---

### Metric types and PromQL patterns

vLLM exposes three metric types, each requiring a different PromQL treatment:

- **Gauge**: a live snapshot value (e.g. queue depth). Read directly, no transformation.
- **Counter**: monotonically increasing total (e.g. requests served). Wrap in `rate(metric[1m])` to get a per-second rate.
- **Histogram**: records a distribution across buckets (e.g. latency). Use `histogram_quantile(0.95, rate(metric_bucket[5m]))` to get a percentile. Latency panels use a longer `[5m]` window than throughput panels (`[1m]`) because percentile estimates need more samples to be statistically stable.

---

### Why these specific metrics

#### Latency

Three panels: E2E latency (P50/P95/P99), TTFT, TPOT.

E2E latency is the SLO metric. TTFT (time to first token) and TPOT (time per output token) decompose *where* that time goes: 
- E2E ≈ TTFT + (output_tokens × TPOT). 
- TTFT measures prefill cost and queue wait. 
- TPOT measures decode speed.

Together they answer not just "is it slow" but "slow *where*", which is what makes the dashboard useful for diagnosis, not just alerting.

#### Throughput

Four panels: requests running, generated tokens/sec, request throughput (req/s), queue depth.

- Queue depth (`num_requests_waiting`) is the most actionable single metric: if it grows, the system is overloaded, full stop. 
- Request throughput gives the achieved RPS to compare against the load test target.
- Requests running and generated tokens/sec give context on what the system is actually doing at that moment.

#### KV Cache

Two panels: GPU KV cache usage (%), preemption rate.

- KV cache usage shows headroom or how close the system is to the ceiling. 
- Preemption rate is the alarm: it becomes nonzero only when the cache already ran out and vLLM is paying the cost by evicting and recomputing sequences. Each preemption shows up as a P99 spike in the E2E latency panel, which is why these two sections are connected.

---

### Reading the dashboards: Debugging workflow

Start at the top of the dashboard and go down.

**E2E latency is high →**
- TTFT high, TPOT normal → bottleneck is before decoding: requests are queuing or prefill is slow. Check queue depth.
- TPOT high, TTFT normal → bottleneck is during decoding: too many sequences decoded simultaneously, memory bandwidth saturated. Check requests running.
- P95 fine but P99 spikes intermittently → check preemption rate: cache evictions cause occasional stalls.

**Queue depth is growing →**
Arrival rate exceeds serving rate. Either the model is too slow per request (TPOT) or the concurrency limit (`--max-num-seqs`) is the ceiling. Check KV cache: if it's near 100%, that's what's preventing vLLM from starting new requests.

**KV cache near 100% or preemptions nonzero →**
Cache pressure. Fix: reduce `--max-num-seqs` (fewer concurrent sequences) or reduce `--max-model-len` (smaller KV blocks per token). Preemptions are more urgent than just queuing because they waste GPU compute and cause latency spikes.

---

### Screenshots - TBD

- `screenshots/grafana_serving.png` — full dashboard reacting to a burst of requests *(H100)*
