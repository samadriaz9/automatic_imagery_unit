#!/usr/bin/env python3
"""
Automation procedure GUI — six manual steps plus incubation and timed imaging.

Run on the Raspberry Pi:
    python procedure_gui.py
"""

import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

from device_config import (
    DEFAULT_INCUBATION_COUNT,
    DEFAULT_INCUBATION_MINUTES,
    DEFAULT_INCUBATION_TEMP_C,
    DEFAULT_PICTURE_INTERVAL_MIN,
    DEFAULT_PICTURE_ROUNDS,
    MAX_PETRI_DISHES,
    MAX_PICTURE_ROUNDS,
    PICTURE_INTERVAL_OPTIONS,
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


BG = "#1e2430"
PANEL = "#2a3142"
ACCENT = "#5b9bd5"
ACCENT2 = "#7ec8a4"
TEXT = "#e8ecf4"
MUTED = "#9aa5b8"
WARN = "#e8a87c"


class ProcedureGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Automation Imagery — Procedure")
        self.root.configure(bg=BG)
        self.root.minsize(960, 640)

        self._busy = False
        self._stop_incubation_ui = False
        self._temp_display = tk.StringVar(value="--.- °C")
        self._target_display = tk.StringVar(value=f"Target {DEFAULT_INCUBATION_TEMP_C:.0f} °C")
        self._time_display = tk.StringVar(value="Ready")
        self._status_display = tk.StringVar(value="Idle")
        self._petri_count = tk.IntVar(value=10)
        self._incub_count = tk.IntVar(value=DEFAULT_INCUBATION_COUNT)
        self._incub_temp = tk.DoubleVar(value=DEFAULT_INCUBATION_TEMP_C)
        self._incub_minutes = tk.DoubleVar(value=DEFAULT_INCUBATION_MINUTES)
        self._picture_rounds = tk.IntVar(value=DEFAULT_PICTURE_ROUNDS)
        self._interval_vars = [
            tk.StringVar(value=str(DEFAULT_PICTURE_INTERVAL_MIN))
            for _ in range(MAX_PICTURE_ROUNDS)
        ]

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        top = tk.Frame(self.root, bg=BG, padx=12, pady=10)
        top.pack(fill=tk.BOTH, expand=True)

        left = tk.Frame(top, bg=PANEL, padx=10, pady=10)
        left.pack(side=tk.LEFT, fill=tk.Y)

        tk.Label(
            left, text="Procedure steps", bg=PANEL, fg=TEXT, font=("Segoe UI", 12, "bold")
        ).pack(anchor="w", pady=(0, 8))

        steps = [
            ("1. All Home", step_01_all_home),
            ("2. Insert Petri Dishes", step_02_insert_petri_dishes),
            ("3. Shift for Incubation", step_03_shift_for_incubation),
            ("4. Start Incubation", self._run_incubation_only),
            ("5. Take Pictures", self._run_pictures_only),
            ("6. Sterilize", step_06_sterilize),
        ]
        for label, fn in steps:
            self._mk_btn(left, label, fn).pack(fill=tk.X, pady=4)

        self._mk_btn(left, "Timed Study (incubate + capture)", self._run_timed_study, ACCENT2).pack(
            fill=tk.X, pady=(14, 4)
        )

        center = tk.Frame(top, bg=BG, padx=12)
        center.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        tk.Label(
            center, textvariable=self._status_display, bg=BG, fg=ACCENT, font=("Segoe UI", 11)
        ).pack(anchor="w")

        viz = tk.Frame(center, bg=PANEL, padx=16, pady=16)
        viz.pack(fill=tk.X, pady=8)

        self._canvas = tk.Canvas(viz, width=320, height=220, bg=PANEL, highlightthickness=0)
        self._canvas.pack()
        self._draw_idle_gauge()

        tk.Label(
            viz, textvariable=self._temp_display, bg=PANEL, fg=TEXT, font=("Segoe UI", 28, "bold")
        ).pack(pady=(8, 0))
        tk.Label(
            viz, textvariable=self._target_display, bg=PANEL, fg=MUTED, font=("Segoe UI", 11)
        ).pack()
        tk.Label(
            viz, textvariable=self._time_display, bg=PANEL, fg=ACCENT2, font=("Segoe UI", 14)
        ).pack(pady=(6, 0))

        tk.Label(center, text="Log", bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w")
        self._log = scrolledtext.ScrolledText(
            center, height=12, bg="#151a22", fg=TEXT, insertbackground=TEXT, font=("Consolas", 9)
        )
        self._log.pack(fill=tk.BOTH, expand=True, pady=(4, 0))

        right = tk.Frame(top, bg=PANEL, padx=12, pady=10)
        right.pack(side=tk.RIGHT, fill=tk.Y)

        tk.Label(right, text="Settings", bg=PANEL, fg=TEXT, font=("Segoe UI", 12, "bold")).pack(
            anchor="w", pady=(0, 10)
        )

        self._counter_row(right, "Petri dishes", self._petri_count, 1, MAX_PETRI_DISHES)
        self._counter_row(right, "Incubation cycles", self._incub_count, 1, 20)

        tk.Label(right, text="Incubation °C", bg=PANEL, fg=MUTED).pack(anchor="w", pady=(10, 0))
        tk.Spinbox(
            right,
            from_=20,
            to=50,
            increment=0.5,
            textvariable=self._incub_temp,
            width=8,
        ).pack(anchor="w")

        tk.Label(right, text="Minutes per cycle", bg=PANEL, fg=MUTED).pack(anchor="w", pady=(8, 0))
        tk.Spinbox(
            right,
            from_=0.5,
            to=600,
            increment=0.5,
            textvariable=self._incub_minutes,
            width=8,
        ).pack(anchor="w")

        tk.Label(right, text="Picture rounds", bg=PANEL, fg=MUTED).pack(anchor="w", pady=(14, 0))
        self._counter_row(right, "", self._picture_rounds, 1, MAX_PICTURE_ROUNDS)

        tk.Label(
            right,
            text="Minutes before each round",
            bg=PANEL,
            fg=MUTED,
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(10, 4))

        opts = [str(x) for x in PICTURE_INTERVAL_OPTIONS]
        for i in range(MAX_PICTURE_ROUNDS):
            row = tk.Frame(right, bg=PANEL)
            row.pack(fill=tk.X, pady=2)
            tk.Label(row, text=f"Round {i + 1}", bg=PANEL, fg=TEXT, width=8, anchor="w").pack(
                side=tk.LEFT
            )
            cb = ttk.Combobox(
                row, textvariable=self._interval_vars[i], values=opts, width=5, state="readonly"
            )
            cb.pack(side=tk.LEFT)
            if str(DEFAULT_PICTURE_INTERVAL_MIN) not in opts:
                cb.set(str(PICTURE_INTERVAL_OPTIONS[1]))

    def _mk_btn(self, parent, text, command, color=ACCENT):
        return tk.Button(
            parent,
            text=text,
            command=lambda: self._run_action(text, command),
            bg=color,
            fg="#102030",
            activebackground="#8ab4e8",
            relief=tk.FLAT,
            padx=8,
            pady=8,
            font=("Segoe UI", 10, "bold"),
            cursor="hand2",
        )

    def _counter_row(self, parent, label, var, vmin, vmax):
        tk.Label(parent, text=label, bg=PANEL, fg=MUTED).pack(anchor="w", pady=(8, 0))
        row = tk.Frame(parent, bg=PANEL)
        row.pack(fill=tk.X, pady=4)

        def dec():
            var.set(max(vmin, int(var.get()) - 1))

        def inc():
            var.set(min(vmax, int(var.get()) + 1))

        tk.Button(row, text="−", width=3, command=dec, bg="#3d465c", fg=TEXT, relief=tk.FLAT).pack(
            side=tk.LEFT
        )
        tk.Label(row, textvariable=var, bg=PANEL, fg=TEXT, width=4, font=("Segoe UI", 14, "bold")).pack(
            side=tk.LEFT, padx=8
        )
        tk.Button(row, text="+", width=3, command=inc, bg="#3d465c", fg=TEXT, relief=tk.FLAT).pack(
            side=tk.LEFT
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
        self._log_msg(
            f"Incubation: {self._incub_count.get()}× "
            f"{self._incub_temp.get()}°C for {self._incub_minutes.get()} min"
        )
        step_04_incubation(
            target_c=self._incub_temp.get(),
            minutes=self._incub_minutes.get(),
            count=self._incub_count.get(),
            on_tick=self._incubation_tick,
        )

    def _do_pictures(self):
        n = int(self._petri_count.get())
        self._log_msg(f"Prepare imaging, then capture {n} petri dish(es)")
        step_05_prepare_imaging()
        exp = capture_petri_dishes(n)
        step_05_post_imaging_cleanup()
        self._log_msg(f"Saved under: {exp}")

    def _run_incubation_only(self):
        pass

    def _run_pictures_only(self):
        pass

    def _run_timed_study(self):
        pass

    def _do_timed_study(self):
        n_petri = int(self._petri_count.get())
        n_rounds = int(self._picture_rounds.get())
        intervals = [int(float(v.get())) for v in self._interval_vars]
        self._log_msg(
            f"Timed study: {n_rounds} round(s), petri={n_petri}, intervals={intervals[:n_rounds]}"
        )

        def on_log(msg):
            self.root.after(0, lambda: self._log_msg(msg))

        exp = run_timed_picture_study(
            num_petri_dishes=n_petri,
            num_rounds=n_rounds,
            interval_minutes=intervals,
            target_c=self._incub_temp.get(),
            on_tick=self._incubation_tick,
            on_log=on_log,
        )
        self._log_msg(f"Experiment folder: {exp}")

    def _draw_idle_gauge(self):
        c = self._canvas
        c.delete("all")
        cx, cy, r = 160, 110, 78
        c.create_oval(cx - r, cy - r, cx + r, cy + r, outline="#3d465c", width=14)
        c.create_text(cx, cy, text="Ready", fill=MUTED, font=("Segoe UI", 14))

    def _draw_gauge(self, temp_c, target_c, remaining_s, elapsed_s):
        c = self._canvas
        c.delete("all")
        cx, cy, r = 160, 110, 78

        # Time ring (green)
        total = max(1.0, elapsed_s + remaining_s)
        frac = min(1.0, elapsed_s / total)
        c.create_oval(cx - r, cy - r, cx + r, cy + r, outline="#3d465c", width=12)
        if frac > 0:
            c.create_arc(
                cx - r,
                cy - r,
                cx + r,
                cy + r,
                start=90,
                extent=-360 * frac,
                outline=ACCENT2,
                width=12,
                style=tk.ARC,
            )

        # Temperature bar (bottom)
        tfrac = min(1.0, max(0.0, temp_c / max(50.0, target_c + 5)))
        bx0, bx1, by = 40, 280, 195
        c.create_rectangle(bx0, by, bx1, by + 14, fill="#3d465c", outline="")
        c.create_rectangle(bx0, by, bx0 + (bx1 - bx0) * tfrac, by + 14, fill=WARN, outline="")
        c.create_text(cx, 28, text="Incubating", fill=ACCENT, font=("Segoe UI", 11, "bold"))

        # Decorative bubbles
        for i, (ox, oy, rad) in enumerate([(50, 60, 8), (260, 80, 6), (230, 160, 10)]):
            c.create_oval(ox - rad, oy - rad, ox + rad, oy + rad, fill=ACCENT, stipple="gray50")

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
