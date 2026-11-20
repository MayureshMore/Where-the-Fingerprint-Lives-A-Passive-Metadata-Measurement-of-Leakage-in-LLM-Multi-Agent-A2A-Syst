#!/usr/bin/env bash
#
# a2a-leakcheck, stage 1: download the C2 header-only captures from Zenodo, check them against
# SHA256SUMS.txt (committed next to this script) and unpack them into downloads/.
#
# Usage: ./1_analysis_object/a2a-leakcheck/fetch.sh
# Needs curl, and unzip or python3. Downloads 22 MB once; later runs reuse the checked file.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RECORD=24238559                                   # doi:10.5281/zenodo.24238559, version 1.0
BASE="https://zenodo.org/records/$RECORD/files"
FILE=c2-raw-pcaps-headers-only.zip
DL="$HERE/downloads"
mkdir -p "$DL"

sha256() {
    if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | cut -d' ' -f1
    else shasum -a 256 "$1" | cut -d' ' -f1; fi
}

want=$(awk -v f="$FILE" '$2 == f { print $1 }' "$HERE/SHA256SUMS.txt")
[ -n "$want" ] || { echo "no checksum for $FILE in SHA256SUMS.txt" >&2; exit 1; }

curl -fsSL --retry 3 -o "$DL/SHA256SUMS.txt" "$BASE/SHA256SUMS.txt?download=1"
if ! cmp -s "$DL/SHA256SUMS.txt" "$HERE/SHA256SUMS.txt"; then
    echo "the record's SHA256SUMS.txt differs from the committed copy" >&2
    exit 1
fi

if [ -f "$DL/$FILE" ] && [ "$(sha256 "$DL/$FILE")" = "$want" ]; then
    echo "$FILE: already downloaded"
else
    echo "downloading $FILE (22 MB) from zenodo.org, record $RECORD"
    curl -fsSL --retry 3 -o "$DL/$FILE.part" "$BASE/$FILE?download=1"
    mv "$DL/$FILE.part" "$DL/$FILE"
fi
got=$(sha256 "$DL/$FILE")
if [ "$got" != "$want" ]; then
    echo "$FILE: sha256 $got, expected $want" >&2
    exit 1
fi
echo "$FILE: sha256 matches SHA256SUMS.txt"

if [ ! -f "$DL/data/raw_c2_padmax/session_meta.json" ]; then
    if command -v unzip >/dev/null 2>&1; then
        unzip -q -o "$DL/$FILE" -d "$DL"
    else
        python3 -m zipfile -e "$DL/$FILE" "$DL"
    fi
fi
for arm in raw_c2 raw_c2_pad raw_c2_padmax; do
    echo "  downloads/data/$arm: $(find "$DL/data/$arm" -name '*.pcap' | wc -l | tr -d ' ') captures"
done
