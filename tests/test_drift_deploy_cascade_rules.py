"""Drift Sentinel — deploy-cascade rules MAJ-013/14/15/20/21.

Codifies the 9-bug HME + PPEME deploy cascade from 2026-05-13 / 14
(see memory `hme_deploy_post_mortem_2026_05_13.md` and
`standard_engine_deploy_template.md`). Each rule has at least one
passing case, one failing case, and one edge case.

WHY these tests exist:
    The first commit to add MAJ-013/14/15 (940b2f5, 2026-05-13)
    landed the YAML descriptions but never wired Python handlers.
    The rules were doctrine-claim-only (effective per the YAML,
    inert per the code). This file confirms the handlers now fire on
    the documented bug patterns and stay quiet on the canonical fix
    patterns — closing the gap per
    `feedback_doctrine_claim_vs_committed_code.md`.
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "drift_sentinel"))

from drift_scan import (  # noqa: E402
    Artifact,
    _check_cloudbuild_secret_env_in_non_bash_step,
    _check_cloud_sql_url_discipline,
    _check_cloudrun_runtime_sa_missing_cloudsql_client,
    _check_cloudsql_password_drift_between_instance_and_secret,
    _check_dockerfile_alembic_discipline,
)

_MAJ_013_RULE = {
    "id": "MAJ-013",
    "severity": "major",
    "remediation": "Use entrypoint: bash, or migrate at container startup.",
}
_MAJ_014_RULE = {
    "id": "MAJ-014",
    "severity": "major",
    "remediation": "Generate the password ONCE and reuse the shell var.",
}
_MAJ_015_RULE = {
    "id": "MAJ-015",
    "severity": "major",
    "remediation": "Grant roles/cloudsql.client to <engine>-runtime SA.",
}
_MAJ_020_RULE = {
    "id": "MAJ-020",
    "severity": "major",
    "remediation": "COPY alembic + alembic.ini + start.sh into the image.",
}
_MAJ_021_RULE = {
    "id": "MAJ-021",
    "severity": "major",
    "remediation": "Use URL.create(..., query={'host': socket}) for Cloud SQL.",
}


def _yaml(content: str, *, identifier: str = "cloudbuild.yaml") -> Artifact:
    return Artifact(
        source="codebase",
        identifier=identifier,
        artifact_type="config",
        content=content,
        metadata={"ext": ".yaml"},
    )


def _sh(content: str, *, identifier: str = "scripts/bootstrap.sh") -> Artifact:
    return Artifact(
        source="codebase",
        identifier=identifier,
        artifact_type="config",
        content=content,
        metadata={"ext": ".sh"},
    )


def _md(content: str, *, identifier: str = "SETUP.md") -> Artifact:
    return Artifact(
        source="codebase",
        identifier=identifier,
        artifact_type="markdown",
        content=content,
        metadata={"ext": ".md"},
    )


def _py(content: str, *, identifier: str = "engine/api/db.py") -> Artifact:
    return Artifact(
        source="codebase",
        identifier=identifier,
        artifact_type="code",
        content=content,
        metadata={"ext": ".py"},
    )


def _dockerfile(content: str, *, repo: str = "test-engine") -> Artifact:
    """A Dockerfile artifact. Identifier uses a repo-relative path so the
    handler can resolve sibling alembic/ + start.sh under
    /Users/admin/Documents/GitHub/<repo>/.
    """
    return Artifact(
        source="codebase",
        identifier=f"{repo}/Dockerfile",
        artifact_type="config",
        content=content,
        metadata={"ext": ""},
    )


# ---------------------------------------------------------------------------
# MAJ-013 — cloudbuild secretEnv in non-bash step
# ---------------------------------------------------------------------------


def test_maj013_fires_on_exec_wrapper_with_secret_env():
    """The canonical HME bug — exec-wrapper step + secretEnv = literal '$VAR'."""
    yaml = """\
steps:
  - id: migrate
    name: gcr.io/google-appengine/exec-wrapper
    args:
      - -i
      - us-central1-docker.pkg.dev/proj/img:latest
      - --
      - alembic
      - upgrade
      - head
    secretEnv: ['DB_PASSWORD']
availableSecrets:
  secretManager:
    - versionName: projects/p/secrets/db-password/versions/latest
      env: DB_PASSWORD
"""
    violations = _check_cloudbuild_secret_env_in_non_bash_step(
        _yaml(yaml), _MAJ_013_RULE,
    )
    assert len(violations) == 1
    assert violations[0].rule_id == "MAJ-013"
    assert "secretEnv" in violations[0].excerpt


def test_maj013_does_not_fire_on_bash_entrypoint_step():
    yaml = """\
