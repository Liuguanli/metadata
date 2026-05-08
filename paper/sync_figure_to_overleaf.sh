#!/usr/bin/env bash
set -euo pipefail

OVERLEAF_ROOT="/Users/guanlil1/Dropbox/应用/Overleaf/Metadata-management"
SOURCE=""
TARGET_NAME=""
CAPTION=""
LABEL=""
WIDTH="0.92\\columnwidth"
APPLY="true"

usage() {
  cat <<'EOF'
Usage:
  bash paper/sync_figure_to_overleaf.sh \
    --source <local-image-path> \
    --target-name <name-in-overleaf> \
    --caption "<figure caption>" \
    --label <fig:label> \
    [--width <latex-width>] \
    [--apply true|false] \
    [--overleaf-root <path>]

Example:
  bash paper/sync_figure_to_overleaf.sh \
    --source experiment_results/figures/figure_safety.png \
    --target-name figure_safety.png \
    --caption "Safety comparison under synthetic workload." \
    --label fig:safety
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --source) SOURCE="$2"; shift 2 ;;
    --target-name) TARGET_NAME="$2"; shift 2 ;;
    --caption) CAPTION="$2"; shift 2 ;;
    --label) LABEL="$2"; shift 2 ;;
    --width) WIDTH="$2"; shift 2 ;;
    --apply) APPLY="$2"; shift 2 ;;
    --overleaf-root) OVERLEAF_ROOT="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1"; usage; exit 1 ;;
  esac
done

if [ -z "$SOURCE" ] || [ -z "$TARGET_NAME" ] || [ -z "$CAPTION" ] || [ -z "$LABEL" ]; then
  usage
  exit 1
fi

if [ ! -f "$SOURCE" ]; then
  echo "Source not found: $SOURCE"
  exit 1
fi

FIG_DIR="${OVERLEAF_ROOT}/figures"
TEX_FILE="${OVERLEAF_ROOT}/VLDB.tex"
DEST="${FIG_DIR}/${TARGET_NAME}"

mkdir -p "$FIG_DIR"
cp "$SOURCE" "$DEST"
echo "Copied figure to: $DEST"

SNIP_FILE="$(mktemp)"
cat > "$SNIP_FILE" <<EOF
\\begin{figure}[t]
\\centering
\\includegraphics[width=${WIDTH}]{figures/${TARGET_NAME}}
\\caption{${CAPTION}}
\\label{${LABEL}}
\\end{figure}
EOF

if [ "${APPLY}" = "true" ]; then
  if [ ! -f "$TEX_FILE" ]; then
    echo "TeX file not found: $TEX_FILE"
    rm -f "$SNIP_FILE"
    exit 1
  fi

  TMP_TEX="$(mktemp)"
  awk -v snip_file="$SNIP_FILE" '
    BEGIN { inserted=0 }
    {
      if (!inserted && $0 ~ /\\bibliography\{/) {
        while ((getline line < snip_file) > 0) print line
        print ""
        inserted=1
      }
      print $0
    }
    END {
      if (!inserted) {
        print ""
        while ((getline line < snip_file) > 0) print line
      }
      close(snip_file)
    }
  ' "$TEX_FILE" > "$TMP_TEX"
  mv "$TMP_TEX" "$TEX_FILE"
  echo "Applied figure block into: $TEX_FILE"
else
  echo "Apply disabled. Figure block prepared only."
fi

echo "----- Figure LaTeX -----"
cat "$SNIP_FILE"
rm -f "$SNIP_FILE"
