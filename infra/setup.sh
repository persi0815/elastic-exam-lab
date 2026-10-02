#!/usr/bin/env bash
set -euo pipefail
cd /usr/share/elasticsearch
mkdir -p config/certs /snapshots/cluster1 /snapshots/cluster2
if [ ! -f config/certs/transport.p12 ]; then
  if [ ! -f config/certs/ca.p12 ]; then
    bin/elasticsearch-certutil ca --silent --out config/certs/ca.p12 --pass ""
  fi
  bin/elasticsearch-certutil cert --silent --ca config/certs/ca.p12 --ca-pass "" --out config/certs/transport.p12 --pass ""
fi
chown -R 1000:0 config/certs /snapshots/cluster1 /snapshots/cluster2
find config/certs -type d -exec chmod 750 {} \;
find config/certs -type f -exec chmod 640 {} \;
chmod 770 /snapshots/cluster1 /snapshots/cluster2
printf 'Local lab transport certificates and snapshot directories are ready.\n'