steps:
  - id: migrate
    name: gcr.io/cloud-builders/gcloud
    entrypoint: bash
    args:
      - -c
      - 'alembic upgrade head --x-arg=db_url=$$DB_PASSWORD'
    secretEnv: ['DB_PASSWORD']
"""
    assert _check_cloudbuild_secret_env_in_non_bash_step(
        _yaml(yaml), _MAJ_013_RULE,
    ) == []


def test_maj013_does_not_fire_when_no_secret_env():
    yaml = """\
steps:
  - id: build
    name: gcr.io/cloud-builders/docker
    args: [build, -t, foo, .]
"""
    assert _check_cloudbuild_secret_env_in_non_bash_step(
        _yaml(yaml), _MAJ_013_RULE,
    ) == []


def test_maj013_skips_non_cloudbuild_yaml():
    """Random YAML files (not cloudbuild) are out of scope."""
    yaml = """\
steps:
  - name: foo
    secretEnv: ['X']
"""
    art = _yaml(yaml, identifier="config/some-other.yaml")
    assert _check_cloudbuild_secret_env_in_non_bash_step(
        art, _MAJ_013_RULE,
    ) == []


def test_maj013_honors_noqa_override():
    yaml = """\
steps:
  - id: migrate
    name: gcr.io/google-appengine/exec-wrapper
    secretEnv: ['DB_PASSWORD']  # noqa: MAJ-013 — accepted exec-wrapper drift
"""
    assert _check_cloudbuild_secret_env_in_non_bash_step(
        _yaml(yaml), _MAJ_013_RULE,
    ) == []


# ---------------------------------------------------------------------------
# MAJ-014 — Cloud SQL password drift between instance and secret
# ---------------------------------------------------------------------------


def test_maj014_fires_on_two_separate_openssl_calls():
    """PPEME's bug: instance and secret end up with different passwords."""
    sh = """\
#!/bin/bash
gcloud sql instances create ppeme-pg \\
  --database-version=POSTGRES_15 \\
  --root-password="$(openssl rand -base64 24)" \\
  --tier=db-f1-micro --region=us-central1
echo -n "$(openssl rand -base64 24)" | \\
  gcloud secrets create ppeme-db-password --data-file=-
"""
    violations = _check_cloudsql_password_drift_between_instance_and_secret(
        _sh(sh), _MAJ_014_RULE,
    )
    assert len(violations) >= 1
    assert violations[0].rule_id == "MAJ-014"


def test_maj014_does_not_fire_on_single_var_reused():
    """The canonical fix from standard_engine_deploy_template.md §9."""
    sh = """\
#!/bin/bash
PW="$(openssl rand -base64 24)"
gcloud sql instances create ppeme-pg \\
  --root-password="$PW" --tier=db-f1-micro --region=us-central1
echo -n "$PW" | gcloud secrets create ppeme-db-password --data-file=-
"""
    assert _check_cloudsql_password_drift_between_instance_and_secret(
        _sh(sh), _MAJ_014_RULE,
    ) == []


def test_maj014_does_not_fire_when_no_db_password_secret_referenced():
    """openssl rand for other purposes (signing keys, etc.) is fine."""
    sh = """\
#!/bin/bash
KEY1="$(openssl rand -base64 32)"
KEY2="$(openssl rand -base64 32)"
gcloud secrets create signing-key-a --data-file=<(echo -n "$KEY1")
gcloud secrets create signing-key-b --data-file=<(echo -n "$KEY2")
"""
    assert _check_cloudsql_password_drift_between_instance_and_secret(
        _sh(sh), _MAJ_014_RULE,
    ) == []


def test_maj014_fires_in_setup_md_too():
    """SETUP.md / README often documents the same bootstrap commands."""
    md = """\
# Engine bootstrap

Create the SQL instance:

```bash
gcloud sql instances create my-engine-pg \\
  --root-password="$(openssl rand -base64 24)"
```

Create the secret:

```bash
echo -n "$(openssl rand -base64 24)" | \\
  gcloud secrets create my-engine-db-password --data-file=-
```
"""
    violations = _check_cloudsql_password_drift_between_instance_and_secret(
        _md(md), _MAJ_014_RULE,
    )
    assert len(violations) >= 1


def test_maj014_skips_python_and_yaml_for_speed():
    """Restricted to .sh / .md / .yaml-like artifacts; ext check enforced."""
    art = Artifact(
        source="codebase",
        identifier="engine/setup.py",
        artifact_type="code",
        content=(
            'subprocess.run(["gcloud sql instances create x "\n'
            '  "--root-password=$(openssl rand -base64 24)"])\n'
            'subprocess.run(["gcloud secrets create x-db-password "\n'
            '  "$(openssl rand -base64 24)"])\n'
        ),
        metadata={"ext": ".py"},
    )
    assert _check_cloudsql_password_drift_between_instance_and_secret(
        art, _MAJ_014_RULE,
    ) == []


