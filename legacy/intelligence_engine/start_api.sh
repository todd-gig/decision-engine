#!/bin/bash
# start_api.sh — Start the Gigaton AI Gateway
# Runs on port 8002 (matched to gigaton-ui-system apiClient)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "╔══════════════════════════════════════════╗"
echo "║       Gigaton AI Gateway v1.0.0          ║"
echo "║   Decision Engine + Translation Layer    ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# Check for API keys and report availability
echo "Provider status:"
[ -n "$ANTHROPIC_API_KEY" ] && echo "  ✓ Claude (ANTHROPIC_API_KEY set)"     || echo "  ○ Claude (mock mode — set ANTHROPIC_API_KEY)"
[ -n "$OPENAI_API_KEY" ]    && echo "  ✓ OpenAI (OPENAI_API_KEY set)"        || echo "  ○ OpenAI (mock mode — set OPENAI_API_KEY)"
[ -n "$GEMINI_API_KEY" ]    && echo "  ✓ Gemini (GEMINI_API_KEY set)"        || echo "  ○ Gemini (mock mode — set GEMINI_API_KEY)"
echo ""
echo "Starting on http://localhost:8002"
echo "API docs: http://localhost:8002/docs"
echo ""

PYTHONPATH="$SCRIPT_DIR" uvicorn api.main:app \
  --host 0.0.0.0 \
  --port 8002 \
  --reload \
  --log-level info
