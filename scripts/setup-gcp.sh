#!/usr/bin/env bash
# One-time setup in TankoUp's GCP project, run after `gcloud auth login`.
#
# 1. Creates the MCP server's key for the TankoUp API (one row in its api_keys
#    table, with the API's own CLI) and stores it straight in Secret Manager.
#    The key is never printed nor written to disk.
# 2. Creates a service account for the MCP server that can read that secret
#    and nothing else.
#
# Needs a checkout of the TankoUp API (FinderLost/tanko) at $TANKO_DIR.
set -euo pipefail

PROJECT=tanko-up-498117
TANKO_DIR=${TANKO_DIR:-$HOME/develop/tanko}
SECRET=TANKOUP_MCP_API_KEY
SA=tankoup-mcp
SA_EMAIL=$SA@$PROJECT.iam.gserviceaccount.com

if gcloud secrets describe "$SECRET" --project "$PROJECT" >/dev/null 2>&1; then
  echo "secret $SECRET already exists, keeping it"
else
  key="$(
    cd "$TANKO_DIR"
    TANKO_DATABASE_URL="$(gcloud secrets versions access 1 --secret TANKO_DATABASE_URL --project "$PROJECT")" \
    TANKO_API_KEY_SECRET="$(gcloud secrets versions access 1 --secret TANKO_API_KEY_SECRET --project "$PROJECT")" \
      uv run --frozen python -m app.cli key-create mcp | sed -n 2p | tr -d ' '
  )"
  if [[ "$key" != tanko_* ]]; then
    echo "key-create did not return a key; nothing stored" >&2
    exit 1
  fi
  printf '%s' "$key" | gcloud secrets create "$SECRET" --project "$PROJECT" \
    --replication-policy=automatic --data-file=-
  unset key
  echo "created API key 'mcp' and stored it in $SECRET"
fi

if ! gcloud iam service-accounts describe "$SA_EMAIL" --project "$PROJECT" >/dev/null 2>&1; then
  gcloud iam service-accounts create "$SA" --project "$PROJECT" --display-name "TankoUp MCP server"
fi
gcloud secrets add-iam-policy-binding "$SECRET" --project "$PROJECT" \
  --member "serviceAccount:$SA_EMAIL" --role roles/secretmanager.secretAccessor >/dev/null
echo "service account $SA_EMAIL can read $SECRET"