# ---------------------------------------------------------------------------
# MAJ-015 — Cloud Run runtime SA missing cloudsql.client
# ---------------------------------------------------------------------------


def test_maj015_fires_when_sa_created_but_no_client_role_grant():
    sh = """\
#!/bin/bash
gcloud iam service-accounts create ppeme-runtime --project=gigaton-platform
# (no cloudsql.client grant)
gcloud run deploy ppeme \\
  --service-account=ppeme-runtime@gigaton-platform.iam.gserviceaccount.com \\
  --add-cloudsql-instances=gigaton-platform:us-central1:ppeme-pg \\
  --image=us-central1-docker.pkg.dev/gigaton-platform/img:latest
"""
    violations = _check_cloudrun_runtime_sa_missing_cloudsql_client(
        _sh(sh), _MAJ_015_RULE,
    )
    assert len(violations) == 1
    assert "ppeme-runtime" in violations[0].excerpt
    assert violations[0].rule_id == "MAJ-015"


def test_maj015_does_not_fire_when_client_role_granted():
    sh = """\
#!/bin/bash
gcloud iam service-accounts create ppeme-runtime --project=gigaton-platform
gcloud projects add-iam-policy-binding gigaton-platform \\
  --member="serviceAccount:ppeme-runtime@gigaton-platform.iam.gserviceaccount.com" \\
  --role="roles/cloudsql.client"
gcloud run deploy ppeme \\
  --service-account=ppeme-runtime@gigaton-platform.iam.gserviceaccount.com \\
  --add-cloudsql-instances=gigaton-platform:us-central1:ppeme-pg
"""
    assert _check_cloudrun_runtime_sa_missing_cloudsql_client(
        _sh(sh), _MAJ_015_RULE,
    ) == []


def test_maj015_does_not_fire_when_no_cloudsql_in_use():
    """SA created for a service without Cloud SQL is not in scope."""
    sh = """\
#!/bin/bash
gcloud iam service-accounts create gateway-runtime --project=gigaton-platform
gcloud run deploy gigaton-gateway \\
  --service-account=gateway-runtime@gigaton-platform.iam.gserviceaccount.com
"""
    assert _check_cloudrun_runtime_sa_missing_cloudsql_client(
        _sh(sh), _MAJ_015_RULE,
    ) == []


def test_maj015_fires_in_setup_md_too():
    md = """\
# Bootstrap

```bash
gcloud iam service-accounts create my-engine-runtime --project=gigaton-platform
gcloud run deploy my-engine \\
  --service-account=my-engine-runtime@gigaton-platform.iam.gserviceaccount.com \\
  --add-cloudsql-instances=gigaton-platform:us-central1:my-engine-pg
```
"""
    violations = _check_cloudrun_runtime_sa_missing_cloudsql_client(
        _md(md), _MAJ_015_RULE,
    )
    assert len(violations) == 1


# ---------------------------------------------------------------------------
# MAJ-020 — Dockerfile alembic discipline
# ---------------------------------------------------------------------------


def _alembic_repo_fixture(github_root: Path, name: str, *,
                          with_alembic_copy: bool,
                          with_alembic_ini_copy: bool,
                          start_sh_migrates: bool | None) -> Artifact:
    """Create a synthetic repo under ``github_root/<name>`` with the
    requested alembic + Dockerfile shape; return a Dockerfile Artifact.

    The handler reads ``DRIFT_LOCAL_CODEBASE_ROOT`` to resolve sibling
    files — tests must monkeypatch that env var to ``github_root``.
    """
    repo_root = github_root / name
    repo_root.mkdir(parents=True, exist_ok=True)
    (repo_root / "alembic.ini").write_text(
        "[alembic]\nscript_location = alembic\n")
    alembic_dir = repo_root / "alembic"
    alembic_dir.mkdir(exist_ok=True)
    (alembic_dir / "env.py").write_text("")
    if start_sh_migrates is not None:
        body = "#!/usr/bin/env bash\nset -e\n"
        if start_sh_migrates:
            body += "alembic upgrade head\n"
        body += "exec uvicorn api.main:app\n"
        (repo_root / "start.sh").write_text(body)

    df_lines = [
        "FROM python:3.11-slim",
        "WORKDIR /app",
        "COPY requirements.txt /app/",
        "RUN pip install -r requirements.txt",
        "COPY api/ /app/api/",
    ]
    if with_alembic_copy:
        df_lines.append("COPY alembic/ /app/alembic/")
    if with_alembic_ini_copy:
        df_lines.append("COPY alembic.ini /app/alembic.ini")
    if start_sh_migrates is not None:
        df_lines.append("COPY start.sh /app/start.sh")
        df_lines.append("RUN chmod +x /app/start.sh")
        df_lines.append('CMD ["/app/start.sh"]')
    else:
        df_lines.append('CMD ["uvicorn", "api.main:app"]')
    content = "\n".join(df_lines) + "\n"
    return Artifact(
        source="codebase",
        identifier=f"{name}/Dockerfile",
        artifact_type="config",
        content=content,
        metadata={"ext": "", "repo": name},
    )


