"""Tkinter control panel for the realtime voice changer."""

import json
import os
import tkinter as tk
from tkinter import ttk, messagebox

from .engine import Engine
from .presets import PRESETS, PARAMS, CHOICES, defaults
from . import virtualmic as vmic

CONFIG = os.path.expanduser("~/.config/voicechanger.json")

# slider groups -> (label, param key, unit)
TABS = {
    "Голос": [
        ("Питч (полутона)", "pitch", "st"),
        ("Форманты (тембр)", "formant", "x"),
        ("Вход", "in_gain_db", "dB"),
        ("Гейт (шумодав)", "gate_db", "dB"),
    ],
    "Тембр": [
        ("Обрез низов", "hp_hz", "Hz"),
        ("Обрез верхов", "lp_hz", "Hz"),
        ("Частота пика", "peak_hz", "Hz"),
        ("Усиление пика", "peak_db", "dB"),
    ],
    "Драйв": [
        ("Перегруз", "dist_drive", "x"),
        ("Перегруз микс", "dist_mix", ""),
        ("Биты", "crush_bits", "bit"),
        ("Даунсэмпл", "crush_ds", "x"),
        ("Крашер микс", "crush_mix", ""),
        ("Кольцевая мод. Гц", "ring_freq", "Hz"),
        ("Кольцевая мод. микс", "ring_mix", ""),
        ("Ва-ва", "wah_mix", ""),
    ],
    "Модуляция": [
        ("Скорость мод.", "mod_rate", "Hz"),
        ("Глубина мод.", "mod_depth", "ms"),
        ("Микс мод.", "mod_mix", ""),
        ("Фейзер скорость", "phaser_rate", "Hz"),
        ("Фейзер микс", "phaser_mix", ""),
        ("Тремоло скорость", "trem_rate", "Hz"),
        ("Тремоло глубина", "trem_depth", ""),
    ],
    "Простр.": [
        ("Эхо время", "echo_time", "ms"),
        ("Эхо повторы", "echo_fb", ""),
        ("Эхо микс", "echo_mix", ""),
        ("Реверб размер", "rev_room", ""),
        ("Реверб демпфер", "rev_damp", ""),
        ("Реверб микс", "rev_mix", ""),
        ("Выход", "out_gain_db", "dB"),
    ],
}


