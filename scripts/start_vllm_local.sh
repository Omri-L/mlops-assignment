#!/usr/bin/env bash
set -euo pipefail

MODEL="Qwen/Qwen3-0.6B"

export VLLM_TARGET_DEVICE=cpu

exec uv run python -m vllm.entrypoints.openai.api_server \
    --model "$MODEL" \
    --host 0.0.0.0 \
    --port 8000 \
    --dtype float32 \
    --device cpu \
    --max-model-len 4096