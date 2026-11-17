# Grabador

Grabador de pantalla para Linux (Arch), pensado para NVIDIA NVENC (RTX 3060).
Graba **pantalla completa, una ventana, una región o la ventana enfocada**, a
720p / 900p / 1080p / 1440p / nativa y 30 / 60 / 120 / 144 fps.

## Instalación (Arch)

```bash
./install.sh
```

Recomendado (AUR): `yay -S gpu-screen-recorder` — graba ventanas **aunque estén tapadas** y funciona en Wayland.

## Uso

```bash
grabador                                   # interfaz gráfica
grabador info                              # diagnóstico: sesión, monitor, NVENC, herramientas
grabador grabar -r 1080p -f 60             # pantalla completa a 1080p60
grabador grabar -o ventana -r 1080p -f 60  # haces clic en la ventana a grabar
grabador grabar -o region -r 720p -f 30    # seleccionas región con el ratón (slop)
grabador grabar -q edicion -c hevc --mic   # máxima calidad para editar, HEVC, con micrófono
grabador detener                           # detiene lo que esté grabando (GUI o CLI)
grabador alternar -r 1080p -f 60           # inicia/detiene: bindéalo a una tecla (p.ej. Super+R)
```

Los videos van a `~/Videos/Grabador/` (en `.mkv` por defecto: si se corta la luz el archivo sigue sirviendo;
`--contenedor mp4` si lo prefieres). Para pasar mkv a mp4 sin recodificar:
`ffmpeg -i in.mkv -c copy out.mp4`.

## Motores

| | ffmpeg (x11grab + NVENC) | gpu-screen-recorder |
|---|---|---|
| X11 pantalla / región | ✔ | ✔ |
| X11 ventana | ✔ (debe estar visible) | ✔ aunque esté tapada |
| Wayland | ✘ | ✔ (diálogo del portal) |
| Uso de CPU | bajo-medio (escalado en CPU) | mínimo (todo en GPU) |

`auto` usa gpu-screen-recorder si está instalado; si no, ffmpeg. Si NVENC no funciona cae a libx264.

## Notas importantes sobre calidad

- **Tu monitor es 1366×768**: grabar a 1080p **reescala**, no añade detalle (sirve para que el timeline del editor sea 1080p).
  Para **1080p real**, renderiza el escritorio a 1920×1080 y que la GPU lo reduzca al panel:
  ```bash
  ./superres.sh 1920x1080   # luego graba con resolución "nativa"
  ./superres.sh off
  ```
  (X11; usa `nvidia-settings` ViewPortIn si está disponible, si no `xrandr --scale`.) El texto se verá más pequeño en tu monitor, pero la grabación tendrá detalle real.
- **FPS mayores al refresco del monitor** (~60 Hz) producen frames duplicados. 120/144 solo tiene sentido para juegos que rendericen más fps o para cámara lenta.
- Calidades: `media` (CQ 26), `alta` (21), `edicion` (17), `ultra` (14). Para editar en DaVinci Resolve en Linux, considera recodificar a DNxHR o usar HEVC.

## Segundo plano

- La GUI se minimiza al grabar; si la cierras eligiendo "No", la grabación sigue y se para con `grabador detener`.
- `grabador alternar` + atajo de teclado = grabación sin ventana visible.
