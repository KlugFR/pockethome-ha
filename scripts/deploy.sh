#!/bin/sh
# Copie l'intégration sur Home Assistant OS (SSH) et la redémarre.  Usage : scripts/deploy.sh root@<ip-de-ha>
set -e
[ -n "$1" ] || { echo "usage: $0 root@<ip-de-ha>" >&2; exit 1; }
cd "$(dirname "$0")/.."
scp -r custom_components/pockethome "$1:/config/custom_components/"
# Icône personnelle facultative (non publiée) : local-brand/icon.png et icon@2x.png remplacent celle du dépôt
[ -d local-brand ] && scp local-brand/*.png "$1:/config/custom_components/pockethome/brand/"
ssh "$1" "ha core restart"
