#!/usr/bin/env bash
# Install OSDImporter plugin into a running LimeSurvey Docker container.
# Usage: ./install.sh [container_name]
set -e

CONTAINER="${1:-limesurvey}"
PLUGIN_DIR="/var/www/html/plugins/OSDImporter"

echo "Copying OSDImporter into $CONTAINER:$PLUGIN_DIR ..."
docker cp OSDImporter "$CONTAINER:$(dirname $PLUGIN_DIR)/"

echo "Setting permissions ..."
docker exec "$CONTAINER" chown -R www-data:www-data "$PLUGIN_DIR"
docker exec "$CONTAINER" chmod -R 755 "$PLUGIN_DIR"

echo "Done. Activate the plugin in Admin → Configuration → Plugin manager."