class App:
    def __init__(self, root):
        self.root = root
        self.engine = Engine()
        self.sliders = {}
        self.toggles = {}
        self.choice_vars = {}
        self.updating = False
        self.route_before = None
        self.user_presets = {}

        root.title("Voice Changer")
        root.geometry("980x680")
        root.minsize(880, 600)

        self._build_top()
        self._build_body()
        self._build_status()
        self._load_config()
        self._bind_keys()
        self.select_preset("Clean (bypass)")
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self._tick()

    # ---------------- layout ------------------------------------------------
    def _build_top(self):
        top = ttk.Frame(self.root, padding=8)
        top.pack(fill="x")

        ins, outs = Engine.devices()
        self.in_map = {lbl: idx for idx, lbl in ins}
        self.out_map = {lbl: idx for idx, lbl in outs}

        ttk.Label(top, text="Микрофон:").grid(row=0, column=0, sticky="w")
        self.in_var = tk.StringVar()
        self.in_cb = ttk.Combobox(top, textvariable=self.in_var, width=42,
                                  values=[l for _, l in ins], state="readonly")
        self.in_cb.grid(row=0, column=1, padx=4, sticky="we")

        ttk.Label(top, text="Выход:").grid(row=0, column=2, sticky="w", padx=(10, 0))
        self.out_var = tk.StringVar()
        self.out_cb = ttk.Combobox(top, textvariable=self.out_var, width=42,
                                   values=[l for _, l in outs], state="readonly")
        self.out_cb.grid(row=0, column=3, padx=4, sticky="we")

        ttk.Label(top, text="Буфер:").grid(row=0, column=4, sticky="w", padx=(10, 0))
        self.block_var = tk.StringVar(value="256")
        ttk.Combobox(top, textvariable=self.block_var, width=6, state="readonly",
                     values=["64", "128", "256", "512", "1024"]).grid(row=0, column=5)

        self.start_btn = ttk.Button(top, text="▶  Старт", command=self.toggle_run)
        self.start_btn.grid(row=0, column=6, padx=(10, 0))

        # defaults: prefer a real mic and the pipewire/pulse output
        for _, l in ins:
            if "fifine" in l.lower() or "mic" in l.lower():
                self.in_var.set(l)
                break
        else:
            if ins:
                self.in_var.set(ins[0][1])
        for _, l in outs:
            if l.endswith("pipewire") or l.endswith("pulse") or "default" in l:
                self.out_var.set(l)
                break
        else:
            if outs:
                self.out_var.set(outs[0][1])

        top.columnconfigure(1, weight=1)
        top.columnconfigure(3, weight=1)

    def _build_body(self):
        body = ttk.Frame(self.root, padding=(8, 0))
        body.pack(fill="both", expand=True)

        # ---- presets ----
        left = ttk.LabelFrame(body, text="Пресеты", padding=6)
        left.pack(side="left", fill="y")
        self.search_var = tk.StringVar()
        se = ttk.Entry(left, textvariable=self.search_var, width=26)
        se.pack(fill="x")
        se.insert(0, "")
        self.search_var.trace_add("write", lambda *_: self.refresh_presets())

        wrap = ttk.Frame(left)
        wrap.pack(fill="both", expand=True, pady=4)
        self.plist = tk.Listbox(wrap, width=26, height=24, activestyle="dotbox",
                                exportselection=False)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.plist.yview)
        self.plist.configure(yscrollcommand=sb.set)
        self.plist.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.plist.bind("<<ListboxSelect>>", self.on_preset_click)

        btns = ttk.Frame(left)
        btns.pack(fill="x")
        ttk.Button(btns, text="Сохранить свой", command=self.save_user_preset).pack(
            side="left", fill="x", expand=True)
        ttk.Button(btns, text="Удалить", command=self.delete_user_preset).pack(
            side="left", fill="x", expand=True)
        self.refresh_presets()

        # ---- parameters ----
        right = ttk.Frame(body)
        right.pack(side="left", fill="both", expand=True, padx=(8, 0))

        sw = ttk.LabelFrame(right, text="Переключатели", padding=6)
        sw.pack(fill="x")
        for i, (key, label) in enumerate([
                ("robot", "Робот"), ("whisper", "Шёпот"),
                ("autotune", "Автотюн"), ("comp", "Компрессор"),
                ("denoise", "Шумоподавление")]):
            var = tk.BooleanVar()
            self.toggles[key] = var
            ttk.Checkbutton(sw, text=label, variable=var,
                            command=lambda k=key, v=var: self.on_toggle(k, v)
                            ).grid(row=0, column=i, padx=6, sticky="w")
        col = 0
        row2 = ttk.Frame(sw)
        row2.grid(row=1, column=0, columnspan=6, sticky="w", pady=(6, 0))
        for key, label in [("mod_mode", "Модуляция"), ("dist_kind", "Тип перегруза"),
                           ("scale", "Гамма")]:
            ttk.Label(row2, text=label + ":").grid(row=0, column=col, padx=(0, 3))
            var = tk.StringVar()
            self.choice_vars[key] = var
            cb = ttk.Combobox(row2, textvariable=var, values=CHOICES[key],
                              width=11, state="readonly")
            cb.grid(row=0, column=col + 1, padx=(0, 12))
            cb.bind("<<ComboboxSelected>>",
                    lambda e, k=key, v=var: self.engine.chain.set(k, v.get()))
            col += 2

        nb = ttk.Notebook(right)
        nb.pack(fill="both", expand=True, pady=6)
        for tab, items in TABS.items():
            frame = ttk.Frame(nb, padding=8)
            nb.add(frame, text=tab)
            for r, (label, key, unit) in enumerate(items):
                self._add_slider(frame, r, label, key, unit)
            frame.columnconfigure(1, weight=1)

    def _add_slider(self, parent, row, label, key, unit):
        default, lo, hi, kind = PARAMS[key]
        ttk.Label(parent, text=label, width=20, anchor="w").grid(
            row=row, column=0, sticky="w", pady=3)
        var = tk.DoubleVar(value=float(default))
        val_lbl = ttk.Label(parent, width=10, anchor="e")

        def on_move(v, k=key, vl=val_lbl, u=unit, kd=kind):
            value = float(v)
            if kd == "i":
                value = round(value)
            vl.configure(text=f"{value:.2f} {u}" if kd == "f" else f"{int(value)} {u}")
            if not self.updating:
                self.engine.chain.set(k, value if kd == "f" else int(value))

        sc = ttk.Scale(parent, from_=lo, to=hi, variable=var,
                       orient="horizontal", command=on_move)
        sc.grid(row=row, column=1, sticky="we", padx=6)
        val_lbl.grid(row=row, column=2, sticky="e")
        # double-click resets to the preset default
        sc.bind("<Double-Button-1>", lambda e, k=key, v=var: self.reset_param(k, v))
        self.sliders[key] = (var, on_move)

    def _build_status(self):
        bar = ttk.Frame(self.root, padding=8)
        bar.pack(fill="x")

        self.bypass_var = tk.BooleanVar()
        self.mute_var = tk.BooleanVar()
        ttk.Checkbutton(bar, text="Байпас (пробел)", variable=self.bypass_var,
                        command=lambda: setattr(self.engine.chain, "bypass",
                                                self.bypass_var.get())).pack(side="left")
        ttk.Checkbutton(bar, text="Мьют", variable=self.mute_var,
                        command=lambda: setattr(self.engine.chain, "muted",
                                                self.mute_var.get())).pack(side="left", padx=8)

        self.vmic_btn = ttk.Button(bar, text="Создать вирт. микрофон",
                                   command=self.toggle_vmic)
        self.vmic_btn.pack(side="left", padx=8)
        self.monitor_var = tk.BooleanVar()
        ttk.Checkbutton(bar, text="Слышать себя", variable=self.monitor_var,
                        command=self.toggle_monitor).pack(side="left")

        ttk.Label(bar, text="вход").pack(side="left", padx=(16, 2))
        self.in_meter = ttk.Progressbar(bar, length=90, maximum=100)
        self.in_meter.pack(side="left")
        ttk.Label(bar, text="выход").pack(side="left", padx=(8, 2))
        self.out_meter = ttk.Progressbar(bar, length=90, maximum=100)
        self.out_meter.pack(side="left")

        self.status = ttk.Label(self.root, text="Остановлено", anchor="w",
                                padding=(10, 2), relief="sunken")
        self.status.pack(fill="x", side="bottom")

    def _bind_keys(self):
        self.root.bind("<space>", lambda e: self.kb_bypass())
        self.root.bind("<Down>", lambda e: self.step_preset(1))
        self.root.bind("<Up>", lambda e: self.step_preset(-1))
        self.root.bind("<Control-m>", lambda e: self.kb_mute())

    # ---------------- preset handling ---------------------------------------
    def all_presets(self):
        d = dict(PRESETS)
        d.update(self.user_presets)
        return d

    def refresh_presets(self):
        q = self.search_var.get().strip().lower()
        self.plist.delete(0, "end")
        self.visible = [n for n in self.all_presets() if q in n.lower()]
        for n in self.visible:
            self.plist.insert("end", ("★ " if n in self.user_presets else "") + n)

    def on_preset_click(self, _evt=None):
        sel = self.plist.curselection()
        if sel:
            self.select_preset(self.visible[sel[0]])

    def step_preset(self, delta):
        if not self.visible:
            return
        cur = self.plist.curselection()
        i = (cur[0] if cur else 0) + delta
        i = max(0, min(len(self.visible) - 1, i))
        self.plist.selection_clear(0, "end")
        self.plist.selection_set(i)
        self.plist.see(i)
        self.select_preset(self.visible[i])

    def select_preset(self, name):
        params = self.all_presets().get(name)
        if params is None:
            return
        self.current_preset = name
        self.engine.chain.load(params)
        self.sync_widgets()
        if name not in [self.plist.get(i).lstrip("★ ") for i in
                        (self.plist.curselection() or [])]:
            try:
                i = self.visible.index(name)
                self.plist.selection_clear(0, "end")
                self.plist.selection_set(i)
                self.plist.see(i)
            except ValueError:
                pass

    def sync_widgets(self):
        """Push the chain's parameters into every widget without re-triggering."""
        self.updating = True
        p = self.engine.chain.snapshot()
        for key, (var, on_move) in self.sliders.items():
            var.set(float(p[key]))
            on_move(float(p[key]))
        for key, var in self.toggles.items():
            var.set(bool(p[key]))
        for key, var in self.choice_vars.items():
            var.set(str(p[key]))
        self.updating = False

    def reset_param(self, key, var):
        d = PARAMS[key][0]
        var.set(float(d))
        self.sliders[key][1](float(d))

    def on_toggle(self, key, var):
        self.engine.chain.set(key, bool(var.get()))

    def save_user_preset(self):
        from tkinter.simpledialog import askstring
        name = askstring("Сохранить пресет", "Название:", parent=self.root)
        if not name:
            return
        base = defaults()
        cur = self.engine.chain.snapshot()
        self.user_presets[name] = {k: v for k, v in cur.items() if v != base[k]}
        self.refresh_presets()
        self._save_config()
        self.set_status(f"Пресет «{name}» сохранён")

    def delete_user_preset(self):
        sel = self.plist.curselection()
        if not sel:
            return
        name = self.visible[sel[0]]
        if name not in self.user_presets:
            messagebox.showinfo("Voice Changer", "Встроенные пресеты удалить нельзя")
            return
        del self.user_presets[name]
        self.refresh_presets()
        self._save_config()

    # ---------------- engine control ----------------------------------------
    def toggle_run(self):
        if self.engine.running:
            self.engine.stop()
            self.start_btn.configure(text="▶  Старт")
            self.set_status("Остановлено")
        else:
            try:
                self.route_before = vmic.input_indices() if vmic.available() else None
                self.engine.blocksize = int(self.block_var.get())
                self.engine.start(self.in_map.get(self.in_var.get()),
                                  self.out_map.get(self.out_var.get()))
            except Exception as e:
                messagebox.showerror("Не удалось запустить звук", str(e))
                return
            self.start_btn.configure(text="■  Стоп")
            self.set_status("Работает")
            if vmic.available() and vmic.exists():
                self.root.after(600, self.route_to_vmic)

    def route_to_vmic(self):
        try:
            if vmic.route_output(before=self.route_before):
                self.set_status("Работает → виртуальный микрофон «VoiceChanger»")
        except Exception as e:
            self.set_status(f"Маршрутизация не удалась: {e}")

    def toggle_vmic(self):
        if not vmic.available():
            messagebox.showerror("Voice Changer", "pactl не найден (нужен PipeWire/PulseAudio)")
            return
        try:
            if vmic.exists():
                vmic.destroy()
                self.monitor_var.set(False)
                self.vmic_btn.configure(text="Создать вирт. микрофон")
                self.set_status("Виртуальный микрофон удалён")
            else:
                vmic.create()
                self.vmic_btn.configure(text="Удалить вирт. микрофон")
                self.set_status("Готово: выбери микрофон «VoiceChanger» в Discord/OBS")
                if self.engine.running:
                    self.root.after(400, self.route_to_vmic)
        except Exception as e:
            messagebox.showerror("Voice Changer", str(e))

    def toggle_monitor(self):
        try:
            if self.monitor_var.get():
                if not vmic.exists():
                    vmic.create()
                    self.vmic_btn.configure(text="Удалить вирт. микрофон")
                vmic.monitor_on()
                self.set_status("Слышишь себя через колонки/наушники")
            else:
                vmic.monitor_off()
        except Exception as e:
            self.monitor_var.set(False)
            messagebox.showerror("Voice Changer", str(e))

    def kb_bypass(self):
        self.bypass_var.set(not self.bypass_var.get())
        self.engine.chain.bypass = self.bypass_var.get()

    def kb_mute(self):
        self.mute_var.set(not self.mute_var.get())
        self.engine.chain.muted = self.mute_var.get()

    # ---------------- housekeeping ------------------------------------------
    def set_status(self, text):
        self.status.configure(text=text)

    def _tick(self):
        ch = self.engine.chain
        self.in_meter["value"] = min(100, ch.in_level * 300)
        self.out_meter["value"] = min(100, ch.out_level * 300)
        if self.engine.running:
            msg = (f"Работает · задержка ~{self.engine.latency_ms():.0f} мс · "
                   f"CPU {self.engine.cpu:.0f}% · сбои {self.engine.xruns}")
            if vmic.exists():
                msg += " · вирт. микрофон активен"
            if self.engine.error:
                msg += f" · ОШИБКА: {self.engine.error}"
            self.set_status(msg)
        self.root.after(80, self._tick)

    def _load_config(self):
        try:
            with open(CONFIG) as f:
                cfg = json.load(f)
            self.user_presets = cfg.get("user_presets", {})
            if cfg.get("input") in self.in_map:
                self.in_var.set(cfg["input"])
            if cfg.get("output") in self.out_map:
                self.out_var.set(cfg["output"])
            if cfg.get("blocksize"):
                self.block_var.set(str(cfg["blocksize"]))
            self.refresh_presets()
        except Exception:
            pass
        if vmic.available() and vmic.exists():
            self.vmic_btn.configure(text="Удалить вирт. микрофон")

    def _save_config(self):
        try:
            os.makedirs(os.path.dirname(CONFIG), exist_ok=True)
            with open(CONFIG, "w") as f:
                json.dump({"user_presets": self.user_presets,
                           "input": self.in_var.get(),
                           "output": self.out_var.get(),
                           "blocksize": int(self.block_var.get())}, f, indent=2)
        except Exception:
            pass

    def on_close(self):
        self._save_config()
        self.engine.stop()
        try:
            vmic.monitor_off()
        except Exception:
            pass
        self.root.destroy()


def main():
    root = tk.Tk()
    try:
        ttk.Style().theme_use("clam")
    except Exception:
        pass
    App(root)
    root.mainloop()
