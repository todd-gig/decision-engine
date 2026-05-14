"""scripts/ — operator + bootstrap utilities for decision-engine.

Each script under this package is idempotent + opt-in (never auto-runs at
import time). Modules here are imported by:
  - cli.py subcommands
  - api/main.py startup hooks (env-gated)
  - one-off operator invocations (`python -m scripts.<name>`)

penrose_signal: weakens
penrose_dimension: revenue_per_human_touch
"""
