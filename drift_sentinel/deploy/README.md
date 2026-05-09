# Deploy — Drift Sentinel scheduled runs

Two paths, pick what fits the moment:

## Local (recommended for now)

Mac launchd job, Sundays at 08:00 local time. Writes reports to `drift_sentinel/reports/` for the operator to review.

> **Slack posting is user-initiated only.** Neither the launchd job nor the Cloud Run Job posts to Slack. To push a digest to Slack, run the scanner manually from your terminal: `python3 drift_scan.py --source ... --post-to-slack` with `SLACK_WEBHOOK_URL` set in your shell.

```bash
cd drift_sentinel/deploy/local
bash install_launchd.sh

# verify
launchctl list | grep drift-sentinel
launchctl start com.gigaton.drift-sentinel   # trigger now

# uninstall
bash install_launchd.sh uninstall
```

The plist is at `local/com.gigaton.drift-sentinel.plist`. Edit it to change cadence or sources.

## GCP (when you want it server-side)

Cloud Run Job + Cloud Scheduler. One-time secrets setup, then `gcloud builds submit`.

```bash
# 1. Set up secrets (one-time)
# Follow drift_sentinel/deploy/gcp/secrets.md

# 2. Build + deploy from repo root
gcloud builds submit \
  --config drift_sentinel/deploy/gcp/cloudbuild.yaml .

# 3. Create the Scheduler job (one-time)
gcloud scheduler jobs create http drift-sentinel-weekly \
  --location=us-central1 \
  --schedule="0 8 * * 0" \
  --time-zone="America/Chicago" \
  --uri="https://us-central1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/$(gcloud config get-value project)/jobs/drift-sentinel:run" \
  --http-method=POST \
  --oauth-service-account-email="drift-sentinel-scheduler@$(gcloud config get-value project).iam.gserviceaccount.com"
```

Files:

- `gcp/Dockerfile` — Python 3.12 + `gh CLI` + the sentinel code (no Slack)
- `gcp/cloudbuild.yaml` — Cloud Build pipeline (build → push → deploy as Cloud Run Job, mounts only the gh-token secret)
- `gcp/scheduler.yaml` — Cloud Scheduler config reference
- `gcp/secrets.md` — Secret Manager setup walkthrough (gh-token only)

## Why both?

Local gives you a working scheduled scan today, no GCP perms needed. GCP gives you a managed cadence that survives laptop restarts and runs even when offline. Switch when ready.
