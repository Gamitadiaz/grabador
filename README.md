# Grabador

Grabador de pantalla para Linux (Arch), pensado para NVIDIA NVENC (RTX 3060).
Graba **pantalla completa, una ventana, una región o la ventana enfocada**, a
720p / 900p / 1080p / 1440p / nativa y 30 / 60 / 120 / 144 fps.

## Instalación (Arch)

```bash
./install.sh
```

Recomendado (AUR): `yay -S gpu-screen-recorder` — graba ventanas **aunque estén tapadas** y funciona en Wayland.

## Uso sin terminal

Abre **Grabador** desde el menú de aplicaciones. Elige qué grabar, resolución y fps, y pulsa **● Grabar**.
Tu configuración se recuerda (`~/.config/grabador/config.json`). Lo técnico está en **▸ Avanzado**.

**Al grabar** la ventana se oculta y queda un indicador:

| Opción | Qué hace | Cuándo |
|---|---|---|
| `auto` | pantalla completa → bandeja; ventana/región → mini barra | recomendado |
| `mini barra` | ventanita flotante `● 00:42 ■`, arrastrable, siempre encima | grabar una ventana o región |
| `bandeja` | icono junto al reloj; clic = detener (requiere `yad`) | pantalla completa / juegos |
| `minimizar` | solo minimiza la ventana | si tu panel no tiene bandeja |

Ojo: si grabas **pantalla completa** con la mini barra, la barra sale en el video. Por eso `auto` usa la bandeja.

**Consumo**: la interfaz usa ~25 MB de RAM y ~0 % CPU (se actualiza 1 vez por segundo). Lo que consume es
codificar el video, y eso lo hace la GPU (NVENC/VAAPI).

## Uso desde terminal

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

## Gráficas compatibles

No necesitas NVIDIA. El encoder se elige solo (`grabador info` muestra cuál):

| Gráfica | Codificación | Supermuestreo (1080p real) |
|---|---|---|
| NVIDIA | NVENC | `nvidia-settings` ViewPortIn |
| Intel integrada / AMD | VAAPI (hardware) | `xrandr --scale-from` |
| Cualquier otra | CPU (libx264) | `xrandr --scale-from` |

Forzar uno: `grabador grabar -e vaapi` / `-e nvenc` / `-e cpu`. Si VAAPI sale "no" en Intel viejo
(antes de Broadwell, ~2014): `sudo pacman -S libva-intel-driver`. Verifica con `vainfo`.

## Motores

| | ffmpeg (x11grab + NVENC) | gpu-screen-recorder |
|---|---|---|
| X11 pantalla / región | ✔ | ✔ |
| X11 ventana | ✔ (debe estar visible) | ✔ aunque esté tapada |
| Wayland | ✘ | ✔ (diálogo del portal) |
| Uso de CPU | bajo-medio (escalado en CPU) | mínimo (todo en GPU) |

`auto` usa gpu-screen-recorder si está instalado; si no, ffmpeg. Si NVENC no funciona cae a libx264.

## Resolución REAL sin escalado (juegos y navegador)

Tu panel es 1366×768. En lugar de agrandar el video después (pierde nitidez), Grabador hace que la GPU
**dibuje todo el escritorio a 1920×1080** y lo reduzca a tu monitor (lo mismo que DSR en Windows).
El juego y el navegador renderizan 1080p de verdad y la grabación captura esos píxeles.

```bash
grabador superres 1920x1080      # (o botón "Activar" en la GUI, con auto-revertir en 15 s)
grabador navegador chrome        # Chrome a escala 1.41: en tu monitor se ve de tamaño normal
grabador grabar -r nativa -f 60  # = 1920x1080 reales
grabador superres off            # volver a la normalidad
```

- **Navegador**: con escala 1.41 la página se ve igual de grande que siempre en tu monitor, pero se dibuja con
  1.41× más píxeles. Chrome debe estar **totalmente cerrado** antes de abrirlo así (si no, ignora el flag).
  Firefox: `about:config` → `layout.css.devPixelsPerPx = 1.41` (pon `-1` para quitarlo), o zoom 140 % (Ctrl +).
  Juegos de canvas/WebGL que respetan `devicePixelRatio` (Unity WebGL, Phaser, la mayoría de .io modernos)
  renderizan a 1080p real. Si un juego tiene un canvas de tamaño fijo, ni esto ni nada le da más detalle.
- **Juegos nativos / Steam (Proton)**: ponlos en pantalla completa a 1920×1080.
- **Costo**: la GPU dibuja ~2× píxeles. Para juegos de navegador la 3060 sobra; en juegos pesados perderás fps.
- 2560×1440 → grabar en `1080p` = supersampling (más nítido aún), a cambio de más GPU.
- Requiere **sesión X11** (en Wayland no existe este escalado; elige "Plasma (X11)" / "Xorg" en el login).
  Usa `nvidia-settings` (ViewPortIn) si está; si no, `xrandr --scale-from`.

## Otras notas

- **FPS mayores al refresco del monitor** (~60 Hz) producen frames duplicados. 120/144 solo tiene sentido para
  juegos que rendericen más fps o para cámara lenta.
- Calidades: `media` (CQ 26), `alta` (21), `edicion` (17), `ultra` (14). Para YouTube, `alta`/`edicion` en 1080p60.

## Segundo plano

- La GUI se minimiza al grabar; si la cierras eligiendo "No", la grabación sigue y se para con `grabador detener`.
- `grabador alternar` + atajo de teclado = grabación sin ventana visible.
