#!/usr/bin/env bash
#
# Start vLLM with your chosen configuration.
# Reference: https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html

set -euo pipefail

MODEL="Qwen/Qwen3-30B-A3B-Instruct-2507"

exec uv run python -m vllm.entrypoints.openai.api_server \
    --model "$MODEL" \
    --host 0.0.0.0 \
    --port 8000 \
    --dtype bfloat16 \
    --max-model-len 8192 \
    --gpu-memory-utilization 0.92 \
    --max-num-seqs 64 \
    --enable-chunked-prefill \
    --enable-prefix-caching \
    --trust-remote-code \
    --disable-log-requests
    # --quantization fp8   ← uncomment and test in Phase 6 if latency is tight