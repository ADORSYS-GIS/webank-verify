#!/usr/bin/env bash
# Download MaxMind GeoLite2-Country database
set -euo pipefail

if [ -z "${MAXMIND_LICENSE_KEY:-}" ]; then
    echo "MAXMIND_LICENSE_KEY not set — skipping GeoIP download"
    exit 0
fi

mkdir -p ./data
URL="https://download.maxmind.com/app/geoip_download?edition_id=GeoLite2-Country&license_key=${MAXMIND_LICENSE_KEY}&suffix=tar.gz"
curl -sL "$URL" -o /tmp/geoip.tar.gz
tar -xzf /tmp/geoip.tar.gz -C /tmp
find /tmp -name "GeoLite2-Country.mmdb" -exec mv {} ./data/GeoLite2-Country.mmdb \;
rm -f /tmp/geoip.tar.gz
echo "GeoLite2-Country.mmdb downloaded to ./data/"