def test_maj020_fires_when_alembic_dir_not_copied(tmp_path, monkeypatch):
    monkeypatch.setenv("DRIFT_LOCAL_CODEBASE_ROOT", str(tmp_path))
    art = _alembic_repo_fixture(
        tmp_path, "engine-a",
        with_alembic_copy=False,
        with_alembic_ini_copy=True,
        start_sh_migrates=True,
    )
    violations = _check_dockerfile_alembic_discipline(art, _MAJ_020_RULE)
    rule_ids = {v.rule_id for v in violations}
    assert "MAJ-020" in rule_ids
    assert any("alembic" in v.excerpt for v in violations)


def test_maj020_fires_when_alembic_ini_not_copied(tmp_path, monkeypatch):
    monkeypatch.setenv("DRIFT_LOCAL_CODEBASE_ROOT", str(tmp_path))
    art = _alembic_repo_fixture(
        tmp_path, "engine-b",
        with_alembic_copy=True,
        with_alembic_ini_copy=False,
        start_sh_migrates=True,
    )
    violations = _check_dockerfile_alembic_discipline(art, _MAJ_020_RULE)
    assert any("alembic.ini" in v.excerpt for v in violations)


def test_maj020_fires_when_start_sh_missing_alembic_upgrade(
    tmp_path, monkeypatch,
):
    monkeypatch.setenv("DRIFT_LOCAL_CODEBASE_ROOT", str(tmp_path))
    art = _alembic_repo_fixture(
        tmp_path, "engine-c",
        with_alembic_copy=True,
        with_alembic_ini_copy=True,
        start_sh_migrates=False,
    )
    violations = _check_dockerfile_alembic_discipline(art, _MAJ_020_RULE)
    assert any("start.sh" in v.excerpt or
               "alembic upgrade head" in v.excerpt
               for v in violations)


def test_maj020_does_not_fire_on_canonical_setup(tmp_path, monkeypatch):
    monkeypatch.setenv("DRIFT_LOCAL_CODEBASE_ROOT", str(tmp_path))
    art = _alembic_repo_fixture(
        tmp_path, "engine-d",
        with_alembic_copy=True,
        with_alembic_ini_copy=True,
        start_sh_migrates=True,
    )
    assert _check_dockerfile_alembic_discipline(
        art, _MAJ_020_RULE,
    ) == []


def test_maj020_does_not_fire_when_dockerfile_copies_whole_context(
    tmp_path, monkeypatch,
):
    """`COPY . .` / `COPY . /app/` copies alembic.ini + alembic/ implicitly.

    Some engines use that single line (sales-operating-system, several
    others) instead of explicit per-directory copies. That's still a
    valid pattern — alembic ships into the image — so don't flag it.
    """
    monkeypatch.setenv("DRIFT_LOCAL_CODEBASE_ROOT", str(tmp_path))
    name = "engine-whole-context"
    repo_root = tmp_path / name
    repo_root.mkdir()
    (repo_root / "alembic.ini").write_text("[alembic]\n")
    (repo_root / "alembic").mkdir()
    body = "#!/usr/bin/env bash\nalembic upgrade head\nexec uvicorn x:y\n"
    (repo_root / "start.sh").write_text(body)
    art = Artifact(
        source="codebase",
        identifier=f"{name}/Dockerfile",
        artifact_type="config",
        content=(
            "FROM python:3.11-slim\n"
            "WORKDIR /app\n"
            "COPY requirements.txt .\n"
            "RUN pip install -r requirements.txt\n"
            "COPY . .\n"
            'CMD ["/app/start.sh"]\n'
        ),
        metadata={"ext": "", "repo": name},
    )
    assert _check_dockerfile_alembic_discipline(
        art, _MAJ_020_RULE,
    ) == []


