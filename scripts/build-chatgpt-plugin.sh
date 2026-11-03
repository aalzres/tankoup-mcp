#!/usr/bin/env bash
# Zips directories/chatgpt-plugin into the package the OpenAI Platform's
# Plugins page takes for a directory submission (dist/tankoup-chatgpt-plugin.zip).
set -euo pipefail
cd "$(dirname "$0")/.."

python3 -m json.tool directories/chatgpt-plugin/.codex-plugin/plugin.json >/dev/null
python3 -m json.tool directories/chatgpt-plugin/.mcp.json >/dev/null

mkdir -p dist
rm -f dist/tankoup-chatgpt-plugin.zip
(cd directories/chatgpt-plugin && zip -qrX ../../dist/tankoup-chatgpt-plugin.zip .codex-plugin .mcp.json assets)
unzip -l dist/tankoup-chatgpt-plugin.zip
