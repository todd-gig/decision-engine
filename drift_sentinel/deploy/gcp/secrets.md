# GCP Secrets Setup — one-time

The Cloud Run Job mounts ONE Secret Manager secret at runtime: a GitHub token (so the `gh CLI` inside the container can authenticate non-interactively).

**Slack posting is intentionally NOT a job secret.** Slack integrations are user-level only — scheduled runs emit reports to Cloud Logging; the operator posts to Slack from their own terminal or chat session if/when they want to share.

## 1. Create the GitHub token secret

```bash
# GitHub PAT — needs `repo` + `read:org` scopes (matches todd-gig token)
echo -n 'ghp_...' \
  | gcloud secrets create drift-gh-token --data-file=-
```

To rotate later: `gcloud secrets versions add drift-gh-token --data-file=-`.

## 2. Grant the Cloud Run service account access

```bash
PROJECT_ID="$(gcloud config get-value project)"
PROJECT_NUM="$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')"
RUN_SA="${PROJECT_NUM}-compute@developer.gserviceaccount.com"

gcloud secrets add-iam-policy-binding drift-gh-token \
  --member="serviceAccount:${RUN_SA}" \
  --role="roles/secretmanager.secretAccessor"
```

## 3. Create the Scheduler service account (Cloud Scheduler → Cloud Run Job)

```bash
gcloud iam service-accounts create drift-sentinel-scheduler \
  --display-name="Drift Sentinel — Cloud Scheduler invoker"

gcloud run jobs add-iam-policy-binding drift-sentinel \
  --region=us-central1 \
  --member="serviceAccount:drift-sentinel-scheduler@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/run.invoker"
```

## 4. Container `gh` auth

The Dockerfile installs `gh CLI`. The container reads `GH_TOKEN` from
the env (auto-set by Cloud Run from `drift-gh-token`); `gh` picks that
up automatically with no further config.

## 5. Verify

```bash
# Trigger the job once manually
gcloud run jobs execute drift-sentinel --region=us-central1 --wait

# Check the Slack channel for the digest, and Cloud Logging for the
# llm_audit lines
```
