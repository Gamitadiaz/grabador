"""Interfaz gráfica (tkinter) del Grabador."""
from __future__ import annotations

import subprocess
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import grabador as g


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Grabador")
        self.resizable(False, False)
        self.proc: subprocess.Popen | None = None
        self.salida: Path | None = None
        self.t0 = 0.0
        self.cfg = g.Config()

        self.v_motor = tk.StringVar(value="auto")
        self.v_obj = tk.StringVar(value="pantalla")
        self.v_res = tk.StringVar(value="1080p")
        self.v_fps = tk.StringVar(value="60")
        self.v_codec = tk.StringVar(value="h264")
        self.v_cal = tk.StringVar(value="alta")
        self.v_ajuste = tk.StringVar(value="barras")
        self.v_cont = tk.StringVar(value="mkv")
        self.v_audio = tk.BooleanVar(value=True)
        self.v_mic = tk.BooleanVar(value=False)
        self.v_cursor = tk.BooleanVar(value=True)
        self.v_min = tk.BooleanVar(value=True)
        self.v_dir = tk.StringVar(value=str(g.DEFAULT_DIR))
        self.v_estado = tk.StringVar(value="Listo")
        self.v_sel = tk.StringVar(value="")

        self._ui()
        self._info_sistema()
        self.protocol("WM_DELETE_WINDOW", self._cerrar)

    # ------------------------------------------------------------------ UI
    def _ui(self) -> None:
        pad = {"padx": 6, "pady": 3}
        f = ttk.Frame(self, padding=10)
        f.grid()

        def fila(r, label, widget):
            ttk.Label(f, text=label).grid(row=r, column=0, sticky="w", **pad)
            widget.grid(row=r, column=1, columnspan=2, sticky="we", **pad)

        def combo(var, vals):
            return ttk.Combobox(f, textvariable=var, values=vals, state="readonly", width=22)

        fila(0, "Motor", combo(self.v_motor, ["auto", "ffmpeg", "gsr"]))
        fila(1, "Qué grabar", combo(self.v_obj, ["pantalla", "ventana", "region", "enfocada"]))
        ttk.Button(f, text="Elegir ventana/región…", command=self._seleccionar).grid(
            row=2, column=1, sticky="we", **pad)
        ttk.Label(f, textvariable=self.v_sel, foreground="gray").grid(row=2, column=2, sticky="w")
        fila(3, "Resolución", combo(self.v_res, list(g.RESOLUCIONES)))
        fila(4, "FPS", ttk.Combobox(f, textvariable=self.v_fps,
                                    values=[str(x) for x in g.FPS_OPCIONES], width=22))
        fila(5, "Códec", combo(self.v_codec, ["h264", "hevc"]))
        fila(6, "Calidad", combo(self.v_cal, list(g.CALIDADES)))
        fila(7, "Ajuste", combo(self.v_ajuste, ["barras", "estirar"]))
        fila(8, "Contenedor", combo(self.v_cont, ["mkv", "mp4"]))

        cb = ttk.Frame(f)
        for txt, var in (("Audio PC", self.v_audio), ("Micrófono", self.v_mic),
                         ("Cursor", self.v_cursor), ("Minimizar al grabar", self.v_min)):
            ttk.Checkbutton(cb, text=txt, variable=var).pack(side="left", padx=3)
        cb.grid(row=9, column=0, columnspan=3, sticky="w", pady=4)

        d = ttk.Frame(f)
        ttk.Entry(d, textvariable=self.v_dir, width=30).pack(side="left")
        ttk.Button(d, text="…", width=3, command=self._carpeta).pack(side="left", padx=3)
        fila(10, "Carpeta", d)

        self.btn = ttk.Button(f, text="● Grabar", command=self._toggle)
        self.btn.grid(row=11, column=0, columnspan=3, sticky="we", pady=(10, 4))
        ttk.Label(f, textvariable=self.v_estado, wraplength=380).grid(
            row=12, column=0, columnspan=3, sticky="w")
        self.lbl_info = ttk.Label(f, foreground="gray", wraplength=380, justify="left")
        self.lbl_info.grid(row=13, column=0, columnspan=3, sticky="w", pady=(6, 0))

    def _info_sistema(self) -> None:
        txt = [f"Sesión: {g.tipo_sesion()}"]
        if g.which("xrandr"):
            w, h, _, _, hz = g.pantalla_x11()
            txt.append(f"Monitor: {w}x{h} @ {hz:.0f} Hz")
        enc = g.encoders_ffmpeg()
        txt.append("NVENC: " + ("sí" if "h264_nvenc" in enc else "no (usará CPU)"))
        txt.append("gpu-screen-recorder: " + ("sí" if g.which("gpu-screen-recorder") else "no"))
        txt.append("Atajo global: bindea `grabador.py alternar` en tu WM/DE.")
        self.lbl_info.config(text="  ·  ".join(txt[:-1]) + "\n" + txt[-1])

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
        self.t0 = time.time()
        self.btn.config(text="■ Detener")
        if self.v_min.get():
            self.iconify()
        self._tick()

    def _tick(self) -> None:
        if not self.proc:
            return
        rc = self.proc.poll()
        if rc is None:
            s = int(time.time() - self.t0)
            self.v_estado.set(f"● REC {s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d} → {self.salida.name}")
            self.title(f"● REC {s // 60:02d}:{s % 60:02d} – Grabador")
            self.after(500, self._tick)
            return
        # terminó (botón, atajo `detener`, o error)
        g.PIDFILE.unlink(missing_ok=True)
        self.proc = None
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
        if self.proc and not messagebox.askyesno(
                "Grabando", "Hay una grabación en curso.\n¿Detenerla y salir?\n"
                            "(No = salir y dejarla grabando en segundo plano)"):
            self.destroy()   # se queda grabando; para con `grabador.py detener`
            return
        if self.proc:
            g.detener()
        self.destroy()


def lanzar_gui() -> int:
    try:
        App().mainloop()
    except tk.TclError as e:
        print(f"No se pudo abrir la GUI: {e}")
        return 1
    return 0
