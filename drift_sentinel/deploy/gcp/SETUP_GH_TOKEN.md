# Creating the drift-gh-token secret in GCP

The drift sentinel GitHub adapter reads repository artifacts via the GitHub API.
When `drift-gh-token` exists in Secret Manager, Cloud Build mounts it automatically.
When absent, the GitHub adapter yields 0 artifacts (silent degradation — not an error).

## Steps

1. Create a GitHub PAT with `repo:read` scope at https://github.com/settings/tokens
   - Token name: `drift-sentinel-read`  
   - Expiration: 90 days (recommended — rotate quarterly)
   - Required scopes: `repo` (read-only is sufficient)

2. Create the secret in GCP:
   ```bash
   echo -n "ghp_YOUR_TOKEN_HERE" | \
     gcloud secrets create drift-gh-token \
       --project=carmen-beach-properties \
       --replication-policy=automatic \
       --data-file=-
   ```

3. Grant the Cloud Build service account access:
   ```bash
   PROJECT_NUMBER=$(gcloud projects describe carmen-beach-properties --format='value(projectNumber)')
   gcloud secrets add-iam-policy-binding drift-gh-token \
     --project=carmen-beach-properties \
     --member="serviceAccount:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com" \
     --role="roles/secretmanager.secretAccessor"
   ```

4. Verify the secret exists:
   ```bash
   gcloud secrets describe drift-gh-token --project=carmen-beach-properties
   ```

5. Re-run the drift sentinel build to pick up the secret:
   ```bash
   cd /Users/admin/Documents/GitHub/decision-engine
   gcloud builds submit --config drift_sentinel/deploy/gcp/cloudbuild.yaml . \
     --project=carmen-beach-properties
   ```

## Rotation

When the PAT expires, add a new version:
```bash
echo -n "ghp_NEW_TOKEN" | \
  gcloud secrets versions add drift-gh-token \
    --project=carmen-beach-properties \
    --data-file=-
```
The Cloud Run Job picks up `:latest` automatically on the next execution.
