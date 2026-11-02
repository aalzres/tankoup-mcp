#!/usr/bin/env bash
# Builds the image in Cloud Build and deploys it to Cloud Run. Needs
# scripts/setup-gcp.sh to have run once.
#
# Scales to zero and never past one instance: an idle server costs nothing,
# and the in-memory rate limits are the service's real limits.
set -euo pipefail
cd "$(dirname "$0")/.."

PROJECT=tanko-up-498117
REGION=europe-west1

gcloud run deploy tankoup-mcp \
  --source . \
  --project "$PROJECT" \
  --region "$REGION" \
  --service-account "tankoup-mcp@$PROJECT.iam.gserviceaccount.com" \
  --allow-unauthenticated \
  --min-instances 0 \
  --max-instances 1 \
  --concurrency 80 \
  --cpu 1 \
  --memory 512Mi \
  --cpu-throttling \
  --timeout 60 \
  --set-secrets TANKOUP_API_KEY=TANKOUP_MCP_API_KEY:1 \
  --quiet
