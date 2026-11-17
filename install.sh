#!/usr/bin/env bash
# Instala dependencias (Arch) y deja `grabador` en ~/.local/bin + lanzador en el menú.
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
if command -v pacman >/dev/null; then
  PKGS=(ffmpeg tk xdotool xorg-xwininfo xorg-xrandr slop libpulse libnotify libva-utils yad xdg-utils)
  GPUS=$(lspci -nn 2>/dev/null | grep -Ei 'vga|3d|display' || true)
  echo "$GPUS"
  grep -qi nvidia <<<"$GPUS" && PKGS+=(nvidia-settings)
  grep -qi intel  <<<"$GPUS" && PKGS+=(intel-media-driver)   # VAAPI Intel (Broadwell o más nuevo)
  grep -Eqi 'amd|ati|radeon' <<<"$GPUS" && PKGS+=(mesa)      # VAAPI AMD (incluido en mesa)
  sudo pacman -S --needed "${PKGS[@]}"
  echo "Opcional (recomendado): gpu-screen-recorder desde AUR ->  yay -S gpu-screen-recorder"
fi
chmod +x "$DIR/grabador.py" "$DIR/superres.sh"
mkdir -p ~/.local/bin ~/.local/share/applications
ln -sf "$DIR/grabador.py" ~/.local/bin/grabador
cat > ~/.local/share/applications/grabador.desktop <<D
[Desktop Entry]
Name=Grabador
Comment=Grabar pantalla o ventanas (NVENC)
Exec=$HOME/.local/bin/grabador
Icon=media-record
Terminal=false
Type=Application
Categories=AudioVideo;Recorder;
D
echo "Listo. Ejecuta: grabador   (asegúrate de tener ~/.local/bin en el PATH)"