def test_maj020_skips_repo_without_alembic(tmp_path, monkeypatch):
    """A Dockerfile in a repo with no alembic at all is out of scope."""
    monkeypatch.setenv("DRIFT_LOCAL_CODEBASE_ROOT", str(tmp_path))
    name = "engine-no-alembic"
    (tmp_path / name).mkdir()
    art = Artifact(
        source="codebase",
        identifier=f"{name}/Dockerfile",
        artifact_type="config",
        content="FROM python:3.11-slim\nCOPY api/ /app/api/\n",
        metadata={"ext": "", "repo": name},
    )
    assert _check_dockerfile_alembic_discipline(
        art, _MAJ_020_RULE,
    ) == []


# ---------------------------------------------------------------------------
# MAJ-021 — Cloud SQL URL discipline (URL.create vs raw f-string)
# ---------------------------------------------------------------------------


def test_maj021_fires_on_raw_fstring_with_cloudsql_socket():
    """HME bug #6 from 2026-05-13: f-string with /cloudsql/ host."""
    code = '''
import os
HOST = os.environ["DB_HOST"]
USER = os.environ["DB_USER"]
PW = os.environ["DB_PASSWORD"]
NAME = os.environ["DB_NAME"]
URL = f"postgresql+psycopg2://{USER}:{PW}@/cloudsql/proj:us-central1:pg/{NAME}"
'''
    violations = _check_cloud_sql_url_discipline(_py(code), _MAJ_021_RULE)
    assert len(violations) == 1
    assert violations[0].rule_id == "MAJ-021"


def test_maj021_does_not_fire_when_url_create_used_nearby():
    """The canonical fix from standard_engine_deploy_template.md §3."""
    code = '''
from sqlalchemy.engine import URL
import os
HOST = os.environ["DB_HOST"]
USER = os.environ["DB_USER"]
PW = os.environ["DB_PASSWORD"]
NAME = os.environ["DB_NAME"]
if HOST.startswith("/"):
    url = URL.create(
        drivername="postgresql+psycopg2",
        username=USER, password=PW, database=NAME,
        query={"host": HOST},
    ).render_as_string(hide_password=False)
'''
    assert _check_cloud_sql_url_discipline(_py(code), _MAJ_021_RULE) == []


def test_maj021_does_not_fire_on_tcp_host_pattern():
    """TCP hosts (no /cloudsql/ socket path) are out of scope."""
    code = '''
import os
USER = os.environ["DB_USER"]
PW = os.environ["DB_PASSWORD"]
HOST = "db.example.com"
URL = f"postgresql+psycopg2://{USER}:{PW}@{HOST}:5432/mydb"
'''
    assert _check_cloud_sql_url_discipline(_py(code), _MAJ_021_RULE) == []


def test_maj021_skips_test_files():
    code = '''
URL = f"postgresql+psycopg2://u:p@/cloudsql/p:r:i/db"
'''
    art = Artifact(
        source="codebase",
        identifier="engine/tests/test_db.py",
        artifact_type="code",
        content=code,
        metadata={"ext": ".py"},
    )
    assert _check_cloud_sql_url_discipline(art, _MAJ_021_RULE) == []


def test_maj021_honors_noqa_override():
    code = '''
URL = f"postgresql+psycopg2://u:p@/cloudsql/p:r:i/db"  # noqa: MAJ-021 — accepted
'''
    assert _check_cloud_sql_url_discipline(_py(code), _MAJ_021_RULE) == []


def test_maj021_fires_on_format_style_template_with_host_placeholder():
    """`.format()`-style template with explicit {host} placeholder."""
    code = '''
TEMPLATE = "postgresql://user:pw@{host}/db"
url = TEMPLATE.format(host=os.environ["DB_HOST"])
'''
    violations = _check_cloud_sql_url_discipline(_py(code), _MAJ_021_RULE)
    assert len(violations) == 1


def test_maj021_does_not_fire_on_scheme_prefix_slicing():
    """Regression: sales-operating-system/scripts/seed_from_pg.py was
    falsely flagged 2026-05-14 because the rule fired on
    `"postgresql://" + dsn[len("postgres+asyncpg://"):]` — that's not
    URL construction, it's scheme-prefix manipulation. The tightened
    rule must NOT fire on this pattern.
    """
    code = '''
def normalize_dsn(dsn: str) -> str:
    for prefix in ("postgresql+asyncpg://", "postgres+asyncpg://"):
        if dsn.startswith(prefix):
            dsn = "postgresql://" + dsn[len(prefix):]
    if dsn.startswith("postgres://"):
        dsn = "postgresql://" + dsn[len("postgres://"):]
    return dsn
'''
    assert _check_cloud_sql_url_discipline(_py(code), _MAJ_021_RULE) == []
