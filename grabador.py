#!/usr/bin/env python3
"""
Grabador - grabador de pantalla para Linux (X11 / Wayland) pensado para NVIDIA NVENC.

Uso:
  grabador.py                 -> abre la interfaz gráfica
  grabador.py grabar [opts]   -> graba desde terminal (Ctrl+C o `grabador.py detener` para parar)
  grabador.py detener         -> detiene la grabación activa (útil para atajo de teclado)
  grabador.py alternar [opts] -> inicia si no hay grabación, detiene si la hay (atajo global)
  grabador.py info            -> muestra sesión, encoders y herramientas detectadas
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

APP = "grabador"
RUNTIME_DIR = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp"))
PIDFILE = RUNTIME_DIR / f"{APP}.pid"
DEFAULT_DIR = Path(os.environ.get("XDG_VIDEOS_DIR", Path.home() / "Videos")) / "Grabador"

RESOLUCIONES = {
    "nativa": None,
    "720p": (1280, 720),
    "900p": (1600, 900),
    "1080p": (1920, 1080),
    "1440p": (2560, 1440),
}
FPS_OPCIONES = [30, 60, 120, 144]
CALIDADES = {  # (cq para nvenc, crf para x264, calidad gsr)
    "media": (26, 26, "medium"),
    "alta": (21, 21, "high"),
    "edicion": (17, 17, "very_high"),   # archivos grandes, ideal para editar
    "ultra": (14, 14, "ultra"),
}


# ----------------------------------------------------------------------------- utilidades
def which(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def run(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def tipo_sesion() -> str:
    t = os.environ.get("XDG_SESSION_TYPE", "").lower()
    if t in ("x11", "wayland"):
        return t
    if os.environ.get("WAYLAND_DISPLAY"):
        return "wayland"
    return "x11" if os.environ.get("DISPLAY") else "desconocida"


def encoders_ffmpeg() -> set[str]:
    if not which("ffmpeg"):
        return set()
    out = run(["ffmpeg", "-hide_banner", "-encoders"])
    return {e for e in ("h264_nvenc", "hevc_nvenc", "av1_nvenc", "libx264", "libx265")
            if re.search(rf"\s{e}\s", out)}


def nvenc_funciona(codec: str = "h264_nvenc") -> bool:
    """ffmpeg puede listar nvenc aunque el driver no lo soporte: hacemos una prueba real."""
    r = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
         "color=black:s=256x256:d=0.1", "-c:v", codec, "-f", "null", "-"],
        capture_output=True, text=True)
    return r.returncode == 0


def pantalla_x11() -> tuple[int, int, int, int, float]:
    """Devuelve (w, h, x, y, refresh) del monitor primario (o del escritorio completo)."""
    out = run(["xrandr", "--current"]) if which("xrandr") else ""
    refresh = 60.0
    m = re.search(r"^\S+ connected primary (\d+)x(\d+)\+(\d+)\+(\d+)", out, re.M) or \
        re.search(r"^\S+ connected (\d+)x(\d+)\+(\d+)\+(\d+)", out, re.M)
    r = re.search(r"(\d+\.\d+)\*", out)
    if r:
        refresh = float(r.group(1))
    if m:
        w, h, x, y = map(int, m.groups())
        return w, h, x, y, refresh
    out = run(["xdpyinfo"]) if which("xdpyinfo") else ""
    m = re.search(r"dimensions:\s+(\d+)x(\d+)", out)
    if m:
        return int(m.group(1)), int(m.group(2)), 0, 0, refresh
    return 1366, 768, 0, 0, refresh


def seleccionar_ventana() -> str | None:
    """El usuario hace clic en una ventana; devuelve su id (X11)."""
    if which("xdotool"):
        out = run(["xdotool", "selectwindow"]).strip()
        return out or None
    if which("xwininfo"):
        m = re.search(r"Window id: (0x[0-9a-f]+)", run(["xwininfo"]))
        return m.group(1) if m else None
    return None


def geometria_ventana(win_id: str) -> tuple[int, int, int, int] | None:
    out = run(["xwininfo", "-id", str(win_id)]) if which("xwininfo") else ""
    vals = {k: int(v) for k, v in re.findall(
        r"(Absolute upper-left X|Absolute upper-left Y|Width|Height):\s+(-?\d+)", out)}
    if len(vals) == 4:
        return (vals["Width"], vals["Height"],
                vals["Absolute upper-left X"], vals["Absolute upper-left Y"])
    return None


def seleccionar_region() -> tuple[int, int, int, int] | None:
    if not which("slop"):
        return None
    out = run(["slop", "-f", "%w %h %x %y"]).split()
    return tuple(map(int, out)) if len(out) == 4 else None  # type: ignore[return-value]


def monitor_audio() -> str:
    """Fuente 'monitor' del sink por defecto = audio del escritorio."""
    sink = run(["pactl", "get-default-sink"]).strip() if which("pactl") else ""
    return f"{sink}.monitor" if sink else "default"


def par(n: int) -> int:
    return n - (n % 2)


# ----------------------------------------------------------------------------- configuración
@dataclass
class Config:
    motor: str = "auto"            # auto | ffmpeg | gsr
    objetivo: str = "pantalla"     # pantalla | ventana | region | enfocada
    resolucion: str = "1080p"
    fps: int = 60
    codec: str = "h264"            # h264 | hevc
    calidad: str = "alta"
    ajuste: str = "barras"         # barras (mantiene proporción) | estirar
    audio_escritorio: bool = True
    microfono: bool = False
    cursor: bool = True
    contenedor: str = "mkv"        # mkv (seguro ante cortes) | mp4
    carpeta: str = str(DEFAULT_DIR)
    ventana_id: str | None = None
    region: tuple[int, int, int, int] | None = None   # w, h, x, y
    extra: list[str] = field(default_factory=list)


def resolver_motor(cfg: Config) -> str:
    if cfg.motor != "auto":
        return cfg.motor
    if which("gpu-screen-recorder"):
        return "gsr"
    return "ffmpeg"


def ruta_salida(cfg: Config) -> Path:
    d = Path(cfg.carpeta).expanduser()
    d.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    tag = cfg.resolucion if cfg.resolucion != "nativa" else "nativa"
    return d / f"grab_{stamp}_{cfg.objetivo}_{tag}_{cfg.fps}fps.{cfg.contenedor}"


def avisos(cfg: Config) -> list[str]:
    msgs = []
    sesion = tipo_sesion()
    if sesion == "x11" or which("xrandr"):
        w, h, _, _, hz = pantalla_x11()
        if cfg.fps > hz + 1:
            msgs.append(f"Tu monitor va a ~{hz:.0f} Hz: a {cfg.fps} fps habrá frames duplicados "
                        f"(útil solo para cámara lenta/edición, no aporta fluidez real).")
        tgt = RESOLUCIONES.get(cfg.resolucion)
        if tgt and (tgt[0] > w or tgt[1] > h) and cfg.objetivo == "pantalla":
            msgs.append(f"Escritorio de {w}x{h} -> {tgt[0]}x{tgt[1]} es reescalado (no añade detalle). "
                        "Para 1080p real usa superres.sh.")
    if sesion == "wayland" and resolver_motor(cfg) == "ffmpeg":
        msgs.append("En Wayland ffmpeg (x11grab) solo verá apps XWayland. Instala gpu-screen-recorder.")
    return msgs


# ----------------------------------------------------------------------------- comandos
def comando_ffmpeg(cfg: Config, salida: Path) -> list[str]:
    if tipo_sesion() == "wayland" and not os.environ.get("DISPLAY"):
        raise RuntimeError("ffmpeg necesita X11. En Wayland usa el motor gpu-screen-recorder.")
    display = os.environ.get("DISPLAY", ":0")
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-stats", "-y"]

    grab = ["-f", "x11grab", "-thread_queue_size", "1024", "-framerate", str(cfg.fps),
            "-draw_mouse", "1" if cfg.cursor else "0"]
    if cfg.objetivo == "pantalla":
        w, h, x, y, _ = pantalla_x11()
        grab += ["-video_size", f"{w}x{h}", "-i", f"{display}+{x},{y}"]
    elif cfg.objetivo in ("ventana", "enfocada"):
        win = cfg.ventana_id
        if cfg.objetivo == "enfocada":
            win = run(["xdotool", "getactivewindow"]).strip() if which("xdotool") else None
        if not win:
            raise RuntimeError("No se pudo obtener la ventana (instala xdotool o xorg-xwininfo).")
        # window_id graba el contenido de la ventana aunque la muevas.
        # Con ffmpeg/x11grab la ventana debe estar visible (no tapada ni minimizada).
        grab += ["-window_id", str(int(str(win), 0)), "-i", display]
    elif cfg.objetivo == "region":
        if not cfg.region:
            raise RuntimeError("No hay región seleccionada (instala slop).")
        w, h, x, y = cfg.region
        grab += ["-video_size", f"{par(w)}x{par(h)}", "-i", f"{display}+{x},{y}"]
    cmd += grab

    n_audio = 0
    if cfg.audio_escritorio:
        cmd += ["-f", "pulse", "-thread_queue_size", "1024", "-i", monitor_audio()]
        n_audio += 1
    if cfg.microfono:
        cmd += ["-f", "pulse", "-thread_queue_size", "1024", "-i", "default"]
        n_audio += 1

    # --- filtros de video
    tgt = RESOLUCIONES.get(cfg.resolucion)
    vf = []
    if tgt:
        W, H = tgt
        if cfg.ajuste == "estirar":
            vf.append(f"scale={W}:{H}:flags=lanczos")
        else:
            vf.append(f"scale={W}:{H}:flags=lanczos:force_original_aspect_ratio=decrease")
            vf.append(f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black")
    else:
        vf.append("scale=trunc(iw/2)*2:trunc(ih/2)*2")
    vf.append("format=yuv420p")
    fc = f"[0:v]{','.join(vf)}[v]"
    maps = ["-map", "[v]"]
    if n_audio == 2:
        fc += ";[1:a][2:a]amix=inputs=2:duration=longest:normalize=0[a]"
        maps += ["-map", "[a]"]
    elif n_audio == 1:
        maps += ["-map", "1:a"]
    cmd += ["-filter_complex", fc] + maps

    # --- encoder
    cq, crf, _ = CALIDADES[cfg.calidad]
    enc = encoders_ffmpeg()
    nv = f"{cfg.codec}_nvenc"
    if nv in enc and nvenc_funciona(nv):
        cmd += ["-c:v", nv, "-preset", "p5", "-tune", "hq", "-rc", "vbr", "-cq", str(cq),
                "-b:v", "0", "-g", str(cfg.fps * 2), "-bf", "0"]
        if cfg.codec == "hevc":
            cmd += ["-tag:v", "hvc1"]
    else:
        sw = "libx265" if cfg.codec == "hevc" else "libx264"
        cmd += ["-c:v", sw, "-preset", "veryfast", "-crf", str(crf), "-g", str(cfg.fps * 2)]
    if n_audio:
        cmd += ["-c:a", "aac", "-b:a", "192k"]
    if cfg.contenedor == "mp4":
        cmd += ["-movflags", "+faststart"]
    cmd += ["-r", str(cfg.fps)] + cfg.extra + [str(salida)]
    return cmd


def comando_gsr(cfg: Config, salida: Path) -> list[str]:
    """gpu-screen-recorder: NVENC directo, graba ventanas tapadas (X11) y funciona en Wayland."""
    sesion = tipo_sesion()
    if cfg.objetivo == "pantalla":
        w = "portal" if sesion == "wayland" else "screen"
    elif cfg.objetivo == "enfocada":
        w = "portal" if sesion == "wayland" else "focused"
    elif cfg.objetivo == "ventana":
        if sesion == "wayland":
            w = "portal"   # el diálogo del sistema te deja elegir ventana
        else:
            if not cfg.ventana_id:
                raise RuntimeError("Selecciona una ventana primero.")
            w = str(int(str(cfg.ventana_id), 0))
    else:  # region
        if not cfg.region:
            raise RuntimeError("No hay región seleccionada (instala slop).")
        rw, rh, rx, ry = cfg.region
        w = "region"
    _, _, q = CALIDADES[cfg.calidad]
    cmd = ["gpu-screen-recorder", "-w", w, "-c", cfg.contenedor, "-f", str(cfg.fps),
           "-k", cfg.codec, "-q", q, "-fm", "cfr", "-cursor", "yes" if cfg.cursor else "no"]
    if w == "region":
        cmd += ["-region", f"{par(rw)}x{par(rh)}+{rx}+{ry}"]
    tgt = RESOLUCIONES.get(cfg.resolucion)
    if tgt:
        cmd += ["-s", f"{tgt[0]}x{tgt[1]}"]
    if cfg.audio_escritorio and cfg.microfono:
        cmd += ["-a", "default_output|default_input"]
    elif cfg.audio_escritorio:
        cmd += ["-a", "default_output"]
    elif cfg.microfono:
        cmd += ["-a", "default_input"]
    cmd += cfg.extra + ["-o", str(salida)]
    return cmd


def construir(cfg: Config) -> tuple[list[str], Path]:
    salida = ruta_salida(cfg)
    motor = resolver_motor(cfg)
    if motor == "gsr":
        return comando_gsr(cfg, salida), salida
    return comando_ffmpeg(cfg, salida), salida


# ----------------------------------------------------------------------------- control de proceso
def pid_activo() -> int | None:
    try:
        pid = int(PIDFILE.read_text().strip())
        os.kill(pid, 0)
        return pid
    except (OSError, ValueError):
        PIDFILE.unlink(missing_ok=True)
        return None


def iniciar(cfg: Config, log=None) -> tuple[subprocess.Popen, Path]:
    if pid_activo():
        raise RuntimeError("Ya hay una grabación en curso.")
    cmd, salida = construir(cfg)
    print("» " + " ".join(cmd), file=sys.stderr)
    proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL,
                            stdout=log or subprocess.DEVNULL, stderr=log or None,
                            start_new_session=True)  # sobrevive si cierras la terminal/GUI
    PIDFILE.write_text(str(proc.pid))
    return proc, salida


def detener(timeout: float = 15) -> bool:
    pid = pid_activo()
    if not pid:
        return False
    os.kill(pid, signal.SIGINT)   # ffmpeg y gsr cierran el archivo correctamente con SIGINT
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            os.kill(pid, 0)
        except OSError:
            break
        time.sleep(0.2)
    else:
        os.kill(pid, signal.SIGTERM)
    PIDFILE.unlink(missing_ok=True)
    return True


def notificar(msg: str) -> None:
    if which("notify-send"):
        subprocess.Popen(["notify-send", "-a", "Grabador", "Grabador", msg])


# ----------------------------------------------------------------------------- CLI
def cfg_desde_args(a: argparse.Namespace) -> Config:
    cfg = Config(motor=a.motor, objetivo=a.objetivo, resolucion=a.resolucion, fps=a.fps,
                 codec=a.codec, calidad=a.calidad, ajuste=a.ajuste,
                 audio_escritorio=not a.sin_audio, microfono=a.mic, cursor=not a.sin_cursor,
                 contenedor=a.contenedor, carpeta=a.carpeta, ventana_id=a.ventana)
    if cfg.objetivo == "ventana" and not cfg.ventana_id and \
            not (tipo_sesion() == "wayland" and resolver_motor(cfg) == "gsr"):
        print("Haz clic en la ventana que quieres grabar…", file=sys.stderr)
        cfg.ventana_id = seleccionar_ventana()
    if cfg.objetivo == "region":
        print("Selecciona la región con el ratón…", file=sys.stderr)
        cfg.region = seleccionar_region()
    return cfg


def cmd_grabar(a: argparse.Namespace) -> int:
    cfg = cfg_desde_args(a)
    for m in avisos(cfg):
        print("⚠ " + m, file=sys.stderr)
    if a.dry_run:
        cmd, salida = construir(cfg)
        print(" ".join(cmd))
        return 0
    proc, salida = iniciar(cfg)
    notificar(f"Grabando → {salida.name}")
    print(f"Grabando en {salida}  (Ctrl+C o `{APP} detener` para parar)", file=sys.stderr)
    try:
        if a.duracion:
            proc.wait(timeout=a.duracion)
        else:
            proc.wait()
    except subprocess.TimeoutExpired:
        detener()
    except KeyboardInterrupt:
        detener()
    proc.wait()
    PIDFILE.unlink(missing_ok=True)
    notificar(f"Guardado: {salida.name}")
    print(f"Guardado: {salida}", file=sys.stderr)
    return 0


def cmd_alternar(a: argparse.Namespace) -> int:
    if pid_activo():
        detener()
        notificar("Grabación detenida")
        return 0
    cfg = cfg_desde_args(a)
    _, salida = iniciar(cfg)
    notificar(f"Grabando → {salida.name}")
    return 0  # el proceso queda en segundo plano; otro `alternar` lo detiene


def cmd_info(_: argparse.Namespace) -> int:
    print(f"Sesión:            {tipo_sesion()}")
    if which("xrandr"):
        w, h, x, y, hz = pantalla_x11()
        print(f"Monitor:           {w}x{h}+{x}+{y} @ {hz:.2f} Hz")
    enc = encoders_ffmpeg()
    print(f"ffmpeg encoders:   {', '.join(sorted(enc)) or '(ffmpeg no instalado)'}")
    if "h264_nvenc" in enc:
        print(f"NVENC funcional:   {'sí' if nvenc_funciona() else 'NO (revisa driver nvidia)'}")
    for t in ("gpu-screen-recorder", "xdotool", "xwininfo", "slop", "pactl", "notify-send"):
        print(f"{t:<19}{'✔' if which(t) else '✘'}")
    print(f"Grabación activa:  {pid_activo() or 'no'}")
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=APP, description="Grabador de pantalla (NVENC)")
    sub = p.add_subparsers(dest="accion")

    def opts(sp):
        sp.add_argument("-m", "--motor", choices=["auto", "ffmpeg", "gsr"], default="auto")
        sp.add_argument("-o", "--objetivo", choices=["pantalla", "ventana", "region", "enfocada"],
                        default="pantalla")
        sp.add_argument("-r", "--resolucion", choices=list(RESOLUCIONES), default="1080p")
        sp.add_argument("-f", "--fps", type=int, default=60)
        sp.add_argument("-c", "--codec", choices=["h264", "hevc"], default="h264")
        sp.add_argument("-q", "--calidad", choices=list(CALIDADES), default="alta")
        sp.add_argument("--ajuste", choices=["barras", "estirar"], default="barras")
        sp.add_argument("--contenedor", choices=["mkv", "mp4"], default="mkv")
        sp.add_argument("--carpeta", default=str(DEFAULT_DIR))
        sp.add_argument("--ventana", help="id de ventana X11 (0x…); si no, haces clic")
        sp.add_argument("--sin-audio", action="store_true")
        sp.add_argument("--mic", action="store_true", help="mezclar micrófono")
        sp.add_argument("--sin-cursor", action="store_true")
        sp.add_argument("-d", "--duracion", type=float, help="segundos (opcional)")
        sp.add_argument("--dry-run", action="store_true", help="solo imprime el comando")

    opts(sub.add_parser("grabar", help="grabar desde la terminal"))
    opts(sub.add_parser("alternar", help="inicia/detiene (para atajo de teclado)"))
    sub.add_parser("detener", help="detiene la grabación activa")
    sub.add_parser("info", help="diagnóstico del sistema")
    sub.add_parser("gui", help="interfaz gráfica (por defecto)")
    return p


def main() -> int:
    a = parser().parse_args()
    if a.accion == "grabar":
        return cmd_grabar(a)
    if a.accion == "alternar":
        return cmd_alternar(a)
    if a.accion == "detener":
        ok = detener()
        print("Detenida." if ok else "No había grabación activa.")
        return 0
    if a.accion == "info":
        return cmd_info(a)
    from grabador_gui import lanzar_gui  # import diferido: la CLI no necesita tkinter
    return lanzar_gui()


if __name__ == "__main__":
    sys.exit(main())
