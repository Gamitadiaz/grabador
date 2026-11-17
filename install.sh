#!/usr/bin/env bash
# Instala dependencias (Arch) y deja `grabador` en ~/.local/bin + lanzador en el menú.
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
if command -v pacman >/dev/null; then
  sudo pacman -S --needed ffmpeg tk xdotool xorg-xwininfo xorg-xrandr slop libpulse libnotify nvidia-settings
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
