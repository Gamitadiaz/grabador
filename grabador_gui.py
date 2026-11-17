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
        self.v_res = tk.StringVar(value="nativa")
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
        self.v_sr = tk.StringVar(value="1920x1080")
        self.v_sr_estado = tk.StringVar(value="")

        self._ui()
        self._sr_refrescar()
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

        sr = ttk.LabelFrame(f, text="Resolución REAL (sin escalado)", padding=8)
        sr.grid(row=14, column=0, columnspan=3, sticky="we", pady=(10, 0))
        ttk.Label(sr, text="Dibujar escritorio a").grid(row=0, column=0, sticky="w")
        ttk.Combobox(sr, textvariable=self.v_sr, width=11, state="readonly",
                     values=["1600x900", "1920x1080", "2560x1440"]).grid(row=0, column=1, padx=4)
        ttk.Button(sr, text="Activar", command=self._sr_activar).grid(row=0, column=2, padx=2)
        ttk.Button(sr, text="Restaurar", command=self._sr_off).grid(row=0, column=3, padx=2)
        ttk.Button(sr, text="Abrir Chrome", command=lambda: self._nav("chrome")).grid(
            row=1, column=0, sticky="we", pady=(6, 0))
        ttk.Button(sr, text="Abrir Firefox", command=lambda: self._nav("firefox")).grid(
            row=1, column=1, sticky="we", pady=(6, 0), padx=4)
        ttk.Label(sr, textvariable=self.v_sr_estado, foreground="gray", wraplength=370,
                  justify="left").grid(row=2, column=0, columnspan=4, sticky="w", pady=(6, 0))

    # ------------------------------------------------------------------ supermuestreo
    def _sr_refrescar(self) -> None:
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
        self._info_sistema()

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
