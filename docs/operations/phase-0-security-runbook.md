# Phase 0 Task 1 — PAT Rotation Runbook

**Owner:** Todd
**Time:** ~10 minutes end-to-end
**Blocks:** All 29 other tasks in the Unified Decision Engine plan
**Status of local scrubbing:** ✅ Done by Claude — `repo_master_list.txt` and both copies of `UNIFIED_DECISION_ENGINE_INTEGRATION.md` no longer contain the live token.
**Status of remote rotation:** ⏳ Todd to execute below.

---

## Why this is P0

A live GitHub PAT (`REDACTED_PAT_REVOKED_2026-04-17`) was embedded in a remote URL for `todd-gig/Carmen-Beach-Properties` and written to `~/Desktop/github-multiaccount/repo_master_list.txt`. Until this token is revoked at github.com, anyone who has ever read that file or any backup of it has push access to that repo — and potentially lateral access depending on token scope. The kernel freeze in Phase 1 commits the locked API contract to `decision-engine`, and we cannot cut v2.0.0 with a known credential exposure in scope.

---

## Step 1 — Revoke the token (2 minutes)

1. Open https://github.com/settings/tokens in the browser where `todd-gig` is signed in.
2. Find the token that starts with `gho_sQlm...`. Click **Delete**. Confirm.
3. While you're there: delete any other tokens you don't recognize or can't name. Unknown tokens are assumed compromised.

**Verification:** The token is gone from the list. No other action is valid until this is true.

---

## Step 2 — Issue a scoped replacement (3 minutes)

Only create this token if you actually need a PAT. If you can switch to SSH (Step 3), skip this step entirely — SSH is strictly better.

If you need a PAT (e.g. for a CI system that requires one):

1. https://github.com/settings/tokens → **Generate new token (fine-grained)**.
2. Name: `todd-gig-cli-2026Q2`
3. Expiration: **90 days** (not custom, not "no expiration")
4. Resource owner: `todd-gig`
5. Repository access: **Only select repositories** → pick just what actually needs it (likely `Carmen-Beach-Properties`, `decision-engine`, `gigaton-engine`, `sales-operating-system`, `transcript-knowledge-base`)
6. Permissions: **Contents: Read and write**, **Metadata: Read-only**, **Workflows: Read and write** if CI needs it. Nothing else. No org permissions.
7. Generate. Copy the token **into 1Password or GCP Secret Manager**, not into a file, not into a URL, not into a shell history.
8. SSO-authorize if Gigaton's GitHub org has SSO enforced.

Do the same for the `bella-byte` account if it also uses a PAT.

---

## Step 3 — Switch to SSH where possible (3 minutes, strongly recommended)

SSH keys don't leak into URLs, don't expire awkwardly, and don't get copy-pasted into Slack. On your Mac:

```bash
# Generate one key per identity (skip if keys already exist)
ssh-keygen -t ed25519 -C "todd@gigaton.ai" -f ~/.ssh/id_ed25519_todd_gig
ssh-keygen -t ed25519 -C "todd.cx@turtleisland.solutions" -f ~/.ssh/id_ed25519_bella_byte

# Add both to the agent
eval "$(ssh-agent -s)"
ssh-add --apple-use-keychain ~/.ssh/id_ed25519_todd_gig
ssh-add --apple-use-keychain ~/.ssh/id_ed25519_bella_byte

# Copy each pub key to clipboard, one at a time, and add to the matching GitHub account
pbcopy < ~/.ssh/id_ed25519_todd_gig.pub
# → github.com (signed in as todd-gig) → Settings → SSH and GPG keys → New SSH key → paste → save

pbcopy < ~/.ssh/id_ed25519_bella_byte.pub
# → github.com (signed in as bella-byte) → Settings → SSH and GPG keys → New SSH key → paste → save
```

Per-host routing via `~/.ssh/config` (this is how you cleanly support two GitHub identities on one machine):

```
Host github.com-todd-gig
  HostName github.com
  User git
  IdentityFile ~/.ssh/id_ed25519_todd_gig
  IdentitiesOnly yes

Host github.com-bella-byte
  HostName github.com
  User git
  IdentityFile ~/.ssh/id_ed25519_bella_byte
  IdentitiesOnly yes
```

Test:
```bash
ssh -T github.com-todd-gig       # expect: "Hi todd-gig! You've successfully authenticated..."
ssh -T github.com-bella-byte     # expect: "Hi bella-byte! ..."
```

---

## Step 4 — Rewrite remote URLs to strip the token (1 minute)

The exposed URL lives in the local clone at `/Users/admin/Documents/GitHub/Carmen-Beach-Properties/.git/config`. Rewrite it:

