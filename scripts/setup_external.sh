#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXTERNAL_ROOT="${EXTERNAL_ROOT:-$(cd "$ROOT_DIR/.." && pwd)/_external}"
GPT_SOVITS_DIR="${GPT_SOVITS_DIR:-$EXTERNAL_ROOT/GPT-SoVITS}"
ECDICT_DIR="${ECDICT_DIR:-$EXTERNAL_ROOT/ECDICT}"
ECDICT_CSV_PATH="${ECDICT_CSV_PATH:-$ECDICT_DIR/ecdict.csv}"

echo "[setup] project root: $ROOT_DIR"
echo "[setup] external root: $EXTERNAL_ROOT"

mkdir -p "$EXTERNAL_ROOT" "$ECDICT_DIR"

if [[ ! -d "$GPT_SOVITS_DIR/.git" ]]; then
  echo "[setup] cloning GPT-SoVITS into $GPT_SOVITS_DIR"
  git clone https://github.com/RVC-Boss/GPT-SoVITS.git "$GPT_SOVITS_DIR"
else
  echo "[setup] GPT-SoVITS already present: $GPT_SOVITS_DIR"
fi

cat <<EOF

[setup] external dependency layout

  GPT-SoVITS: $GPT_SOVITS_DIR
  ECDICT dir : $ECDICT_DIR
  ECDICT csv : $ECDICT_CSV_PATH

Next steps:

1. Place or download ecdict.csv at:
   $ECDICT_CSV_PATH

2. If GPT-SoVITS needs fast-langdetect, place:
   lid.176.bin
   under:
   $GPT_SOVITS_DIR/GPT_SoVITS/pretrained_models/fast_langdetect/

3. Start GPT-SoVITS separately, then point EngWords to it with:
   VOCABOS_TTS_API_URL=http://127.0.0.1:9880/tts

4. Import ECDICT into EngWords when ready:
   python -m data_pipeline.import_ecdict "$ECDICT_CSV_PATH"

This script prepares external directories only. It does not vendor GPT-SoVITS or ECDICT into this repository.
EOF
