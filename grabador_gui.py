"""Interfaz gráfica (tkinter) del Grabador."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import grabador as g

CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "grabador" / "config.json"
AL_GRABAR = ["auto", "mini barra", "bandeja", "minimizar"]


class MiniBarra(tk.Toplevel):
    """Ventanita flotante: ● 00:00  ■  (arrastrable, siempre encima, ~0% CPU)."""

    def __init__(self, master: "App") -> None:
        super().__init__(master)
        self.overrideredirect(True)          # sin bordes ni barra de título
        self.attributes("-topmost", True)
        try:
            self.attributes("-alpha", 0.85)
        except tk.TclError:
            pass
        self.configure(bg="#1e1e1e")
        self.punto = tk.Label(self, text="●", fg="#ff3b30", bg="#1e1e1e", font=("Sans", 12))
        self.punto.pack(side="left", padx=(8, 2))
        self.tiempo = tk.Label(self, text="00:00", fg="white", bg="#1e1e1e", font=("Monospace", 10))
        self.tiempo.pack(side="left", padx=4)
        stop = tk.Label(self, text="■", fg="white", bg="#3a3a3a", font=("Sans", 11),
                        padx=8, cursor="hand2")
        stop.pack(side="left", padx=(4, 4), pady=4)
        stop.bind("<Button-1>", lambda _e: master._toggle())
        for w in (self, self.punto, self.tiempo):
            w.bind("<ButtonPress-1>", self._ini)
            w.bind("<B1-Motion>", self._mover)
        self.update_idletasks()
        self.geometry(f"+{self.winfo_screenwidth() - self.winfo_width() - 20}+20")
        self._visible = True

    def _ini(self, e):
        self._dx, self._dy = e.x_root - self.winfo_x(), e.y_root - self.winfo_y()

    def _mover(self, e):
        self.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")

    def actualizar(self, seg: int) -> None:
        self.tiempo.config(text=f"{seg // 60:02d}:{seg % 60:02d}" if seg < 3600
                           else f"{seg // 3600}:{seg % 3600 // 60:02d}:{seg % 60:02d}")
        self._visible = not self._visible     # parpadeo del punto
        self.punto.config(fg="#ff3b30" if self._visible else "#1e1e1e")


class Bandeja:
    """Icono en la bandeja del sistema usando `yad` (pacman -S yad). Clic = detener."""

    def __init__(self) -> None:
        self.p: subprocess.Popen | None = None
        if not g.which("yad"):
            return
        detener = f"{sys.executable} {Path(g.__file__).resolve()} detener"
        self.p = subprocess.Popen(
            ["yad", "--notification", "--listen", "--image=media-record",
             "--text=Grabando – clic para detener", f"--command={detener}",
             f"--menu=Detener grabación!{detener}"],
            stdin=subprocess.PIPE, text=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    @property
    def activa(self) -> bool:
        return self.p is not None

    def actualizar(self, seg: int) -> None:
        if self.p and self.p.poll() is None and seg % 5 == 0:
            try:
                self.p.stdin.write(f"tooltip:Grabando {seg // 60:02d}:{seg % 60:02d} – clic para detener\n")
                self.p.stdin.flush()
            except OSError:
                pass

    def cerrar(self) -> None:
        if self.p and self.p.poll() is None:
            try:
                self.p.stdin.write("quit\n")
                self.p.stdin.flush()
                self.p.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                self.p.kill()
        self.p = None


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Grabador")
        self.resizable(False, False)
        self.proc: subprocess.Popen | None = None
        self.salida: Path | None = None
        self.t0 = 0.0
        self.cfg = g.Config()
        self.barra: MiniBarra | None = None
        self.bandeja: Bandeja | None = None

        self.v_motor = tk.StringVar(value="auto")
        self.v_obj = tk.StringVar(value="pantalla")
        self.v_res = tk.StringVar(value="nativa")
        self.v_fps = tk.StringVar(value="60")
        self.v_codec = tk.StringVar(value="h264")
        self.v_cal = tk.StringVar(value="alta")
        self.v_ajuste = tk.StringVar(value="barras")
        self.v_cont = tk.StringVar(value="mkv")
        self.v_audio = tk.BooleanVar(value=True)
        self.v_mic = tk.BooleanVar(value=False)
        self.v_cursor = tk.BooleanVar(value=True)
        self.v_algrabar = tk.StringVar(value="auto")
        self.v_dir = tk.StringVar(value=str(g.DEFAULT_DIR))
        self.v_estado = tk.StringVar(value="Listo")
        self.v_sel = tk.StringVar(value="")
        self.v_sr = tk.StringVar(value="1920x1080")
        self.v_sr_estado = tk.StringVar(value="")

        self._cargar()
        self._ui()
        self._sr_refrescar()
        self.protocol("WM_DELETE_WINDOW", self._cerrar)

    # ------------------------------------------------------------------ UI
    def _ui(self) -> None:
        pad = {"padx": 6, "pady": 3}
        f = ttk.Frame(self, padding=10)
        f.grid()
        self.f = f

        def fila(parent, r, label, widget):
            ttk.Label(parent, text=label).grid(row=r, column=0, sticky="w", **pad)
            widget.grid(row=r, column=1, columnspan=2, sticky="we", **pad)

        def combo(parent, var, vals, editable=False):
            return ttk.Combobox(parent, textvariable=var, values=vals, width=20,
                                state="normal" if editable else "readonly")

        # --- lo básico
        fila(f, 0, "Qué grabar", combo(f, self.v_obj, ["pantalla", "ventana", "region", "enfocada"]))
        ttk.Button(f, text="Elegir ventana/región…", command=self._seleccionar).grid(
            row=1, column=1, sticky="we", **pad)
        ttk.Label(f, textvariable=self.v_sel, foreground="gray").grid(row=1, column=2, sticky="w")
        fila(f, 2, "Resolución", combo(f, self.v_res, list(g.RESOLUCIONES)))
        fila(f, 3, "FPS", combo(f, self.v_fps, [str(x) for x in g.FPS_OPCIONES], editable=True))
        fila(f, 4, "Calidad", combo(f, self.v_cal, list(g.CALIDADES)))
        cb = ttk.Frame(f)
        ttk.Checkbutton(cb, text="Audio PC", variable=self.v_audio).pack(side="left", padx=3)
        ttk.Checkbutton(cb, text="Micrófono", variable=self.v_mic).pack(side="left", padx=3)
        cb.grid(row=5, column=0, columnspan=3, sticky="w", pady=2)
        fila(f, 6, "Al grabar", combo(f, self.v_algrabar, AL_GRABAR))

        self.btn = ttk.Button(f, text="● Grabar", command=self._toggle)
        self.btn.grid(row=7, column=0, columnspan=3, sticky="we", pady=(8, 4), ipady=4)
        ttk.Label(f, textvariable=self.v_estado, wraplength=360).grid(
            row=8, column=0, columnspan=3, sticky="w")

        # --- resolución real
        sr = ttk.LabelFrame(f, text="Resolución REAL (sin escalado)", padding=8)
        sr.grid(row=9, column=0, columnspan=3, sticky="we", pady=(8, 0))
        ttk.Combobox(sr, textvariable=self.v_sr, width=10, state="readonly",
                     values=["1600x900", "1920x1080", "2560x1440"]).grid(row=0, column=0)
        ttk.Button(sr, text="Activar", command=self._sr_activar).grid(row=0, column=1, padx=3)
        ttk.Button(sr, text="Restaurar", command=self._sr_off).grid(row=0, column=2)
        ttk.Button(sr, text="Abrir Chrome", command=lambda: self._nav("chrome")).grid(
            row=1, column=0, columnspan=2, sticky="we", pady=(6, 0))
        ttk.Button(sr, text="Abrir Firefox", command=lambda: self._nav("firefox")).grid(
            row=1, column=2, sticky="we", pady=(6, 0), padx=(3, 0))
        ttk.Label(sr, textvariable=self.v_sr_estado, foreground="gray", wraplength=340,
                  justify="left").grid(row=2, column=0, columnspan=3, sticky="w", pady=(6, 0))

        # --- avanzado (plegable)
        self.btn_av = ttk.Button(f, text="▸ Avanzado", command=self._toggle_avanzado)
        self.btn_av.grid(row=10, column=0, sticky="w", pady=(8, 0))
        av = self.av = ttk.Frame(f)
        fila(av, 0, "Motor", combo(av, self.v_motor, ["auto", "ffmpeg", "gsr"]))
        fila(av, 1, "Códec", combo(av, self.v_codec, ["h264", "hevc"]))
        fila(av, 2, "Ajuste", combo(av, self.v_ajuste, ["barras", "estirar"]))
        fila(av, 3, "Contenedor", combo(av, self.v_cont, ["mkv", "mp4"]))
        ttk.Checkbutton(av, text="Grabar cursor", variable=self.v_cursor).grid(
            row=4, column=0, columnspan=2, sticky="w", **pad)
        d = ttk.Frame(av)
        ttk.Entry(d, textvariable=self.v_dir, width=24).pack(side="left")
        ttk.Button(d, text="…", width=3, command=self._carpeta).pack(side="left", padx=3)
        fila(av, 5, "Carpeta", d)
        ttk.Button(av, text="Abrir carpeta de videos", command=self._abrir_carpeta).grid(
            row=6, column=0, columnspan=3, sticky="we", **pad)
        self.lbl_info = ttk.Label(av, foreground="gray", wraplength=360, justify="left")
        self.lbl_info.grid(row=7, column=0, columnspan=3, sticky="w", pady=(4, 0))

    def _toggle_avanzado(self) -> None:
        if self.av.winfo_ismapped():
            self.av.grid_remove()
            self.btn_av.config(text="▸ Avanzado")
        else:
            self.av.grid(row=11, column=0, columnspan=3, sticky="we")
            self.btn_av.config(text="▾ Avanzado")

    def _abrir_carpeta(self) -> None:
        d = Path(self.v_dir.get()).expanduser()
        d.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(["xdg-open", str(d)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # ------------------------------------------------------------------ configuración
    def _vars(self) -> dict:
        return {"motor": self.v_motor, "objetivo": self.v_obj, "resolucion": self.v_res,
                "fps": self.v_fps, "codec": self.v_codec, "calidad": self.v_cal,
                "ajuste": self.v_ajuste, "contenedor": self.v_cont, "audio": self.v_audio,
                "mic": self.v_mic, "cursor": self.v_cursor, "carpeta": self.v_dir,
                "al_grabar": self.v_algrabar, "superres": self.v_sr}

    def _cargar(self) -> None:
        try:
            datos = json.loads(CONFIG.read_text())
        except (OSError, ValueError):
            return
        for k, v in self._vars().items():
            if k in datos:
                try:
                    v.set(datos[k])
                except tk.TclError:
                    pass

    def _guardar(self) -> None:
        try:
            CONFIG.parent.mkdir(parents=True, exist_ok=True)
            CONFIG.write_text(json.dumps({k: v.get() for k, v in self._vars().items()}, indent=2))
        except OSError:
            pass

    # ------------------------------------------------------------------ supermuestreo
    def _sr_refrescar(self) -> None:
        self._info_sistema()
        i = g.salida_principal()
        if not i:
            self.v_sr_estado.set("X11/xrandr no disponible.")
            return
        nw, nh = i["nativa"]
        if i["supermuestreo"]:
            self.v_sr_estado.set(f"ACTIVO: escritorio {i['w']}x{i['h']} en panel {nw}x{nh}. "
                                 f"Graba en 'nativa' = {i['w']}x{i['h']} reales.")
        else:
            self.v_sr_estado.set(f"Apagado: escritorio {nw}x{nh}. Activa 1920x1080 para "
                                 "grabar 1080p real; abre el navegador desde aquí para verlo a tamaño normal.")

    def _sr_activar(self) -> None:
        try:
            g.superres(self.v_sr.get())
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Supermuestreo", str(e))
            return
        self.v_res.set("nativa")
        self.after(800, self._sr_confirmar)

    def _sr_confirmar(self) -> None:
        top = tk.Toplevel(self)
        top.title("¿Mantener?")
        top.attributes("-topmost", True)
        restante = [15]
        lbl = ttk.Label(top, padding=15)
        lbl.pack()
        estado = {"ok": False}

        def ok():
            estado["ok"] = True
            top.destroy()
            self._sr_refrescar()

        def cuenta():
            if estado["ok"] or not top.winfo_exists():
                return
            if restante[0] <= 0:
                top.destroy()
                self._sr_off()
                return
            lbl.config(text=f"¿Se ve bien la pantalla?\nSe revierte en {restante[0]} s.")
            restante[0] -= 1
            top.after(1000, cuenta)

        b = ttk.Frame(top, padding=(15, 0, 15, 15))
        b.pack()
        ttk.Button(b, text="Mantener", command=ok).pack(side="left", padx=4)
        ttk.Button(b, text="Revertir", command=lambda: (top.destroy(), self._sr_off())).pack(side="left")
        cuenta()

    def _sr_off(self) -> None:
        try:
            g.superres("off")
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Supermuestreo", str(e))
        self.after(500, self._sr_refrescar)

    def _nav(self, nav: str) -> None:
        msg = g.lanzar_navegador(nav)
        self.v_sr_estado.set(msg)

    def _info_sistema(self) -> None:
        txt = [f"Sesión: {g.tipo_sesion()}"]
        if g.which("xrandr"):
            w, h, _, _, hz = g.pantalla_x11()
            txt.append(f"Escritorio: {w}x{h} @ {hz:.0f} Hz")
        txt.append("Encoder: " + {"nvenc": "NVIDIA NVENC", "vaapi": "Intel/AMD VAAPI",
                                  "cpu": "CPU (x264)"}[g.elegir_encoder("h264")])
        txt.append("gpu-screen-recorder: " + ("sí" if g.which("gpu-screen-recorder") else "no"))
        txt.append("Bandeja: " + ("sí (yad)" if g.which("yad") else "instala yad para usarla"))
        self.lbl_info.config(text="\n".join(txt))

    # ------------------------------------------------------------------ acciones
    def _carpeta(self) -> None:
        d = filedialog.askdirectory(initialdir=self.v_dir.get())
        if d:
            self.v_dir.set(d)

    def _seleccionar(self) -> None:
        obj = self.v_obj.get()
        self.withdraw()
        self.update()
        time.sleep(0.3)
        try:
            if obj == "ventana":
                self.cfg.ventana_id = g.seleccionar_ventana()
                geo = g.geometria_ventana(self.cfg.ventana_id) if self.cfg.ventana_id else None
                self.v_sel.set(f"{self.cfg.ventana_id} {geo[0]}x{geo[1]}" if geo
                               else (self.cfg.ventana_id or "—"))
            elif obj == "region":
                self.cfg.region = g.seleccionar_region()
                r = self.cfg.region
                self.v_sel.set(f"{r[0]}x{r[1]}+{r[2]}+{r[3]}" if r else "instala slop")
            else:
                self.v_sel.set("no aplica")
        finally:
            self.deiconify()

    def _leer_cfg(self) -> g.Config:
        c = self.cfg
        c.motor, c.objetivo = self.v_motor.get(), self.v_obj.get()
        c.resolucion, c.codec = self.v_res.get(), self.v_codec.get()
        c.fps = int(self.v_fps.get())
        c.calidad, c.ajuste, c.contenedor = self.v_cal.get(), self.v_ajuste.get(), self.v_cont.get()
        c.audio_escritorio, c.microfono = self.v_audio.get(), self.v_mic.get()
        c.cursor, c.carpeta = self.v_cursor.get(), self.v_dir.get()
        return c

    def _toggle(self) -> None:
        if self.proc:
            self.v_estado.set("Deteniendo…")
            self.update()
            g.detener()
            return
        cfg = self._leer_cfg()
        wayland_gsr = g.tipo_sesion() == "wayland" and g.resolver_motor(cfg) == "gsr"
        if cfg.objetivo == "ventana" and not cfg.ventana_id and not wayland_gsr:
            self._seleccionar()
        if cfg.objetivo == "region" and not cfg.region:
            self._seleccionar()
        av = g.avisos(cfg)
        if av and not messagebox.askokcancel("Aviso", "\n\n".join(av) + "\n\n¿Grabar de todos modos?"):
            return
        try:
            log = open(Path(g.RUNTIME_DIR) / "grabador.log", "w")
            self.proc, self.salida = g.iniciar(cfg, log=log)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Error", str(e))
            return
        self._guardar()
        self.t0 = time.time()
        self.btn.config(text="■ Detener")
        self._mostrar_indicador(cfg)
        self._tick()

    def _mostrar_indicador(self, cfg: g.Config) -> None:
        modo = self.v_algrabar.get()
        if modo == "auto":
            # pantalla completa: la mini barra saldría en el video -> bandeja
            modo = "bandeja" if cfg.objetivo == "pantalla" and g.which("yad") else "mini barra"
            if cfg.objetivo == "pantalla" and modo == "mini barra":
                modo = "minimizar"
        if modo == "bandeja":
            self.bandeja = Bandeja()
            if not self.bandeja.activa:
                self.bandeja = None
                modo = "mini barra"
                self.v_estado.set("yad no instalado: uso mini barra (sudo pacman -S yad)")
        if modo == "mini barra":
            self.barra = MiniBarra(self)
        if modo == "minimizar":
            self.iconify()
        else:
            self.withdraw()

    def _ocultar_indicador(self) -> None:
        if self.barra:
            self.barra.destroy()
            self.barra = None
        if self.bandeja:
            self.bandeja.cerrar()
            self.bandeja = None

    def _tick(self) -> None:
        if not self.proc:
            return
        rc = self.proc.poll()
        if rc is None:
            s = int(time.time() - self.t0)
            self.v_estado.set(f"● REC {s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d} → {self.salida.name}")
            self.title(f"● REC {s // 60:02d}:{s % 60:02d} – Grabador")
            if self.barra:
                self.barra.actualizar(s)
            if self.bandeja:
                self.bandeja.actualizar(s)
            self.after(1000, self._tick)
            return
        # terminó (botón, atajo `detener`, o error)
        g.PIDFILE.unlink(missing_ok=True)
        self.proc = None
        self._ocultar_indicador()
        self.btn.config(text="● Grabar")
        self.title("Grabador")
        if self.salida and self.salida.exists() and self.salida.stat().st_size > 0:
            mb = self.salida.stat().st_size / 1e6
            self.v_estado.set(f"Guardado: {self.salida} ({mb:.1f} MB)")
            g.notificar(f"Guardado: {self.salida.name}")
        else:
            log = Path(g.RUNTIME_DIR) / "grabador.log"
            tail = log.read_text()[-800:] if log.exists() else ""
            self.v_estado.set(f"Falló la grabación (código {rc}).")
            messagebox.showerror("Error al grabar", tail or f"Código {rc}")
        self.deiconify()

    def _cerrar(self) -> None:
        self._guardar()
        if self.proc and not messagebox.askyesno(
                "Grabando", "Hay una grabación en curso.\n¿Detenerla y salir?\n"
                            "(No = salir y dejarla grabando en segundo plano)"):
            if self.bandeja:
                self.bandeja.p = None   # deja el icono vivo: clic sigue deteniendo
            self.destroy()   # se queda grabando; para con el icono o `grabador detener`
            return
        if self.proc:
            g.detener()
        self._ocultar_indicador()
        self.destroy()


def lanzar_gui() -> int:
    try:
        App().mainloop()
    except tk.TclError as e:
        print(f"No se pudo abrir la GUI: {e}")
        return 1
    return 0
