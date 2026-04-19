#!/bin/bash
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

git config user.name "paolo2299"
git config user.email "pdlawson1@gmail.com"
