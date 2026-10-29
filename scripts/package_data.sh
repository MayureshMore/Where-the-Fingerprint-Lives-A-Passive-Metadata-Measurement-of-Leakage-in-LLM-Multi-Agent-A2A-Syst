#!/usr/bin/env bash
#
# package_data.sh — build the publishable data archives from a populated data/.
#
# Produces two zips under dist/ :
#   dist/a2a-features.zip    the processed feature sets listed below (.npz + labels.json)
#                            — the closed-world, transfer, WAN and confound stages
#   dist/a2a-raw-pcaps.zip   the raw capture sets listed below, stripped to packet headers
#                            (scripts/strip_payload.py) + label sidecars
#                            — needed by the a2a_mcp, AutoGen, CrewAI, defense-overhead and
#                              mixing stages, and to re-extract features from scratch
#
# Only the datasets the paper's results are computed from are packaged (an explicit list,
# so scratch or superseded collections under data/ never leak into the release).
#
# The canonical results (data/results/) are committed in the repo and are NOT
# packaged here.  Upload the two zips to Zenodo/figshare/OSF, then paste the
# resulting DOI/URL and both SHA-256 values from dist/SHA256SUMS.txt into DATA.md
# (the single place they are recorded).  The checksum lets an artifact
# evaluator verify the download matches the release before reproducing.
#
# Usage:
#   bash scripts/package_data.sh
#
set -euo pipefail

OUT="dist"
mkdir -p "$OUT"

# Exclude caches and any stray result dirs that may live under data/.
EXCLUDES=(-x "*/__pycache__/*" -x "*.DS_Store")

# Portable SHA-256 (macOS: shasum -a 256; Linux: sha256sum).
sha256() { if command -v sha256sum >/dev/null 2>&1; then sha256sum "$@"; else shasum -a 256 "$@"; fi; }

# Datasets behind data/results/ (keep in sync with scripts/reproduce.sh).
PROCESSED=(processed processed_amodel_sdk processed_b_sdk processed_blogic_sdk processed_langgraph
           processed_background processed_background_sdk processed_defense_pad processed_defense_rate
           processed_wan processed_offtheshelf processed_interleaved_a processed_interleaved_a_pwr
           processed_interleaved_b processed_interleaved_langgraph processed_wf_interleaved
           processed_wf_interleaved_full)
RAW=(raw raw_amodel_sdk raw_b_sdk raw_blogic_sdk raw_langgraph raw_background raw_background_sdk
     raw_defense_pad raw_defense_rate raw_wan raw_offtheshelf raw_offtheshelf_inst2
     raw_offtheshelf_inst2_natural raw_interleaved_a raw_interleaved_a_pwr raw_interleaved_b
     raw_interleaved_langgraph raw_wf_interleaved raw_wf_interleaved_full
     raw_autogen raw_crewai raw_crewai_matched)
# Packaged only once collected (scripts/run_tls_control.sh).
OPTIONAL_PROCESSED=(processed_tlspair_clear processed_tlspair_tls)
OPTIONAL_RAW=(raw_tlspair_clear raw_tlspair_tls)
for n in "${OPTIONAL_PROCESSED[@]}"; do [ -d "data/$n" ] && PROCESSED+=("$n"); done
for n in "${OPTIONAL_RAW[@]}"; do [ -d "data/$n" ] && RAW+=("$n"); done

PY="${PYTHON:-python3}"
case "$PY" in */*) PY="$(cd "$(dirname "$PY")" && pwd)/$(basename "$PY")" ;; esac   # absolute, survives cd
REPO="$PWD"
STAGE="$OUT/stage_stripped"

# Zip a list of <root>/data/<name>/ sets into one archive (paths inside the zip start at
# data/), failing loudly on any missing set.
pack() {
  local name="$1" root="$2"; shift 2
  local zipfile="$REPO/$name" dirs=() n
  for n in "$@"; do
    [ -d "$root/data/$n" ] || { echo "  MISSING data/$n — collect or unpack it first" >&2; exit 1; }
    dirs+=("data/$n/")
  done
  rm -f "$zipfile"
  ( cd "$root" && zip -r -q "$zipfile" "${dirs[@]}" "${EXCLUDES[@]}" )
  echo "  wrote $name (${#dirs[@]} sets, $(du -h "$zipfile" | cut -f1))"
}

echo "== packaging feature matrices =="
pack "$OUT/a2a-features.zip" . "${PROCESSED[@]}"

# Raw captures are stored at a 96-byte snaplen, which keeps a 20-40 byte slice of
# cleartext payload per packet. Strip every packet to its headers on a staging copy
# (timestamps and on-wire lengths kept, so features are unchanged), verify, then zip.
echo "== stripping payload bytes from raw captures =="
rm -rf "$STAGE"
raw_paths=(); for n in "${RAW[@]}"; do raw_paths+=("data/$n"); done
"$PY" scripts/strip_payload.py --out "$STAGE" "${raw_paths[@]}"
( cd "$STAGE" && "$PY" "$REPO/scripts/strip_payload.py" --check data/* )

echo "== packaging raw captures (header-only) =="
pack "$OUT/a2a-raw-pcaps.zip" "$STAGE" "${RAW[@]}"
rm -rf "$STAGE"

# ── Checksums (so a downloader can verify integrity before reproducing) ───────
echo "== writing checksums =="
( cd "$OUT" && rm -f SHA256SUMS.txt && for z in a2a-features.zip a2a-raw-pcaps.zip; do
    [ -e "$z" ] && sha256 "$z" >> SHA256SUMS.txt; done )
if [ -s "$OUT/SHA256SUMS.txt" ]; then
  echo "  wrote $OUT/SHA256SUMS.txt:"; sed 's/^/    /' "$OUT/SHA256SUMS.txt"
else
  echo "  (no archives were built, so no checksums written)" >&2
fi

echo ""
echo "Done. Next steps:"
echo "  1. Upload dist/*.zip + dist/SHA256SUMS.txt to Zenodo/figshare/OSF (human step)."
echo "  2. Paste the DOI/URL and both SHA-256 values into DATA.md so downloaders can verify."
