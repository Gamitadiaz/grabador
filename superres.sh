#!/usr/bin/env bash
# Renderiza el escritorio a una resolución mayor que la del monitor y la reduce al panel.
# Así la grabación a 1080p es REAL (no reescalada). Solo X11.
#   ./superres.sh 1920x1080   -> escritorio a 1080p mostrado en tu 1366x768
#   ./superres.sh off         -> vuelve a la normalidad
set -euo pipefail
MODO="${1:-1920x1080}"
OUT=$(xrandr --current | awk '/ connected primary/{print $1; exit}')
[[ -z "$OUT" ]] && OUT=$(xrandr --current | awk '/ connected/{print $1; exit}')
NATIVA=$(xrandr --current | awk -v o="$OUT" '$1==o{f=1;next} f&&/\+/{print $1; exit}')

if [[ "$MODO" == "off" ]]; then
  if command -v nvidia-settings >/dev/null && nvidia-settings -q gpus >/dev/null 2>&1; then
    nvidia-settings --assign CurrentMetaMode="$OUT: nvidia-auto-select +0+0 {ViewPortIn=$NATIVA, ViewPortOut=$NATIVA+0+0}" >/dev/null
  else
    xrandr --output "$OUT" --mode "$NATIVA" --scale 1x1 --panning 0x0
  fi
  echo "Restaurado a $NATIVA"; exit 0
fi

if command -v nvidia-settings >/dev/null && nvidia-settings -q gpus >/dev/null 2>&1; then
  # Método NVIDIA: escalado por la GPU, sin parpadeo de cursor y con buen filtrado.
  nvidia-settings --assign CurrentMetaMode="$OUT: nvidia-auto-select +0+0 {ViewPortIn=$MODO, ViewPortOut=$NATIVA+0+0}" >/dev/null
else
  # Método genérico xrandr.
  W=${MODO%x*}; H=${MODO#*x}; NW=${NATIVA%x*}; NH=${NATIVA#*x}
  SX=$(awk "BEGIN{printf \"%.4f\", $W/$NW}"); SY=$(awk "BEGIN{printf \"%.4f\", $H/$NH}")
  xrandr --output "$OUT" --mode "$NATIVA" --scale "${SX}x${SY}" --panning "${MODO}"
fi
echo "Escritorio a $MODO en $OUT (panel $NATIVA). Graba con resolución 'nativa'. Vuelve con: $0 off"
