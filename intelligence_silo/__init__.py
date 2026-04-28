"""Intelligence Silo integration shim for the decision engine.

Provides a singleton `IntelligenceNode` that the pipeline imports lazily.
The node is initialized once on first call to get_node() and reused.

Environment variables:
  INTELLIGENCE_SILO_PATH   — path to the intelligence-silo repo root
                             (default: ../intelligence-silo relative to this file)
  INTELLIGENCE_SILO_CONFIG — path to silo.yaml config (default: config/silo.yaml
                             inside the silo root)

If the silo package is not importable, get_node() returns None and the
pipeline skips memory recording silently.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_node = None
_initialized = False


def get_node():
    """Return the singleton IntelligenceNode, initializing it on first call.

    Returns None if the silo is not available or fails to initialize.
    """
    global _node, _initialized
    if _initialized:
        return _node

    _initialized = True
    _node = _init_node()
    return _node


def _init_node():
    """Attempt to import and initialize the IntelligenceNode."""
    # Locate the intelligence-silo repo
    silo_root = os.environ.get("INTELLIGENCE_SILO_PATH")
    if silo_root:
        silo_path = Path(silo_root)
    else:
        # Default: sibling directory
        silo_path = Path(__file__).parent.parent.parent / "intelligence-silo"

    if not silo_path.exists():
        logger.debug("Intelligence silo not found at %s — skipping", silo_path)
        return None

    # Add to sys.path so `from core.node import IntelligenceNode` works
    if str(silo_path) not in sys.path:
        sys.path.insert(0, str(silo_path))

    try:
        from core.node import IntelligenceNode  # type: ignore

        config_path = os.environ.get(
            "INTELLIGENCE_SILO_CONFIG",
            str(silo_path / "config" / "silo.yaml"),
        )
        node = IntelligenceNode(config_path=config_path)
        logger.info("Intelligence silo initialized: node=%s", node.node_id)
        return node

    except Exception as exc:
        logger.warning("Failed to initialize intelligence silo: %s", exc)
        return None


def reset():
    """Reset the singleton (useful for testing)."""
    global _node, _initialized
    _node = None
    _initialized = False