```bash
cd /Users/admin/Documents/GitHub/Carmen-Beach-Properties

# If you did Step 3 (SSH), preferred:
git remote set-url origin git@github.com-todd-gig:todd-gig/Carmen-Beach-Properties.git

# If you skipped SSH and are staying on HTTPS:
git remote set-url origin https://github.com/todd-gig/Carmen-Beach-Properties.git

git remote -v   # verify the new URL has NO token in it
```

Audit the other clone at `/Users/admin/.knowledge_sync/repos/Carmen-Beach-Properties` the same way — and every repo on the box:

```bash
find /Users/admin -name "config" -path "*/.git/config" -print -exec grep -l "gho_\|ghp_\|github_pat_" {} \;
```

Any hit → `git remote set-url origin <clean-url>` on that repo.

---

## Step 5 — Scrub git history if the token was ever committed (5 minutes, only if needed)

If the token was pasted into a committed file (not just a working-tree file), `git filter-repo` or BFG is required. For our case the token was only in a local scan output that was NOT committed anywhere, so this step is **not required**. Confirm with:

```bash
cd /Users/admin/Documents/GitHub/Carmen-Beach-Properties
git log --all -S "REDACTED_PAT_REVOKED_2026-04-17" -- :
# No output = clean. Any output = run filter-repo.
```

If any output appears, install `git-filter-repo` (`brew install git-filter-repo`) and run:

```bash
git filter-repo --replace-text <(echo "REDACTED_PAT_REVOKED_2026-04-17==>REMOVED")
git push origin --force --all
git push origin --force --tags
```

Then notify every collaborator to re-clone.

---

## Step 6 — Consolidate credentials (2 minutes)

One vault, one source of truth. Put all of these there now, delete from `.env` files and shell history:

- New `todd-gig` PAT (if you created one)
- New `bella-byte` PAT (if applicable)
- Firebase service-account JSON for `gigaton-platform`
- Anthropic API key
- Gemini API key
- GCP Cloud Run deploy key / service account
- Cloudflare API token
- Slack app bot token (for the kernel's Slack bot in Phase 5)

Use **GCP Secret Manager** for anything the kernel will read at runtime, **1Password** for anything Todd reads interactively. Applications should never read secrets from a file checked into git or from a dotfile that could be synced to iCloud/Dropbox.

---

## Step 7 — Confirmation (30 seconds)

When Steps 1 + 4 are done, message me with:

> Phase 0 done. PAT revoked. Remote URLs clean. Ready for kernel freeze.

That unblocks Phase 1 Task 4 and I'll produce the `decision-engine` v2 scaffold in the next turn.

---

## ⚠️ Second P0 finding — Anthropic API key exposure

A live Anthropic API key (`sk-ant-api03-jyeXYeS...`) was embedded in `.env` files at:
- `~/Desktop/gigaton_v3_execution/v3_bundle/gigaton_modular_ai_claude_project_v3/.env`
- `~/[workspace]/gigaton_v3_execution/v3_bundle/gigaton_modular_ai_claude_project_v3/.env`

Both files have been scrubbed and replaced with `PLACEHOLDER-ROTATE-ME-SEE-PHASE_0_RUNBOOK`.

**Todd action — additional 2 minutes:**
1. Go to https://console.anthropic.com/settings/keys
2. Find the key starting `sk-ant-api03-jyeXYeS...`. Click the trash icon. Confirm.
3. Create a new key named `gigaton-v3-backend-2026Q2`. Copy to GCP Secret Manager as secret name `anthropic_api_key`.
4. In the new decision-engine v2 (formerly `v3_bundle/gigaton_modular_ai_claude_project_v3`), update `backend/app/core/config.py` to read from Secret Manager in production and from `.env` only in local dev.
5. Add `.env` to `.gitignore` before the first commit (verify `cat .gitignore | grep "\.env$"` returns a match).

**Why this matters:** An exposed Anthropic key means anyone with read access to the file can burn through your API budget or exfiltrate conversations via your quota. The rotation and vault move closes this.

---

## What Claude already did (no action needed)

- Redacted the live GitHub PAT from `~/Desktop/github-multiaccount/repo_master_list.txt`
- Redacted the live GitHub PAT from both copies of `UNIFIED_DECISION_ENGINE_INTEGRATION.md`
- Redacted the live Anthropic key from both `.env` copies in `v3_bundle/gigaton_modular_ai_claude_project_v3/`
- Verified zero occurrences of either live credential remain in any user-facing file under `Desktop/` or `gigaton_v3_execution/`

## What Claude cannot do (Todd must execute)

- Log into github.com as `todd-gig` and click Delete on the PAT
- Log into console.anthropic.com and click Delete on the Anthropic key
- Rewrite the remote URL in the local `.git/config` (happens on Todd's actual machine, not the sandbox)
- Move credentials into 1Password / GCP Secret Manager
