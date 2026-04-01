#!/bin/bash
# deploy.sh — Sync private website code to production server.
#
# Assumes the public repo (openscales/) has already been cloned on the server:
#   git clone https://github.com/stmueller/openscales.git /var/www/openscales/openscales
#
# This script syncs only the private website/ files. The server's web root
# should be configured to serve /var/www/openscales/website/, with
# /var/www/openscales/openscales/ as the sibling directory.
#
# Usage:
#   ./tools/deploy.sh
#   REMOTE=user@myserver.com:/var/www/openscales/ ./tools/deploy.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

REMOTE="${REMOTE:-user@server:/var/www/openscales/}"

echo "Deploying website/ to $REMOTE ..."
rsync -av \
  --exclude='.git' \
  --exclude='tmp/' \
  --exclude='*.log' \
  "$REPO_ROOT/website/" \
  "$REMOTE/website/"

echo "Done."
echo ""
echo "Remember to update the public repo on the server:"
echo "  ssh $REMOTE 'git -C openscales/ pull'"
