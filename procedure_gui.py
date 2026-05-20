#!/usr/bin/env python3
"""
Automation procedure GUI — fullscreen, six steps, simple Incubation / Images settings.

Run on the Raspberry Pi:
    python procedure_gui.py

Press Escape to exit fullscreen.
"""

import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext

from device_config import (
    DEFAULT_INCUBATION_COUNT,
    DEFAULT_INCUBATION_MINUTES,
    DEFAULT_INCUBATION_TEMP_C,
    DEFAULT_PICTURE_TIMES,
    INCUBATION_MIN_MAX,
    INCUBATION_MIN_MIN,
    INCUBATION_MIN_STEP,
    INCUBATION_TEMP_OPTIONS,
    MAX_PETRI_DISHES,
    NUM_PICTURE_SLOTS,
    PICTURE_TIME_PRESETS,
)
from workflow_steps import (
    capture_petri_dishes,
    run_timed_picture_study,
    step_01_all_home,
    step_02_insert_petri_dishes,
    step_03_shift_for_incubation,
    step_04_incubation,
    step_05_post_imaging_cleanup,
    step_05_prepare_imaging,
    step_06_sterilize,
)

try:
    from main import shutdown_all
except ImportError:
    def shutdown_all():
        pass


BG = "#1a1f2e"
PANEL = "#252b3d"
CARD = "#2f3649"
ACCENT = "#5b9bd5"
ACCENT2 = "#7ec8a4"
SELECTED = "#3d6ea8"
TEXT = "#eef2f8"
MUTED = "#9aa5b8"
WARN = "#e8a87c"


class ProcedureGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Automation Imagery")
        self.root.configure(bg=BG)

        self._busy = False
        self._fullscreen = True
        self._temp_display = tk.StringVar(value="--.- °C")
        self._target_display = tk.StringVar(value=f"Target {DEFAULT_INCUBATION_TEMP_C:.0f} °C")
        self._time_display = tk.StringVar(value="Ready")
        self._status_display = tk.StringVar(value="Idle")

        self._petri_count = tk.IntVar(value=10)
        self._incub_minutes = tk.DoubleVar(value=DEFAULT_INCUBATION_MINUTES)
        self._incub_count = tk.IntVar(value=DEFAULT_INCUBATION_COUNT)
        self._selected_temp = tk.DoubleVar(value=DEFAULT_INCUBATION_TEMP_C)
        self._picture_times = [tk.IntVar(value=DEFAULT_PICTURE_TIMES[i]) for i in range(NUM_PICTURE_SLOTS)]

        self._temp_buttons = []
        self._canvas = None
        self._gauge_cx = 200
        self._gauge_cy = 120
        self._gauge_r = 90

        self._build_ui()
        self._go_fullscreen()
        self.root.bind("<Escape>", self._on_escape)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _go_fullscreen(self):
        self._fullscreen = True
        try:
            self.root.attributes("-fullscreen", True)
        except tk.TclError:
            self.root.geometry(f"{self.root.winfo_screenwidth()}x{self.root.winfo_screenheight()}+0+0")
        self.root.update_idletasks()

    def _on_escape(self, _event=None):
        if self._fullscreen:
            self._fullscreen = False
            self.root.attributes("-fullscreen", False)
        else:
            self._go_fullscreen()

    def _section(self, parent, title):
        frame = tk.LabelFrame(
            parent,
            text=f"  {title}  ",
            bg=PANEL,
            fg=ACCENT,
            font=("Segoe UI", 11, "bold"),
            labelanchor="n",
            padx=10,
            pady=8,
        )
        frame.pack(fill=tk.X, pady=(0, 12))
        inner = tk.Frame(frame, bg=PANEL)
        inner.pack(fill=tk.X)
        return inner

    def _build_ui(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        outer = tk.Frame(self.root, bg=BG, padx=14, pady=12)
        outer.grid(row=0, column=0, sticky="nsew")
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(0, weight=1)

        # --- Left: steps ---
        left = tk.Frame(outer, bg=PANEL, padx=12, pady=12)
        left.grid(row=0, column=0, sticky="ns")
        tk.Label(left, text="Steps", bg=PANEL, fg=TEXT, font=("Segoe UI", 13, "bold")).pack(
            anchor="w", pady=(0, 10)
        )

        steps = [
            ("All Home", step_01_all_home),
            ("Insert Petri Dishes", step_02_insert_petri_dishes),
            ("Shift for Incubation", step_03_shift_for_incubation),
            ("Start Incubation", self._run_incubation_only),
            ("Take Pictures", self._run_pictures_only),
            ("Sterilize", step_06_sterilize),
        ]
        for label, fn in steps:
            self._mk_btn(left, label, fn, width=22).pack(fill=tk.X, pady=5)

        self._mk_btn(left, "Timed Study", self._run_timed_study, ACCENT2, width=22).pack(
            fill=tk.X, pady=(16, 0)
        )

        # --- Center ---
        center = tk.Frame(outer, bg=BG, padx=16)
        center.grid(row=0, column=1, sticky="nsew")
        center.columnconfigure(0, weight=1)
        center.rowconfigure(2, weight=1)

        tk.Label(
            center, textvariable=self._status_display, bg=BG, fg=ACCENT, font=("Segoe UI", 12)
        ).grid(row=0, column=0, sticky="w")

        viz = tk.Frame(center, bg=PANEL, padx=8, pady=8)
        viz.grid(row=1, column=0, sticky="ew", pady=8)
        viz.columnconfigure(0, weight=1)

        self._canvas = tk.Canvas(viz, height=240, bg=PANEL, highlightthickness=0)
        self._canvas.grid(row=0, column=0, sticky="ew")
        self._canvas.bind("<Configure>", self._on_canvas_resize)

        info = tk.Frame(viz, bg=PANEL)
        info.grid(row=1, column=0, pady=8)
        tk.Label(
            info, textvariable=self._temp_display, bg=PANEL, fg=TEXT, font=("Segoe UI", 32, "bold")
        ).pack()
        tk.Label(
            info, textvariable=self._target_display, bg=PANEL, fg=MUTED, font=("Segoe UI", 11)
        ).pack()
        tk.Label(
            info, textvariable=self._time_display, bg=PANEL, fg=ACCENT2, font=("Segoe UI", 15)
        ).pack(pady=(4, 0))

        tk.Label(center, text="Log", bg=BG, fg=MUTED, font=("Segoe UI", 9)).grid(
            row=2, column=0, sticky="nw"
        )
        self._log = scrolledtext.ScrolledText(
            center,
            bg="#12161f",
            fg=TEXT,
            insertbackground=TEXT,
            font=("Consolas", 10),
            relief=tk.FLAT,
        )
        self._log.grid(row=3, column=0, sticky="nsew", pady=(4, 0))
        center.rowconfigure(3, weight=1)

        # --- Right: settings (2 sections) ---
        right = tk.Frame(outer, bg=PANEL, padx=14, pady=12, width=280)
        right.grid(row=0, column=2, sticky="ns")
        tk.Label(right, text="Settings", bg=PANEL, fg=TEXT, font=("Segoe UI", 13, "bold")).pack(
            anchor="w", pady=(0, 12)
        )

        # Incubation
        inc = self._section(right, "Incubation")
        tk.Label(inc, text="Temperature", bg=PANEL, fg=MUTED, font=("Segoe UI", 9)).pack(
            anchor="w"
        )
        temp_row = tk.Frame(inc, bg=PANEL)
        temp_row.pack(fill=tk.X, pady=6)
        for t in INCUBATION_TEMP_OPTIONS:
            btn = tk.Button(
                temp_row,
                text=f"{t}°C",
                command=lambda temp=t: self._select_temp(temp),
                bg=CARD,
                fg=TEXT,
                activebackground=SELECTED,
                relief=tk.FLAT,
                padx=10,
                pady=10,
                font=("Segoe UI", 11, "bold"),
                cursor="hand2",
            )
            btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
            self._temp_buttons.append((t, btn))
        self._highlight_temp(DEFAULT_INCUBATION_TEMP_C)

        self._stepper_row(inc, "Duration (min)", self._incub_minutes, self._dec_minutes, self._inc_minutes, fmt=".1f")
        self._stepper_row(
            inc,
            "Cycles",
            self._incub_count,
            lambda: self._incub_count.set(max(1, int(self._incub_count.get()) - 1)),
            lambda: self._incub_count.set(min(20, int(self._incub_count.get()) + 1)),
            fmt="d",
        )

        # Images
        img = self._section(right, "Images")
        self._stepper_row(
            img,
            "Petri dishes",
            self._petri_count,
            lambda: self._petri_count.set(max(1, int(self._petri_count.get()) - 1)),
            lambda: self._petri_count.set(min(MAX_PETRI_DISHES, int(self._petri_count.get()) + 1)),
            fmt="d",
        )
        tk.Label(
            img,
            text="Minutes of incubation before each capture",
            bg=PANEL,
            fg=MUTED,
            font=("Segoe UI", 8),
            wraplength=240,
            justify="left",
        ).pack(anchor="w", pady=(4, 6))

        for i in range(NUM_PICTURE_SLOTS):
            self._picture_time_row(img, i + 1, self._picture_times[i])

    def _on_canvas_resize(self, event):
        self._gauge_cx = event.width // 2
        self._gauge_cy = event.height // 2
        self._gauge_r = min(event.width, event.height) // 2 - 16
        if not self._busy:
            self._draw_idle_gauge()

    def _select_temp(self, temp):
        self._selected_temp.set(float(temp))
        self._highlight_temp(temp)
        self._target_display.set(f"Target {temp:.0f} °C")

    def _highlight_temp(self, active):
        for t, btn in self._temp_buttons:
            btn.configure(bg=SELECTED if t == active else CARD)

    def _stepper_row(self, parent, label, var, on_dec, on_inc, fmt="d"):
        tk.Label(parent, text=label, bg=PANEL, fg=MUTED, font=("Segoe UI", 9)).pack(
            anchor="w", pady=(8, 2)
        )
        row = tk.Frame(parent, bg=PANEL)
        row.pack(fill=tk.X)
        tk.Button(
            row, text="−", width=4, command=on_dec, bg=CARD, fg=TEXT, relief=tk.FLAT, font=("Segoe UI", 14, "bold")
        ).pack(side=tk.LEFT)
        tk.Label(row, textvariable=var, bg=PANEL, fg=TEXT, width=6, font=("Segoe UI", 16, "bold")).pack(
            side=tk.LEFT, expand=True
        )
        tk.Button(
            row, text="+", width=4, command=on_inc, bg=CARD, fg=TEXT, relief=tk.FLAT, font=("Segoe UI", 14, "bold")
        ).pack(side=tk.LEFT)

    def _picture_time_row(self, parent, index, var):
        tk.Label(parent, text=f"Picture {index}", bg=PANEL, fg=TEXT, font=("Segoe UI", 9)).pack(
            anchor="w", pady=(6, 0)
        )
        row = tk.Frame(parent, bg=PANEL)
        row.pack(fill=tk.X)

        def dec():
            self._bump_picture_time(var, -1)

        def inc():
            self._bump_picture_time(var, 1)

        tk.Button(row, text="−", width=4, command=dec, bg=CARD, fg=TEXT, relief=tk.FLAT).pack(side=tk.LEFT)
        tk.Label(row, textvariable=var, bg=PANEL, fg=ACCENT2, font=("Segoe UI", 15, "bold")).pack(
            side=tk.LEFT, expand=True
        )
        tk.Label(row, text="min", bg=PANEL, fg=MUTED, font=("Segoe UI", 9)).pack(side=tk.LEFT)
        tk.Button(row, text="+", width=4, command=inc, bg=CARD, fg=TEXT, relief=tk.FLAT).pack(side=tk.LEFT)

    def _bump_picture_time(self, var, direction):
        presets = list(PICTURE_TIME_PRESETS)
        cur = int(var.get())
        try:
            idx = presets.index(cur)
        except ValueError:
            idx = min(range(len(presets)), key=lambda i: abs(presets[i] - cur))
        idx = max(0, min(len(presets) - 1, idx + direction))
        var.set(presets[idx])

    def _dec_minutes(self):
        v = max(INCUBATION_MIN_MIN, float(self._incub_minutes.get()) - INCUBATION_MIN_STEP)
        self._incub_minutes.set(round(v, 1))

    def _inc_minutes(self):
        v = min(INCUBATION_MIN_MAX, float(self._incub_minutes.get()) + INCUBATION_MIN_STEP)
        self._incub_minutes.set(round(v, 1))

    def _mk_btn(self, parent, text, command, color=ACCENT, width=18):
        return tk.Button(
            parent,
            text=text,
            width=width,
            command=lambda: self._run_action(text, command),
            bg=color,
            fg="#0d1520",
            activebackground="#8ab4e8",
            relief=tk.FLAT,
            padx=6,
            pady=12,
            font=("Segoe UI", 11, "bold"),
            cursor="hand2",
        )

    def _log_msg(self, msg):
        self._log.insert(tk.END, msg + "\n")
        self._log.see(tk.END)

    def _run_action(self, title, fn):
        if self._busy:
            return

        def worker():
            self._set_busy(True, title)
            try:
                if fn is self._run_incubation_only:
                    self._do_incubation()
                elif fn is self._run_pictures_only:
                    self._do_pictures()
                elif fn is self._run_timed_study:
                    self._do_timed_study()
                else:
                    fn()
                    self._log_msg(f"Done: {title}")
            except Exception as exc:
                self._log_msg(f"ERROR: {exc}")
                self.root.after(0, lambda: messagebox.showerror("Error", str(exc)))
            finally:
                self._set_busy(False, "Idle")
                self.root.after(0, self._draw_idle_gauge)

        threading.Thread(target=worker, daemon=True).start()

    def _set_busy(self, busy, status):
        self._busy = busy
        self.root.after(0, lambda: self._status_display.set(status))

    def _incubation_tick(self, elapsed, remaining, temp_c, target_c):
        def ui():
            self._temp_display.set(f"{temp_c:.1f} °C")
            self._target_display.set(f"Target {target_c:.1f} °C")
            mins, secs = divmod(int(max(0, remaining)), 60)
            self._time_display.set(f"Remaining {mins:02d}:{secs:02d}")
            self._draw_gauge(temp_c, target_c, remaining, elapsed)

        self.root.after(0, ui)

    def _do_incubation(self):
        t = float(self._selected_temp.get())
        m = float(self._incub_minutes.get())
        n = int(self._incub_count.get())
        self._log_msg(f"Incubation: {n}× {t}°C for {m} min")
        step_04_incubation(target_c=t, minutes=m, count=n, on_tick=self._incubation_tick)

    def _do_pictures(self):
        n = int(self._petri_count.get())
        self._log_msg(f"Capture {n} petri dish(es)")
        step_05_prepare_imaging()
        exp = capture_petri_dishes(n)
        step_05_post_imaging_cleanup()
        self._log_msg(f"Saved: {exp}")

    def _run_incubation_only(self):
        pass

    def _run_pictures_only(self):
        pass

    def _run_timed_study(self):
        pass

    def _get_picture_intervals(self):
        return [int(v.get()) for v in self._picture_times]

    def _do_timed_study(self):
        n_petri = int(self._petri_count.get())
        intervals = self._get_picture_intervals()
        t = float(self._selected_temp.get())
        self._log_msg(f"Timed study: petri={n_petri}, times={intervals} min, temp={t}°C")

        def on_log(msg):
            self.root.after(0, lambda m=msg: self._log_msg(m))

        exp = run_timed_picture_study(
            num_petri_dishes=n_petri,
            num_rounds=NUM_PICTURE_SLOTS,
            interval_minutes=intervals,
            target_c=t,
            on_tick=self._incubation_tick,
            on_log=on_log,
        )
        self._log_msg(f"Experiment: {exp}")

    def _draw_idle_gauge(self):
        if self._canvas is None:
            return
        c = self._canvas
        c.delete("all")
        cx, cy, r = self._gauge_cx, self._gauge_cy, self._gauge_r
        c.create_oval(cx - r, cy - r, cx + r, cy + r, outline="#3d465c", width=14)
        c.create_text(cx, cy, text="Ready", fill=MUTED, font=("Segoe UI", 16))

    def _draw_gauge(self, temp_c, target_c, remaining_s, elapsed_s):
        if self._canvas is None:
            return
        c = self._canvas
        c.delete("all")
        cx, cy, r = self._gauge_cx, self._gauge_cy, self._gauge_r

        total = max(1.0, elapsed_s + remaining_s)
        frac = min(1.0, elapsed_s / total)
        c.create_oval(cx - r, cy - r, cx + r, cy + r, outline="#3d465c", width=12)
        if frac > 0:
            c.create_arc(
                cx - r, cy - r, cx + r, cy + r,
                start=90, extent=-360 * frac,
                outline=ACCENT2, width=12, style=tk.ARC,
            )

        tfrac = min(1.0, max(0.0, temp_c / max(50.0, target_c + 5)))
        bw = max(120, int(self._canvas.winfo_width() * 0.75))
        bx0 = cx - bw // 2
        bx1 = bx0 + bw
        by = cy + r - 10
        c.create_rectangle(bx0, by, bx1, by + 16, fill="#3d465c", outline="")
        c.create_rectangle(bx0, by, bx0 + int(bw * tfrac), by + 16, fill=WARN, outline="")
        c.create_text(cx, cy - r + 24, text="Incubating", fill=ACCENT, font=("Segoe UI", 12, "bold"))

    def _on_close(self):
        if self._busy:
            if not messagebox.askyesno("Busy", "A step is running. Quit anyway?"):
                return
        try:
            shutdown_all()
        except Exception:
            pass
        self.root.destroy()


def main():
    root = tk.Tk()
    ProcedureGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
