#!/bin/sh
# Crée dist/pockethome-<version>.zip : le dossier custom_components/pockethome/ prêt à décompresser dans /config/.
set -e
cd "$(dirname "$0")/.."
version=$(python3 -c "import json;print(json.load(open('custom_components/pockethome/manifest.json'))['version'])")
mkdir -p dist
rm -f "dist/pockethome-$version.zip"
zip -qr "dist/pockethome-$version.zip" custom_components/pockethome -x '*/__pycache__/*' '*.DS_Store'
echo "dist/pockethome-$version.zip"
