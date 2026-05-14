"""Drift Sentinel preventive rules — CRIT-011 + MIN-009.

CRIT-011 (env_mutation_in_request_handler):
    Detects `os.environ[X] = ...` (and .update / .__setitem__) inside
    functions decorated as FastAPI route handlers. WHY: process-global
    env mutation under concurrent request load causes cross-user
    credential contamination. See SIE `fix/llm-secret-ref-param` +
    `design_decision_secret_ref_parameter_2026_05_14.md`.

MIN-009 (cloud_run_max_instances_above_one):
    Detects Cloud Run service configs raising --max-instances above 1.
    WHY: several v0 designs assume single-instance correctness
    (SecretStore cache, in-memory rate limits, scheduler leader-elect).
    See `design_decision_secret_store_cache_2026_05_14.md`.
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "drift_sentinel"))

from drift_scan import (  # noqa: E402
    Artifact,
    _check_cloud_run_max_instances_above_one,
    _check_env_mutation_in_request_handler,
)

_CRIT_011_RULE = {
    "id": "CRIT-011",
    "severity": "critical",
    "remediation": (
        "Pass the value as an explicit parameter; do not mutate "
        "process-global state in concurrent handlers."
    ),
}

_MIN_009_RULE = {
    "id": "MIN-009",
    "severity": "minor",
    "remediation": (
        "Cloud Run --max-instances > 1 triggers v1 follow-ups: see "
        "memory files design_decision_secret_store_cache_2026_05_14 + "
        "initiate cross-instance work."
    ),
}


def _py(content: str, *, identifier: str = "services/x/main.py") -> Artifact:
    return Artifact(
        source="codebase",
        identifier=identifier,
        artifact_type="code",
        content=content,
        metadata={"ext": ".py"},
    )


def _yaml(content: str, *, identifier: str = "cloudbuild.yaml") -> Artifact:
    return Artifact(
        source="codebase",
        identifier=identifier,
        artifact_type="config",
        content=content,
        metadata={"ext": ".yaml"},
    )


# ---------------------------------------------------------------------------
# CRIT-011 — env mutation in FastAPI route handler
# ---------------------------------------------------------------------------


def test_crit011_fires_on_env_assignment_in_app_post_handler():
    """The canonical bug: os.environ[X] = ref inside @app.post handler."""
    code = '''
import os
from fastapi import FastAPI

app = FastAPI()

@app.post("/v1/intel/call")
async def call_provider(req):
    os.environ["ANTHROPIC_API_KEY_REF"] = req.secret_ref
    return {"ok": True}
'''
    violations = _check_env_mutation_in_request_handler(_py(code), _CRIT_011_RULE)
    assert len(violations) == 1
    assert "os.environ" in violations[0].excerpt
    assert violations[0].severity == "critical"
    assert violations[0].rule_id == "CRIT-011"


def test_crit011_fires_on_router_get_handler():
    """@router.get + os.environ[...] = ... should also fire."""
    code = '''
import os
from fastapi import APIRouter

router = APIRouter()

@router.get("/echo")
async def echo(key: str, value: str):
    os.environ[key] = value
    return {"set": True}
'''
    violations = _check_env_mutation_in_request_handler(_py(code), _CRIT_011_RULE)
    assert len(violations) == 1


def test_crit011_fires_on_environ_update_inside_handler():
    code = '''
import os
from fastapi import FastAPI

app = FastAPI()

@app.put("/bulk")
async def bulk_set(items: dict):
    os.environ.update(items)
    return {"ok": True}
'''
    violations = _check_env_mutation_in_request_handler(_py(code), _CRIT_011_RULE)
    assert len(violations) == 1


def test_crit011_does_not_fire_on_environ_get():
    """Read-only access is fine — not a contamination risk."""
    code = '''
import os
from fastapi import FastAPI

app = FastAPI()

@app.get("/whoami")
async def whoami():
    return {"key": os.environ.get("MY_KEY", "default")}
'''
    assert _check_env_mutation_in_request_handler(_py(code), _CRIT_011_RULE) == []


def test_crit011_does_not_fire_on_environ_in_check():
    code = '''
import os
from fastapi import FastAPI

app = FastAPI()

@app.get("/has")
async def has_key():
    return {"present": "MY_KEY" in os.environ}
'''
    assert _check_env_mutation_in_request_handler(_py(code), _CRIT_011_RULE) == []


def test_crit011_does_not_fire_on_module_scope_env_setup():
    """Module-level os.environ setup runs once at import — not a
    concurrent-handler contamination vector."""
    code = '''
import os

os.environ["LOG_LEVEL"] = "INFO"

def some_helper():
    return 42
'''
    assert _check_env_mutation_in_request_handler(_py(code), _CRIT_011_RULE) == []


def test_crit011_does_not_fire_on_non_handler_function():
    """Plain helper function without a route decorator — out of scope."""
    code = '''
import os

def configure_provider(secret_ref):
    os.environ["KEY"] = secret_ref
    return True
'''
    assert _check_env_mutation_in_request_handler(_py(code), _CRIT_011_RULE) == []


def test_crit011_honors_noqa_override():
    code = '''
import os
from fastapi import FastAPI

app = FastAPI()

@app.post("/test")
async def test_handler(value: str):
    os.environ["TEST_KEY"] = value  # noqa: CRIT-011 — intentional in test fixture
    return {"ok": True}
'''
    assert _check_env_mutation_in_request_handler(_py(code), _CRIT_011_RULE) == []


def test_crit011_does_not_fire_on_non_python_files():
    art = Artifact(
        source="codebase",
        identifier="src/handler.ts",
        artifact_type="code",
        content='os.environ["X"] = "y"',
        metadata={"ext": ".ts"},
    )
    assert _check_env_mutation_in_request_handler(art, _CRIT_011_RULE) == []


def test_crit011_multiple_mutations_each_fire_once():
    code = '''
import os
from fastapi import FastAPI

app = FastAPI()

@app.post("/a")
async def a(v: str):
    os.environ["X"] = v
    return {}

@app.post("/b")
async def b(v: str):
    os.environ["Y"] = v
    return {}
'''
    violations = _check_env_mutation_in_request_handler(_py(code), _CRIT_011_RULE)
    assert len(violations) == 2


# ---------------------------------------------------------------------------
# MIN-009 — Cloud Run max-instances > 1
# ---------------------------------------------------------------------------


def test_min009_fires_on_max_instances_equals_two():
    yaml = '''
steps:
  - name: gcr.io/cloud-builders/gcloud
    args:
      - run
      - deploy
      - my-service
      - --max-instances=2
      - --region=us-central1
'''
    violations = _check_cloud_run_max_instances_above_one(_yaml(yaml), _MIN_009_RULE)
    assert len(violations) == 1
    assert "2" in violations[0].excerpt
    assert violations[0].severity == "minor"


def test_min009_fires_on_max_instances_space_form():
    yaml = '''
steps:
  - args: ["--max-instances 5", "--region=us-central1"]
'''
    violations = _check_cloud_run_max_instances_above_one(_yaml(yaml), _MIN_009_RULE)
    assert len(violations) == 1
    assert "5" in violations[0].excerpt


def test_min009_fires_on_knative_max_scale_annotation():
    yaml = '''
apiVersion: serving.knative.dev/v1
kind: Service
metadata:
  annotations:
    autoscaling.knative.dev/maxScale: "10"
'''
    violations = _check_cloud_run_max_instances_above_one(_yaml(yaml), _MIN_009_RULE)
    assert len(violations) == 1
    assert "10" in violations[0].excerpt


def test_min009_fires_on_max_instances_yaml_field():
    yaml = '''
service:
  name: foo
  max_instances: 3
'''
    violations = _check_cloud_run_max_instances_above_one(_yaml(yaml), _MIN_009_RULE)
    assert len(violations) == 1
    assert "3" in violations[0].excerpt


def test_min009_does_not_fire_on_max_instances_one():
    yaml = '''
steps:
  - args:
      - --max-instances=1
'''
    assert _check_cloud_run_max_instances_above_one(_yaml(yaml), _MIN_009_RULE) == []


def test_min009_does_not_fire_when_flag_absent():
    """Absence is fine — Cloud Run default is irrelevant. The rule only
    fires when the operator explicitly raises the cap."""
    yaml = '''
steps:
  - name: gcr.io/cloud-builders/gcloud
    args:
      - run
      - deploy
      - my-service
      - --region=us-central1
'''
    assert _check_cloud_run_max_instances_above_one(_yaml(yaml), _MIN_009_RULE) == []


def test_min009_does_not_fire_on_zero():
    yaml = '''
steps:
  - args:
      - --max-instances=0
'''
    assert _check_cloud_run_max_instances_above_one(_yaml(yaml), _MIN_009_RULE) == []


def test_min009_honors_noqa_override():
    yaml = '''
steps:
  - args:
      - --max-instances=4  # noqa: MIN-009 — multi-instance hardened
'''
    assert _check_cloud_run_max_instances_above_one(_yaml(yaml), _MIN_009_RULE) == []


def test_min009_fires_once_per_line_not_once_per_pattern():
    """A single line matching multiple patterns must produce one violation,
    not duplicates."""
    yaml = 'max_instances: 7  # also matches --max-instances 7'
    art = Artifact(
        source="codebase",
        identifier="config.yaml",
        artifact_type="config",
        content=yaml,
        metadata={"ext": ".yaml"},
    )
    violations = _check_cloud_run_max_instances_above_one(art, _MIN_009_RULE)
    # Each distinct line index reported at most once
    line_nos = {v.location for v in violations}
    assert len(line_nos) == len(violations)


def test_min009_fires_on_python_deploy_script():
    """Deploy automation in Python (not just YAML) should also trip."""
    py = '''
DEPLOY_ARGS = ["--max-instances=8", "--region=us-central1"]
'''
    art = Artifact(
        source="codebase",
        identifier="scripts/deploy.py",
        artifact_type="code",
        content=py,
        metadata={"ext": ".py"},
    )
    violations = _check_cloud_run_max_instances_above_one(art, _MIN_009_RULE)
    assert len(violations) == 1
