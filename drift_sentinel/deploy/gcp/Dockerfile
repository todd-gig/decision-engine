# Drift Sentinel — Cloud Run Job container
# Single-purpose image that runs `drift_scan.py --source github,drive --post-to-slack`
# on a schedule driven by Cloud Scheduler.
FROM python:3.12-slim AS runtime

# gh CLI for the GitHub adapter
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl gnupg \
    && (curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg) \
    && chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) \
        signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] \
        https://cli.github.com/packages stable main" \
        | tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
    && apt-get update && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install pyyaml only — scanner has no other runtime deps
RUN pip install --no-cache-dir pyyaml==6.0.2

# Copy the sentinel directory (must be the build context root or a sub-path)
COPY drift_sentinel /app/drift_sentinel
COPY MASTER_FIRST_PRINCIPLES_REFERENCE.md /app/MASTER_FIRST_PRINCIPLES_REFERENCE.md

WORKDIR /app/drift_sentinel

# Cloud Run Job invokes the script directly. Override CMD via the job spec
# if you want a different source set or fail-on threshold.
#
# Slack posting is intentionally NOT included here — Slack integrations are
# user-level only (see feedback_slack_user_level_only). Scheduled runs emit
# the report to stdout (Cloud Logging); the operator reviews on their terms.
ENTRYPOINT ["python3", "drift_scan.py"]
CMD ["--source", "github", "--no-persist"]
