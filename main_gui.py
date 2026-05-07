"""
Tkinter GUI for automation workflow.

Features:
- Responsive main window for different screen sizes
- Main screen: Run Experiment, Test Camera (full run is inside the experiment window)
"""

import atexit
import gc
import glob
import os
import signal
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

import cv2
from PIL import Image, ImageDraw, ImageFont, ImageTk
import RPi.GPIO as GPIO


def _find_asset_path(filename, extra_candidates=None):
    """Find asset by filename in project folder or provided candidates."""
    candidates = [os.path.join(os.path.dirname(__file__), filename)]
    if extra_candidates:
        candidates.extend(extra_candidates)
    for path in candidates:
        try:
            if path and os.path.exists(path):
                return path
        except Exception:
            continue
    return None


def _rounded_button_photo(width, height, radius, bg_rgb, text, fg="#FFFFFF", font_size=18):
    """PIL image for a large rounded-corner touch button (keep reference on widget)."""
    img = Image.new("RGBA", (int(width), int(height)), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)
    rect = (0, 0, width - 1, height - 1)
    try:
        dr.rounded_rectangle(rect, radius=int(radius), fill=bg_rgb)
    except AttributeError:
        dr.rectangle(rect, fill=bg_rgb)
    font = None
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ):
        try:
            font = ImageFont.truetype(path, int(font_size))
            break
        except Exception:
            continue
    if font is None:
        font = ImageFont.load_default()
    bbox = dr.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    tx = max(0, (width - tw) // 2)
    ty = max(0, (height - th) // 2 - 2)
    dr.text((tx, ty), text, fill=fg, font=font)
    return ImageTk.PhotoImage(img)


def _make_rounded_button(
    parent,
    text,
    command,
    width,
    height,
    radius,
    bg_rgb,
    font_size=18,
    parent_bg="#F3F6FB",
):
    """Create a rounded-corner tk.Button using a generated image."""
    img = _rounded_button_photo(width, height, radius, bg_rgb, text, font_size=font_size)
    btn = tk.Button(
        parent,
        image=img,
        command=command,
        borderwidth=0,
        highlightthickness=0,
        cursor="hand2",
        bg=parent_bg,
        activebackground=parent_bg,
    )
    btn.image = img
    return btn

def _missing_function(module_name, func_name):
    def _inner(*_args, **_kwargs):
        raise RuntimeError(f"Missing module '{module_name}': cannot run '{func_name}()'")
    return _inner


def _missing_cleanup(*_args, **_kwargs):
    return None


from camera_module import Camera_home, Camera_down, cleanup as camera_cleanup
from imaging import start_imaging_capture_pattern
from incubator_lid import incubator_lid_home, incubator_lid_up, cleanup as incubator_lid_cleanup
from relay_control import P1, run_relay, set_relay, cleanup as relay_cleanup

try:
    from filteration_flask import (
        Filteration_flask_up,
        filteration_flask_config,
        cleanup as filteration_cleanup,
    )
except ModuleNotFoundError:
    Filteration_flask_up = _missing_function("filteration_flask", "Filteration_flask_up")
    filteration_flask_config = _missing_function("filteration_flask", "filteration_flask_config")
    filteration_cleanup = _missing_cleanup

try:
    from filteration_suction_pump import (
        filteration_suction_pump_on,
        filteration_suction_pump_off,
        cleanup as filteration_suction_cleanup,
    )
except ModuleNotFoundError:
    filteration_suction_pump_on = _missing_function("filteration_suction_pump", "filteration_suction_pump_on")
    filteration_suction_pump_off = _missing_function("filteration_suction_pump", "filteration_suction_pump_off")
    filteration_suction_cleanup = _missing_cleanup

try:
    from filteration_unit import Filteration_unit_up, filteration_unit_config, cleanup as filteration_unit_cleanup
except ModuleNotFoundError:
    Filteration_unit_up = _missing_function("filteration_unit", "Filteration_unit_up")
    filteration_unit_config = _missing_function("filteration_unit", "filteration_unit_config")
    filteration_unit_cleanup = _missing_cleanup

try:
    from media_dispensor import (
        Media_dispensor_home,
        Media_dispensor_up,
        Media_dispensor_down,
        media_dispensor_home_pressed,
        cleanup as media_dispensor_cleanup,
    )
except ModuleNotFoundError:
    Media_dispensor_home = _missing_function("media_dispensor", "Media_dispensor_home")
    Media_dispensor_up = _missing_function("media_dispensor", "Media_dispensor_up")
    Media_dispensor_down = _missing_function("media_dispensor", "Media_dispensor_down")
    media_dispensor_home_pressed = _missing_function("media_dispensor", "media_dispensor_home_pressed")
    media_dispensor_cleanup = _missing_cleanup

try:
    from petri_dishes import (
        petri_dishes_home,
        petri_dishes_down,
        petri_dishes_up,
        cleanup as petri_dishes_cleanup,
    )
except ModuleNotFoundError:
    petri_dishes_home = _missing_function("petri_dishes", "petri_dishes_home")
    petri_dishes_down = _missing_function("petri_dishes", "petri_dishes_down")
    petri_dishes_up = _missing_function("petri_dishes", "petri_dishes_up")
    petri_dishes_cleanup = _missing_cleanup

try:
    from solinoid_value_drain import cleanup as drain_solenoid_cleanup
except ModuleNotFoundError:
    drain_solenoid_cleanup = _missing_cleanup

try:
    from solinoid_value_to_filteration import (
        solinoid_value_to_filteration,
        water_level_reached,
        cleanup as solenoid_cleanup,
    )
except ModuleNotFoundError:
    solinoid_value_to_filteration = _missing_function("solinoid_value_to_filteration", "solinoid_value_to_filteration")
    water_level_reached = _missing_function("solinoid_value_to_filteration", "water_level_reached")
    solenoid_cleanup = _missing_cleanup

try:
    from solinoid_waste import (
        solinoid_waste_on,
        solinoid_waste_off,
        cleanup as waste_solenoid_cleanup,
    )
except ModuleNotFoundError:
    solinoid_waste_on = _missing_function("solinoid_waste", "solinoid_waste_on")
    solinoid_waste_off = _missing_function("solinoid_waste", "solinoid_waste_off")
    waste_solenoid_cleanup = _missing_cleanup

try:
    from suction_pipe import suction_pipe_home, suction_pipe_up, suction_pipe_down, cleanup as suction_pipe_cleanup
except ModuleNotFoundError:
    suction_pipe_home = _missing_function("suction_pipe", "suction_pipe_home")
    suction_pipe_up = _missing_function("suction_pipe", "suction_pipe_up")
    suction_pipe_down = _missing_function("suction_pipe", "suction_pipe_down")
    suction_pipe_cleanup = _missing_cleanup

try:
    from suction_pump_up_down import (
        suction_pump_home,
        suction_pump_up,
        suction_pump_down,
        cleanup as suction_lift_cleanup,
    )
except ModuleNotFoundError:
    suction_pump_home = _missing_function("suction_pump_up_down", "suction_pump_home")
    suction_pump_up = _missing_function("suction_pump_up_down", "suction_pump_up")
    suction_pump_down = _missing_function("suction_pump_up_down", "suction_pump_down")
    suction_lift_cleanup = _missing_cleanup

try:
    from upper_suction_pump import upper_suction_pump_on, upper_suction_pump_off, cleanup as suction_cleanup
except ModuleNotFoundError:
    upper_suction_pump_on = _missing_function("upper_suction_pump", "upper_suction_pump_on")
    upper_suction_pump_off = _missing_function("upper_suction_pump", "upper_suction_pump_off")
    suction_cleanup = _missing_cleanup


_shutdown_done = False
CAMERA_RELAY_GPIO = 25  # Physical pin 22
CAMERA_RELAY_ACTIVE = GPIO.LOW
CAMERA_RELAY_INACTIVE = GPIO.HIGH


def _bootstrap_gpio():
    """Best-effort GPIO baseline for GUI-driven runs."""
    try:
        GPIO.setwarnings(False)
    except Exception:
        pass
    try:
        GPIO.setmode(GPIO.BCM)
    except Exception:
        pass
    try:
        GPIO.setup(CAMERA_RELAY_GPIO, GPIO.OUT, initial=CAMERA_RELAY_INACTIVE)
    except Exception:
        pass


def pulse_camera_relay(seconds=3.0, active_state=None):
    """
    Pulse camera relay GPIO for camera power toggle.
    Camera power toggles when relay is ON for ~3 seconds.
    """
    _bootstrap_gpio()
    on_state = CAMERA_RELAY_ACTIVE if active_state is None else active_state
    GPIO.output(CAMERA_RELAY_GPIO, on_state)
    time.sleep(max(0.0, float(seconds)))
    # Always restore configured OFF state (important for active-low relays).
    GPIO.output(CAMERA_RELAY_GPIO, CAMERA_RELAY_INACTIVE)


def camera_relay_force_off():
    """Force camera relay to OFF state."""
    _bootstrap_gpio()
    GPIO.output(CAMERA_RELAY_GPIO, CAMERA_RELAY_INACTIVE)


def shutdown_all():
    global _shutdown_done
    if _shutdown_done:
        return
    _shutdown_done = True
    print("\n[Shutdown] Releasing GPIO and stopping outputs...")

    for name, fn in (
        ("filteration_suction_pump", filteration_suction_cleanup),
        ("upper_suction_pump (DC)", suction_cleanup),
        ("suction_pump_up_down", suction_lift_cleanup),
        ("relay", relay_cleanup),
        ("solenoid", solenoid_cleanup),
        ("drain_solenoid", drain_solenoid_cleanup),
        ("waste_solenoid", waste_solenoid_cleanup),
        ("filteration_flask", filteration_cleanup),
        ("filteration_unit", filteration_unit_cleanup),
        ("petri_dishes", petri_dishes_cleanup),
        ("camera", camera_cleanup),
        ("media_dispensor", media_dispensor_cleanup),
        ("suction_pipe", suction_pipe_cleanup),
        ("incubator_lid", incubator_lid_cleanup),
    ):
        try:
            fn()
        except Exception as exc:
            print(f"  Cleanup warning ({name}): {exc}")

    gc.collect()
    try:
        GPIO.cleanup()
    except Exception:
        pass
    print("[Shutdown] Done.")


def _on_sigterm(signum, frame):
    shutdown_all()
    sys.exit(0)


signal.signal(signal.SIGTERM, _on_sigterm)
atexit.register(shutdown_all)


def open_usb_camera(device_index=0):
    idx = int(device_index)
    if sys.platform.startswith("linux"):
        cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
    else:
        cap = cv2.VideoCapture(idx)
    if not cap.isOpened():
        return None
    try:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    except Exception:
        pass
    return cap


def open_usb_camera_with_recovery(
    device_index=0,
    direct_tries=3,
    retry_wait_s=1.0,
    post_relay_wait_s=4.0,
    post_relay_tries=5,
):
    """
    Always toggle camera power relay once, then try opening camera.
    If open fails, toggle once more and retry.
    Returns an opened capture or None.
    """
    # Required behavior: on camera open request, pulse relay for 3 s,
    # then return relay to OFF/original state.
    pulse_camera_relay(3, active_state=CAMERA_RELAY_ACTIVE)
    time.sleep(float(post_relay_wait_s))
    for _ in range(max(1, int(post_relay_tries))):
        cap = open_usb_camera(device_index)
        if cap is not None:
            return cap
        time.sleep(float(retry_wait_s))

    # One more deterministic pulse+retry.
    camera_relay_force_off()
    pulse_camera_relay(3, active_state=CAMERA_RELAY_ACTIVE)
    time.sleep(float(post_relay_wait_s))
    for _ in range(max(1, int(post_relay_tries))):
        cap = open_usb_camera(device_index)
        if cap is not None:
            return cap
        time.sleep(float(retry_wait_s))
    camera_relay_force_off()
    return None


class CameraTestWindow:
    def __init__(self, parent, cap, on_close=None, app=None):
        self.win = tk.Toplevel(parent)
        self._app = app
        self._closing = False
        try:
            if hasattr(parent, "_app_icon_photo") and parent._app_icon_photo is not None:
                self.win.iconphoto(True, parent._app_icon_photo)
        except Exception:
            pass
        self.win.title("USB Camera Test")
        self.win.geometry("1028x600")
        self.win.minsize(900, 520)
        self.win.protocol("WM_DELETE_WINDOW", self.on_close)
        self._on_close_cb = on_close

        container = tk.Frame(self.win, bg="#0C1522")
        container.pack(fill=tk.BOTH, expand=True)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(1, weight=1)

        header = tk.Frame(container, bg="#0F2C52", height=72)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        tk.Label(
            header,
            text="USB Camera Test Console",
            bg="#0F2C52",
            fg="#F2F7FF",
            font=("TkDefaultFont", 20, "bold"),
        ).pack(side=tk.LEFT, padx=14)
        self.status_text = tk.StringVar(value="Live stream active")
        tk.Label(
            header,
            textvariable=self.status_text,
            bg="#0F2C52",
            fg="#BFD3F2",
            font=("TkDefaultFont", 12, "bold"),
        ).pack(side=tk.LEFT, padx=12)

        body = tk.Frame(container, bg="#0C1522")
        body.grid(row=1, column=0, sticky="nsew", padx=8, pady=6)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)

        preview_card = tk.Frame(body, bg="#111F33", bd=0, highlightthickness=0)
        preview_card.grid(row=0, column=0, sticky="nsew")
        preview_card.columnconfigure(0, weight=1)
        preview_card.rowconfigure(0, weight=1)
        self.preview = tk.Label(preview_card, bg="#111F33")
        self.preview.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)

        close_img = _rounded_button_photo(400, 92, 32, (194, 77, 0), "Close Camera", font_size=32)
        self.btn_close_camera = tk.Button(
            body,
            image=close_img,
            command=self.on_close,
            borderwidth=0,
            highlightthickness=0,
            bg="#0C1522",
            activebackground="#0C1522",
            cursor="hand2",
        )
        self.btn_close_camera.image = close_img
        self.btn_close_camera.grid(row=1, column=0, pady=(8, 4))

        self.cap = cap
        if self.cap is None:
            messagebox.showerror("Camera", "Error in loading camera. See the console.")
            self.win.after(50, self.win.destroy)
            return

        self.running = True
        self.photo = None
        self.update_frame()

    def update_frame(self):
        if not getattr(self, "running", False) or self.cap is None:
            return
        ok, frame = self.cap.read()
        if ok and frame is not None:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w = rgb.shape[:2]
            max_w = max(920, self.win.winfo_width() - 36)
            max_h = max(500, self.win.winfo_height() - 175)
            scale = min(float(max_w) / float(w), float(max_h) / float(h))
            if scale < 1.0:
                rgb = cv2.resize(rgb, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
            img = Image.fromarray(rgb)
            self.photo = ImageTk.PhotoImage(img)
            self.preview.configure(image=self.photo)
            self.status_text.set("Live stream active")
        else:
            self.status_text.set("Waiting for camera frame...")
        self.win.after(30, self.update_frame)

    def on_close(self):
        if self._closing:
            return
        self._closing = True
        self.running = False
        try:
            self.btn_close_camera.config(state=tk.DISABLED)
        except Exception:
            pass
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None

        if self._app is not None:
            self._app._show_camera_closing_popup()

        def _relay_worker():
            try:
                pulse_camera_relay(3)
            finally:
                self.win.after(0, self._after_relay_close)

        threading.Thread(target=_relay_worker, daemon=True).start()

    def _after_relay_close(self):
        try:
            camera_relay_force_off()
        except Exception:
            pass
        try:
            if self._app is not None:
                self._app._hide_camera_closing_popup()
        except Exception:
            pass
        if callable(self._on_close_cb):
            try:
                self._on_close_cb()
            except Exception:
                pass
        try:
            self.win.destroy()
        except Exception:
            pass


class ExperimentApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Automation Device Controller")
        self.root.minsize(960, 560)
        self.root.protocol("WM_DELETE_WINDOW", self.on_exit)
        try:
            self.root.attributes("-fullscreen", True)
        except Exception:
            self.root.geometry(self._initial_geometry())
        self._setup_styles()
        self._app_icon_photo = None
        self._title_icon_photo = None
        self._apply_app_icon(self.root)

        self.is_busy = False
        self.initialized = False
        self._last_step_success = None
        self._run_experiment_popup = None

        self.steps = [
            self.step_1,
            self.step_2,
            self.step_3,
            self.step_4,
            self.step_5,
            self.step_6,
            self.step_7,
            self.step_8,
            self.step_9,
            self.step_10,
            self.step_11,
            self.step_12,
            self.step_13,
            self.step_14,
            self.step_15,
        ]
        self.step_labels = [
            "All Module Home",
            "Change Media",
            "Adjust Syringe",
            "Petri Home",
            "Load Filter Paper",
            "Send to Assembly",
            "Pick Media Pad",
            "Pour Media",
            "Pick Filtration Unit",
            "Pick Filter Paper",
            "Shift Incubation",
            "Start Incubation",
            "Start Pictures",
            "Trash Transfer",
            "Sterilize",
        ]
        # Full run sequence follows the "actual experiment" flow shown in manual section.
        self.full_experiment_sequence = [1] + list(range(4, 15))

        outer = ttk.Frame(root, padding=12, style="App.TFrame")
        outer.pack(fill=tk.BOTH, expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(4, weight=1)

        header = tk.Frame(outer, bg="#113058", bd=0, highlightthickness=0)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        header.columnconfigure(0, weight=1)
        header.configure(height=120)
        header.grid_propagate(False)

        title_wrap = tk.Frame(header, bg="#113058")
        title_wrap.grid(row=0, column=0, rowspan=2, sticky="w")
        self._apply_title_icon(title_wrap)

        text_col = tk.Frame(title_wrap, bg="#113058")
        text_col.pack(side=tk.LEFT, padx=(16, 0), pady=(8, 0))
        tk.Label(
            text_col,
            text="Automatic Microbial Detection System",
            bg="#113058",
            fg="#F2F7FF",
            font=("TkDefaultFont", 22, "bold"),
        ).pack(anchor="w")
        tk.Label(
            text_col,
            text="Touch Control Console",
            bg="#113058",
            fg="#BFD3F2",
            font=("TkDefaultFont", 14, "bold"),
        ).pack(anchor="w", pady=(2, 0))

        close_img = _rounded_button_photo(
            236, 94, 34, (194, 77, 0), "Close", font_size=33
        )
        self.btn_close = tk.Button(
            header,
            image=close_img,
            command=self.on_exit,
            borderwidth=0,
            highlightthickness=0,
            cursor="hand2",
            bg="#113058",
            activebackground="#113058",
        )
        self.btn_close.image = close_img
        self.btn_close.grid(row=0, column=1, sticky="e", padx=(12, 0))

        # Push main action buttons down for easier thumb reach on 7" touch LCD.
        spacer = ttk.Frame(outer, style="App.TFrame", height=24)
        spacer.grid(row=1, column=0, sticky="ew")
        spacer.grid_propagate(False)

        action_card = ttk.Frame(outer, style="Card.TFrame", padding=12)
        action_card.grid(row=2, column=0, sticky="ew", pady=(8, 10))
        action_card.columnconfigure(0, weight=1)
        action_card.columnconfigure(1, weight=1)
        action_card.columnconfigure(2, weight=1)
        ttk.Label(action_card, text="Main Actions", style="CardTitle.TLabel").grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 10)
        )

        btn_row = ttk.Frame(action_card, style="Card.TFrame")
        btn_row.grid(row=1, column=0, columnspan=3, sticky="ew")
        btn_row.columnconfigure(0, weight=1)
        btn_row.columnconfigure(1, weight=1)
        btn_row.columnconfigure(2, weight=1)

        bw, bh, br = 380, 134, 31
        ph_steps = _rounded_button_photo(
            bw, bh, br, (22, 98, 212), "Run Experiment", font_size=26
        )
        ph_cam = _rounded_button_photo(
            bw, bh, br, (212, 106, 9), "Test Camera", font_size=26
        )
        ph_take = _rounded_button_photo(
            bw, bh, br, (12, 158, 94), "Take Images", font_size=26
        )

        self.btn_step = tk.Button(
            btn_row,
            image=ph_steps,
            command=self.open_step_popup,
            borderwidth=0,
            highlightthickness=0,
            cursor="hand2",
            bg="#F3F6FB",
            activebackground="#F3F6FB",
        )
        self.btn_step.image = ph_steps
        self.btn_step.grid(row=0, column=0, sticky="ew", padx=(0, 10))

        self.btn_camera = tk.Button(
            btn_row,
            image=ph_cam,
            command=self.open_camera_test,
            borderwidth=0,
            highlightthickness=0,
            cursor="hand2",
            bg="#F3F6FB",
            activebackground="#F3F6FB",
        )
        self.btn_camera.image = ph_cam
        self.btn_camera.grid(row=0, column=1, sticky="ew", padx=8)

        self.btn_take_images = tk.Button(
            btn_row,
            image=ph_take,
            command=self.open_take_images,
            borderwidth=0,
            highlightthickness=0,
            cursor="hand2",
            bg="#F3F6FB",
            activebackground="#F3F6FB",
        )
        self.btn_take_images.image = ph_take
        self.btn_take_images.grid(row=0, column=2, sticky="ew", padx=(8, 0))

        self.status_var = tk.StringVar(value="Ready.")
        status_card = ttk.Frame(outer, style="StatusCard.TFrame", padding=(10, 8))
        status_card.grid(row=3, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(status_card, text="System Status:", style="StatusKey.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(status_card, textvariable=self.status_var, style="Status.TLabel").grid(
            row=0, column=1, sticky="w", padx=(8, 0)
        )

        self.log = tk.Text(
            outer,
            wrap=tk.WORD,
            height=16,
            font=("TkDefaultFont", 12),
            bg="#0D1726",
            fg="#EAF1FF",
            insertbackground="#EAF1FF",
            relief=tk.FLAT,
            padx=8,
            pady=8,
        )
        self.log.grid(row=4, column=0, sticky="nsew")
        self._incubation_stop_requested = False
        self._camera_test_active = False
        self._camera_test_done_once = False
        self._camera_loading_popup = None
        self._camera_closing_popup = None

    def _setup_styles(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("App.TFrame", background="#E9EEF7")
        style.configure("Header.TFrame", background="#113058")
        style.configure("Card.TFrame", background="#F7FAFF")
        style.configure("StatusCard.TFrame", background="#DFE9F8")
        style.configure("Title.TLabel", background="#113058", foreground="#F2F7FF", font=("TkDefaultFont", 22, "bold"))
        style.configure("SubTitle.TLabel", background="#113058", foreground="#BFD3F2", font=("TkDefaultFont", 14, "bold"))
        style.configure("CardTitle.TLabel", background="#F7FAFF", foreground="#1D3557", font=("TkDefaultFont", 15, "bold"))
        style.configure("StatusKey.TLabel", background="#DFE9F8", foreground="#1D3557", font=("TkDefaultFont", 13, "bold"))
        style.configure("Status.TLabel", background="#DFE9F8", foreground="#173C6A", font=("TkDefaultFont", 13, "bold"))
        style.configure(
            "ActionBlue.TButton",
            font=("TkDefaultFont", 14, "bold"),
            padding=(10, 14),
            foreground="white",
            background="#1662D4",
            borderwidth=1,
        )
        style.map("ActionBlue.TButton", background=[("active", "#0F56BF")])
        style.configure(
            "ActionGreen.TButton",
            font=("TkDefaultFont", 14, "bold"),
            padding=(10, 14),
            foreground="white",
            background="#0C9E5E",
            borderwidth=1,
        )
        style.map("ActionGreen.TButton", background=[("active", "#09874F")])
        style.configure(
            "ActionOrange.TButton",
            font=("TkDefaultFont", 14, "bold"),
            padding=(10, 14),
            foreground="white",
            background="#D46A09",
            borderwidth=1,
        )
        style.map("ActionOrange.TButton", background=[("active", "#B45705")])
        style.configure("StepPopup.TButton", font=("TkDefaultFont", 13, "bold"), padding=(10, 12))

    def _apply_app_icon(self, win):
        """Load icon.png from project root and apply to a window."""
        icon_path = _find_asset_path(
            "icon.png",
            extra_candidates=[
                r"D:\office_project_data\automation_device\Automation_Code_v1\icon.png",
            ],
        )
        if not icon_path:
            return
        try:
            if self._app_icon_photo is None:
                self._app_icon_photo = tk.PhotoImage(file=icon_path)
            win.iconphoto(True, self._app_icon_photo)
        except Exception:
            pass

    def _apply_title_icon(self, parent_frame):
        """Show icon.png next to main system title."""
        icon_path = _find_asset_path(
            "icon.png",
            extra_candidates=[
                r"D:\office_project_data\automation_device\Automation_Code_v1\icon.png",
            ],
        )
        if not icon_path:
            return
        try:
            src = Image.open(icon_path).convert("RGBA")
            icon_img = src.resize((84, 84), Image.LANCZOS)
            self._title_icon_photo = ImageTk.PhotoImage(icon_img)
            tk.Label(parent_frame, image=self._title_icon_photo, bg="#113058").pack(side=tk.LEFT)
        except Exception:
            pass

    def _run_with_gpio_retry(self, label, fn, *args, **kwargs):
        """Retry several times if GPIO allocation state is transiently invalid."""
        attempts = 4
        for attempt in range(1, attempts + 1):
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                msg = str(exc)
                if "GPIO not allocated" not in msg:
                    raise
                if attempt >= attempts:
                    raise
                self.write_log(
                    f"{label}: GPIO not allocated (try {attempt}/{attempts}), reinitializing GPIO"
                )
                # Do not call GPIO.cleanup() here: it can desync module-level
                # "_initialized" flags from real GPIO state and cause repeated failures.
                for reset_fn in (
                    media_dispensor_cleanup,
                    incubator_lid_cleanup,
                    suction_pipe_cleanup,
                    filteration_unit_cleanup,
                    filteration_cleanup,
                    petri_dishes_cleanup,
                    suction_lift_cleanup,
                    camera_cleanup,
                    filteration_suction_cleanup,
                    suction_cleanup,
                ):
                    try:
                        reset_fn()
                    except Exception:
                        pass
                _bootstrap_gpio()
                time.sleep(0.25)

    def _initial_geometry(self):
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        w = min(sw, 1028)
        h = min(sh, 600)
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        return f"{w}x{h}+{x}+{y}"

    def _enforce_fullscreen(self, win):
        """Force a toplevel to occupy full screen reliably across WMs."""
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()

        def _apply_once():
            try:
                if not win.winfo_exists():
                    return
            except Exception:
                return
            try:
                win.geometry(f"{sw}x{sh}+0+0")
            except Exception:
                pass
            try:
                win.attributes("-fullscreen", True)
            except Exception:
                pass
            try:
                win.state("zoomed")
            except Exception:
                pass
            try:
                win.lift()
                win.focus_force()
            except Exception:
                pass

        # Apply now + re-apply after mapping (Pi/X11 can ignore first request).
        _apply_once()
        win.after(60, _apply_once)
        win.after(220, _apply_once)

    def set_busy(self, busy, status_text):
        self.is_busy = busy
        state = tk.DISABLED if busy else tk.NORMAL
        self.btn_step.config(state=state)
        self.btn_camera.config(state=state)
        self.btn_take_images.config(state=state)
        self.status_var.set(status_text)

    def write_log(self, text):
        self.log.insert(tk.END, text + "\n")
        self.log.see(tk.END)
        self.root.update_idletasks()

    def ensure_initialized(self):
        if self.initialized:
            return
        self.write_log("Initial setup: bring all modules to home/start position")
        _bootstrap_gpio()
        self._run_with_gpio_retry("Incubator lid home", incubator_lid_home)
        self._run_with_gpio_retry("Suction pipe home", suction_pipe_home)
        self._run_with_gpio_retry("Filteration unit config", filteration_unit_config)
        self._run_with_gpio_retry("Filteration flask config", filteration_flask_config)
        self._run_with_gpio_retry("Petri dishes home", petri_dishes_home)
        self._run_with_gpio_retry("Petri dishes down", petri_dishes_down, 1035)
        self._run_with_gpio_retry("Suction pump home", suction_pump_home)
        self._run_with_gpio_retry("Suction pump up", suction_pump_up, 400)
        self.initialized = True

    def open_step_popup(self):
        if self.is_busy:
            return
        popup = tk.Toplevel(self.root)
        self._run_experiment_popup = popup
        self._apply_app_icon(popup)
        popup.title("Run Experiment")
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self._enforce_fullscreen(popup)
        popup.minsize(min(800, sw), min(480, sh))

        outer = tk.Frame(popup, bg="#E9EEF7")
        outer.pack(fill=tk.BOTH, expand=True)
        outer.rowconfigure(0, weight=0)
        outer.rowconfigure(1, weight=1)
        outer.columnconfigure(0, weight=1)

        header = tk.Frame(outer, bg="#0F2C52", height=88)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        header.columnconfigure(1, weight=1)
        if getattr(self, "_title_icon_photo", None) is not None:
            tk.Label(header, image=self._title_icon_photo, bg="#0F2C52").grid(
                row=0, column=0, rowspan=2, padx=(14, 8), pady=10, sticky="nw"
            )
        tk.Label(
            header,
            text="Experiment Control Panel",
            bg="#0F2C52",
            fg="#F2F7FF",
            font=("TkDefaultFont", 20, "bold"),
        ).grid(row=0, column=1, sticky="nw", pady=(10, 0))
        tk.Label(
            header,
            text="Automatic Microbial Detection System",
            bg="#0F2C52",
            fg="#BFD3F2",
            font=("TkDefaultFont", 13, "bold"),
        ).grid(row=1, column=1, sticky="nw", pady=(0, 10))

        left_w = min(500, max(360, int(sw * 0.36)))
        run_col_w = max(190, left_w - 190)

        content = tk.Frame(outer, bg="#E9EEF7")
        content.grid(row=1, column=0, sticky="nsew")
        content.rowconfigure(0, weight=1)
        content.columnconfigure(0, weight=0, minsize=left_w)
        content.columnconfigure(1, weight=1)

        left_panel = tk.Frame(content, bg="#CFD9EA", width=left_w)
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=0)
        left_panel.columnconfigure(0, weight=1)
        left_panel.columnconfigure(1, weight=0)
        left_panel.columnconfigure(2, weight=0)
        left_panel.columnconfigure(3, weight=0)

        tk.Label(
            left_panel,
            text="Experiments",
            bg="#CFD9EA",
            fg="#0F2C52",
            font=("TkDefaultFont", 16, "bold"),
        ).grid(row=0, column=0, sticky="w", padx=14, pady=(12, 4))

        tk.Label(
            left_panel,
            text="How many experiment runs to enable (1–5):",
            bg="#CFD9EA",
            fg="#1D3557",
            font=("TkDefaultFont", 13, "bold"),
        ).grid(row=1, column=0, columnspan=2, sticky="w", padx=14, pady=(4, 2))
        run_count_var = tk.IntVar(value=5)
        count_slot = tk.Frame(left_panel, bg="#CFD9EA")
        count_slot.grid(row=2, column=0, columnspan=2, sticky="w", padx=14, pady=(0, 8))

        def _adjust_run_count(delta):
            try:
                current = int(run_count_var.get())
            except Exception:
                current = 1
            run_count_var.set(max(1, min(5, current + delta)))

        tk.Button(
            count_slot,
            text="-",
            command=lambda: _adjust_run_count(-1),
            width=3,
            height=2,
            bg="#D9E2F2",
            activebackground="#C8D6EE",
            font=("TkDefaultFont", 14, "bold"),
        ).pack(side=tk.LEFT, padx=(0, 6))
        tk.Entry(
            count_slot,
            textvariable=run_count_var,
            width=4,
            justify=tk.CENTER,
            state="readonly",
            font=("TkDefaultFont", 14, "bold"),
            readonlybackground="#FFFFFF",
        ).pack(side=tk.LEFT, ipady=10)
        tk.Button(
            count_slot,
            text="+",
            command=lambda: _adjust_run_count(1),
            width=3,
            height=2,
            bg="#D9E2F2",
            activebackground="#C8D6EE",
            font=("TkDefaultFont", 14, "bold"),
        ).pack(side=tk.LEFT, padx=(6, 0))

        tk.Label(
            left_panel,
            text="Set delay (hours from now) next to each run button.",
            bg="#CFD9EA",
            fg="#1D3557",
            font=("TkDefaultFont", 13, "bold"),
        ).grid(row=3, column=0, columnspan=2, sticky="w", padx=14, pady=(6, 1))
        tk.Label(
            left_panel,
            text="Minimum gap between consecutive run slots: 8 hours.",
            bg="#CFD9EA",
            fg="#3A5378",
            font=("TkDefaultFont", 12, "bold"),
        ).grid(row=4, column=0, columnspan=2, sticky="w", padx=14, pady=(0, 10))

        mid = tk.Frame(content, bg="#E9EEF7")
        mid.grid(row=0, column=1, sticky="nsew", padx=0, pady=0)
        mid.rowconfigure(0, weight=1)
        mid.columnconfigure(0, weight=1)

        canvas = tk.Canvas(mid, bg="#E9EEF7", highlightthickness=0)
        vsb = ttk.Scrollbar(mid, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        wrapper = ttk.Frame(canvas, padding=12, style="App.TFrame")
        win_id = canvas.create_window((0, 0), window=wrapper, anchor="nw")

        def _on_canvas_configure(event):
            canvas.itemconfigure(win_id, width=max(1, event.width - 4))

        def _on_wrapper_configure(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        canvas.bind("<Configure>", _on_canvas_configure)
        wrapper.bind("<Configure>", _on_wrapper_configure)

        for c in range(3):
            wrapper.columnconfigure(c, weight=1)

        tk.Label(
            wrapper,
            text="Configuration",
            background="#E9EEF7",
            foreground="#0F2C52",
            font=("TkDefaultFont", 18, "bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=6, pady=(0, 2))
        tk.Label(
            wrapper,
            text="Per-step hardware setup (touch a step to run it once)",
            background="#E9EEF7",
            foreground="#3A5378",
            font=("TkDefaultFont", 12, "bold"),
        ).grid(row=1, column=0, columnspan=3, sticky="w", padx=6, pady=(0, 10))

        def _close_popup():
            self._run_experiment_popup = None
            try:
                popup.attributes("-fullscreen", False)
            except Exception:
                pass
            popup.destroy()

        popup.protocol("WM_DELETE_WINDOW", _close_popup)

        def _parse_hours(txt, field_name):
            try:
                v = float(str(txt).strip())
            except Exception:
                messagebox.showerror("Invalid input", f"{field_name} must be a number (hours).")
                return None
            if v < 0:
                messagebox.showerror("Invalid input", f"{field_name} cannot be negative.")
                return None
            return v

        run_profiles = {i: [] for i in range(1, 6)}

        run_delay_vars = [
            tk.StringVar(value="0"),
            tk.StringVar(value="8"),
            tk.StringVar(value="16"),
            tk.StringVar(value="24"),
            tk.StringVar(value="32"),
        ]

        def _adjust_delay_slot(idx, delta_h):
            try:
                current = float(str(run_delay_vars[idx].get()).strip())
            except Exception:
                current = 0.0
            new_v = max(0.0, current + delta_h)
            # Keep integer-like values clean for touch use.
            run_delay_vars[idx].set(str(int(new_v)) if abs(new_v - int(new_v)) < 1e-6 else f"{new_v:.1f}")

        def _make_delay_slot(row_idx, var, top_pad=6):
            slot = tk.Frame(left_panel, bg="#CFD9EA")
            slot.grid(row=row_idx, column=1, sticky="e", padx=(4, 12), pady=(top_pad, 6))
            tk.Button(
                slot,
                text="-",
                command=lambda v=var: _adjust_delay_slot(run_delay_vars.index(v), -1.0),
                width=3,
                height=2,
                bg="#D9E2F2",
                activebackground="#C8D6EE",
                font=("TkDefaultFont", 14, "bold"),
            ).pack(side=tk.LEFT, padx=(0, 4))
            tk.Entry(
                slot,
                textvariable=var,
                width=5,
                justify=tk.CENTER,
                state="readonly",
                font=("TkDefaultFont", 14, "bold"),
                readonlybackground="#FFFFFF",
            ).pack(side=tk.LEFT, ipady=10)
            tk.Button(
                slot,
                text="+",
                command=lambda v=var: _adjust_delay_slot(run_delay_vars.index(v), 1.0),
                width=3,
                height=2,
                bg="#D9E2F2",
                activebackground="#C8D6EE",
                font=("TkDefaultFont", 14, "bold"),
            ).pack(side=tk.LEFT, padx=(4, 0))

        def _validate_run_slots(enabled_runs):
            delays_h = []
            for i in range(enabled_runs):
                hv = _parse_hours(run_delay_vars[i].get(), f"Run {i + 1} delay")
                if hv is None:
                    return None
                delays_h.append(hv)
            for i in range(1, enabled_runs):
                if delays_h[i] - delays_h[i - 1] < 8:
                    messagebox.showerror(
                        "Scheduling",
                        f"Run {i + 1} must be at least 8 hours after Run {i}.",
                    )
                    return None
            return delays_h

        def _schedule_ms_for_run(k, enabled_runs):
            delays_h = _validate_run_slots(enabled_runs)
            if delays_h is None:
                return None
            return int(delays_h[k - 1] * 3600 * 1000)

        def _open_run_profile_editor(run_id):
            prof_popup = tk.Toplevel(popup)
            self._apply_app_icon(prof_popup)
            prof_popup.title(f"Run {run_id} Profile Setup")
            prof_popup.geometry("1020x620")
            prof_popup.minsize(920, 560)
            prof_popup.transient(popup)

            frame = ttk.Frame(prof_popup, padding=12, style="App.TFrame")
            frame.pack(fill=tk.BOTH, expand=True)
            frame.columnconfigure(0, weight=1)
            frame.columnconfigure(1, weight=1)
            frame.columnconfigure(2, weight=1)
            ttk.Label(frame, text="Stage", style="Status.TLabel").grid(
                row=0, column=0, sticky="w", padx=6, pady=(4, 10)
            )
            ttk.Label(frame, text="Temperature (C)", style="Status.TLabel").grid(
                row=0, column=1, sticky="w", padx=6, pady=(4, 10)
            )
            ttk.Label(frame, text="Incubation time before picture (min)", style="Status.TLabel").grid(
                row=0, column=2, sticky="w", padx=6, pady=(4, 10)
            )

            temp_vars = []
            time_vars = []
            existing = run_profiles.get(run_id, [])

            def _spinbox(parent, var, step, min_v, max_v, precision):
                box = ttk.Frame(parent, style="App.TFrame")
                box.columnconfigure(1, weight=1)

                def _adjust(delta):
                    try:
                        value = float(var.get())
                    except Exception:
                        value = float(min_v)
                    value = max(float(min_v), min(float(max_v), value + delta))
                    var.set(f"{value:.{precision}f}" if precision > 0 else f"{int(round(value))}")

                minus_btn = tk.Button(
                    box,
                    text="-",
                    width=3,
                    bg="#D85151",
                    fg="white",
                    activebackground="#C44141",
                    font=("TkDefaultFont", 13, "bold"),
                    command=lambda: _adjust(-step),
                )
                minus_btn.grid(row=0, column=0, padx=(0, 6))

                value_lbl = tk.Label(
                    box,
                    textvariable=var,
                    width=8,
                    bg="#E8EEF8",
                    fg="#1B2F4A",
                    relief=tk.RIDGE,
                    bd=2,
                    font=("TkDefaultFont", 13, "bold"),
                )
                value_lbl.grid(row=0, column=1, sticky="ew")

                plus_btn = tk.Button(
                    box,
                    text="+",
                    width=3,
                    bg="#1C8E56",
                    fg="white",
                    activebackground="#187A4A",
                    font=("TkDefaultFont", 13, "bold"),
                    command=lambda: _adjust(step),
                )
                plus_btn.grid(row=0, column=2, padx=(6, 0))
                return box

            for i in range(5):
                stage_no = i + 1
                if i < len(existing):
                    t_default, m_default = existing[i]
                    t_var = tk.StringVar(value=f"{float(t_default):.1f}")
                    m_var = tk.StringVar(value=f"{int(round(float(m_default)))}")
                else:
                    t_var = tk.StringVar(value="37")
                    m_var = tk.StringVar(value="1" if i == 0 else "0")
                temp_vars.append(t_var)
                time_vars.append(m_var)

                ttk.Label(frame, text=f"Stage {stage_no}", style="Status.TLabel").grid(
                    row=stage_no, column=0, sticky="w", padx=6, pady=8
                )
                _spinbox(frame, t_var, step=0.5, min_v=10.0, max_v=50.0, precision=1).grid(
                    row=stage_no, column=1, sticky="w", padx=6, pady=8
                )
                _spinbox(frame, m_var, step=1, min_v=0, max_v=1440, precision=0).grid(
                    row=stage_no, column=2, sticky="w", padx=6, pady=8
                )

            def _save_profile():
                try:
                    profiles = []
                    for t_var, m_var in zip(temp_vars, time_vars):
                        temp = float(t_var.get().strip())
                        mins = float(m_var.get().strip())
                        if mins > 0:
                            profiles.append((temp, mins))
                except Exception:
                    messagebox.showerror(
                        "Input Error",
                        "Please enter valid numbers for temperatures and times.",
                    )
                    return

                run_profiles[run_id] = profiles
                prof_popup.destroy()

            ttk.Label(
                frame,
                text="Each stage runs incubation (temp + time), then takes pictures.",
                style="Status.TLabel",
            ).grid(row=6, column=0, columnspan=3, sticky="w", padx=6, pady=(6, 2))

            btn_save = _make_rounded_button(
                frame, "Save Profile", _save_profile, 260, 72, 24, (12, 158, 94), font_size=22, parent_bg="#E9EEF7"
            )
            btn_save.grid(row=7, column=1, sticky="ew", pady=(12, 4), padx=6)
            btn_cancel = _make_rounded_button(
                frame, "Cancel", prof_popup.destroy, 260, 72, 24, (212, 106, 9), font_size=22, parent_bg="#E9EEF7"
            )
            btn_cancel.grid(row=7, column=2, sticky="ew", pady=(12, 4), padx=6)

        def _tear_down_popup():
            try:
                popup.attributes("-fullscreen", False)
            except Exception:
                pass
            try:
                popup.destroy()
            except Exception:
                pass

        def _on_run_k(k):
            if self.is_busy:
                messagebox.showinfo("Busy", "Finish the current operation before scheduling a run.")
                return
            try:
                n = int(run_count_var.get())
            except (tk.TclError, ValueError):
                n = 5
            n = max(1, min(5, n))
            if k > n:
                messagebox.showinfo(
                    "Runs disabled",
                    f'Increase "How many experiment runs" to at least {k} to use this button.',
                )
                return
            ms = _schedule_ms_for_run(k, n)
            if ms is None:
                return
            # Safety: Run 1st Experiment always executes the full experiment sequence.
            selected_profile = [] if k == 1 else list(run_profiles.get(k, []))

            def _start_run_now(run_id, profile):
                if profile:
                    self.write_log(
                        f"Run {run_id}: using configured profile with {len(profile)} stage(s)."
                    )
                    self.set_busy(True, f"Running experiment {run_id} profile...")
                    self.root.after(
                        10,
                        lambda p=profile: self._run_incubate_and_picture_worker(p),
                    )
                else:
                    self.write_log(f"Run {run_id}: using default full experiment sequence.")
                    self.root.after(50, self.run_all_steps)

            if k == 1:
                _tear_down_popup()
                if ms <= 0:
                    _start_run_now(k, selected_profile)
                else:
                    self.write_log(f"Run 1st Experiment scheduled in {ms / 3600000.0:.2f} h.")
                    self.root.after(ms, lambda rid=k, p=selected_profile: _start_run_now(rid, p))
            else:
                _tear_down_popup()
                delay_h = ms / 3600000.0
                if ms <= 0:
                    _start_run_now(k, selected_profile)
                else:
                    self.write_log(f"Run {k} Experiment scheduled in {delay_h:.2f} h.")
                    self.root.after(
                        ms,
                        lambda rid=k, p=selected_profile: _start_run_now(rid, p),
                    )

        def _start_experiment_sequence():
            if self.is_busy:
                messagebox.showinfo("Busy", "Finish the current operation before starting sequence.")
                return
            try:
                n = int(run_count_var.get())
            except (tk.TclError, ValueError):
                n = 5
            n = max(1, min(5, n))

            delays_h = _validate_run_slots(n)
            if delays_h is None:
                return

            def _run_sequence_item(run_index):
                # Keep strict sequence by waiting for previous run to finish.
                if self.is_busy:
                    self.write_log(
                        f"Run {run_index} waiting: previous experiment still running."
                    )
                    self.root.after(60000, lambda ri=run_index: _run_sequence_item(ri))
                    return
                self.write_log(f"Starting Run {run_index} Experiment.")
                # Safety: Run 1st Experiment in sequence always uses full experiment flow.
                selected_profile = [] if run_index == 1 else list(run_profiles.get(run_index, []))
                if selected_profile:
                    self.write_log(
                        f"Run {run_index}: using configured profile with {len(selected_profile)} stage(s)."
                    )
                    self.set_busy(True, f"Running experiment {run_index} profile...")
                    self.root.after(
                        10,
                        lambda p=selected_profile: self._run_incubate_and_picture_worker(p),
                    )
                else:
                    self.write_log(f"Run {run_index}: using default full experiment sequence.")
                    self.root.after(50, self.run_all_steps)

            _tear_down_popup()
            for i in range(n):
                run_id = i + 1
                ms = int(delays_h[i] * 3600 * 1000)
                if ms <= 0:
                    self.write_log(f"Run {run_id} queued to start immediately.")
                else:
                    self.write_log(
                        f"Run {run_id} scheduled in {delays_h[i]:.2f} h."
                    )
                self.root.after(ms, lambda ri=run_id: _run_sequence_item(ri))

        section_row = 2
        step_btn_w = min(340, max(220, (sw - 120) // 3))
        step_btn_h = 70
        step_btn_radius = 18
        step_btn_font = 16
        popup_step_buttons = {}
        popup_step_completed = set()

        def _set_popup_step_button_visual(step_no, state_name):
            btn = popup_step_buttons.get(step_no)
            if btn is None:
                return
            img = getattr(btn, f"_img_{state_name}", None)
            if img is not None:
                btn.config(image=img)
                btn.image = img

        def _run_step_from_popup(step_no):
            if self.is_busy:
                return
            if step_no in popup_step_completed:
                ok = messagebox.askyesno(
                    "Confirm Step",
                    f"{self.step_labels[step_no - 1]} already completed once.\nRun this step again?",
                    parent=popup,
                )
                if not ok:
                    return

            btn = popup_step_buttons.get(step_no)
            if btn is not None:
                btn.config(state=tk.DISABLED)
            _set_popup_step_button_visual(step_no, "running")
            self.run_specific_step(step_no)

            def _poll_finish():
                try:
                    if not popup.winfo_exists():
                        return
                except Exception:
                    return
                if self.is_busy:
                    popup.after(250, _poll_finish)
                    return

                if self._last_step_success is True:
                    popup_step_completed.add(step_no)
                    _set_popup_step_button_visual(step_no, "done")
                else:
                    _set_popup_step_button_visual(step_no, "normal")
                if btn is not None:
                    btn.config(state=tk.NORMAL)

            popup.after(250, _poll_finish)

        def _make_manual_step_button(parent, label, step_no, base_color=(22, 98, 212)):
            btn = _make_rounded_button(
                parent,
                label,
                lambda n=step_no: _run_step_from_popup(n),
                width=step_btn_w,
                height=step_btn_h,
                radius=step_btn_radius,
                bg_rgb=base_color,
                font_size=step_btn_font,
                parent_bg="#E9EEF7",
            )
            btn._img_normal = _rounded_button_photo(
                step_btn_w, step_btn_h, step_btn_radius, base_color, label, font_size=step_btn_font
            )
            btn._img_running = _rounded_button_photo(
                step_btn_w, step_btn_h, step_btn_radius, (214, 133, 18), label, font_size=step_btn_font
            )
            btn._img_done = _rounded_button_photo(
                step_btn_w, step_btn_h, step_btn_radius, (24, 148, 86), label, font_size=step_btn_font
            )
            btn.config(image=btn._img_normal)
            btn.image = btn._img_normal
            popup_step_buttons[step_no] = btn
            return btn

        tk.Label(
            wrapper,
            text="Consumable Section",
            background="#E9EEF7",
            foreground="#0F2C52",
            font=("TkDefaultFont", 16, "bold"),
        ).grid(row=section_row, column=0, columnspan=3, sticky="w", padx=6, pady=(6, 4))
        section_row += 1

        consumable_steps = [2, 3]  # Change Media, Adjust Syringe
        for i, step_no in enumerate(consumable_steps):
            label = self.step_labels[step_no - 1]
            consumable_color = (212, 126, 18) if step_no == 2 else (146, 72, 198)
            btn = _make_manual_step_button(wrapper, label, step_no, base_color=consumable_color)
            btn.grid(row=section_row, column=i, sticky="ew", padx=6, pady=6)

        insert_media_var = tk.StringVar(value="")
        tk.Label(
            wrapper,
            textvariable=insert_media_var,
            background="#E9EEF7",
            foreground="#0E7A47",
            font=("TkDefaultFont", 15, "bold"),
        ).grid(row=section_row, column=2, sticky="w", padx=6, pady=6)

        def _refresh_insert_media_label():
            try:
                if not popup.winfo_exists():
                    return
            except Exception:
                return
            try:
                if media_dispensor_home_pressed():
                    insert_media_var.set("Insert Media")
                else:
                    insert_media_var.set("")
            except Exception:
                insert_media_var.set("")
            popup.after(500, _refresh_insert_media_label)

        _refresh_insert_media_label()
        section_row += 1

        tk.Label(
            wrapper,
            text="Run Experiment Manually Step by Step",
            background="#E9EEF7",
            foreground="#0F2C52",
            font=("TkDefaultFont", 16, "bold"),
        ).grid(row=section_row, column=0, columnspan=3, sticky="w", padx=6, pady=(10, 4))
        section_row += 1

        manual_steps = [1] + list(range(4, 15))  # Actual experiment sequence.
        for idx, step_no in enumerate(manual_steps):
            label = self.step_labels[step_no - 1]
            btn = _make_manual_step_button(wrapper, label, step_no, base_color=(22, 98, 212))
            r = section_row + idx // 3
            c = idx % 3
            btn.grid(row=r, column=c, sticky="ew", padx=6, pady=6)
        section_row += (len(manual_steps) + 2) // 3

        drain_btn = _make_rounded_button(
            wrapper,
            "Waste Solenoid 5 sec",
            self.run_waste_solenoid_pulse,
            width=step_btn_w,
            height=step_btn_h,
            radius=step_btn_radius,
            bg_rgb=(34, 124, 164),
            font_size=step_btn_font,
            parent_bg="#E9EEF7",
        )
        drain_btn.grid(row=section_row, column=0, sticky="ew", padx=6, pady=6)
        section_row += 1

        tk.Label(
            wrapper,
            text="Only Incubation plus Imager",
            background="#E9EEF7",
            foreground="#0F2C52",
            font=("TkDefaultFont", 16, "bold"),
        ).grid(row=section_row, column=0, columnspan=3, sticky="w", padx=6, pady=(10, 4))
        section_row += 1

        combo_btn = _make_rounded_button(
            wrapper,
            "Incubate + Pictures",
            self.run_incubate_and_picture_flow,
            width=min(980, sw - 90),
            height=78,
            radius=24,
            bg_rgb=(22, 98, 212),
            font_size=23,
            parent_bg="#E9EEF7",
        )
        combo_btn.grid(row=section_row, column=0, columnspan=3, sticky="ew", padx=6, pady=(6, 6))

        run_btn_h = 80
        run_radius = 20
        run_font = 18

        def _grid_run_button(btn, row_idx, top_pad=6):
            btn.grid(row=row_idx, column=0, sticky="ew", padx=12, pady=(top_pad, 6))

        full_btn = _make_rounded_button(
            left_panel,
            "Run 1st Experiment",
            lambda: _on_run_k(1),
            width=run_col_w,
            height=run_btn_h,
            radius=run_radius,
            bg_rgb=(12, 158, 94),
            font_size=run_font,
            parent_bg="#CFD9EA",
        )
        _grid_run_button(full_btn, 8, top_pad=10)
        _make_delay_slot(8, run_delay_vars[0], top_pad=10)
        profile_btn_1 = _make_rounded_button(
            left_panel,
            "Profile",
            lambda: _open_run_profile_editor(1),
            width=160,
            height=72,
            radius=22,
            bg_rgb=(92, 122, 201),
            font_size=16,
            parent_bg="#CFD9EA",
        )
        profile_btn_1.grid(row=8, column=2, columnspan=2, sticky="ew", padx=(6, 12), pady=(10, 6))

        run2 = _make_rounded_button(
            left_panel,
            "Run 2nd Experiment",
            lambda: _on_run_k(2),
            width=run_col_w,
            height=run_btn_h,
            radius=run_radius,
            bg_rgb=(12, 158, 94),
            font_size=run_font,
            parent_bg="#CFD9EA",
        )
        _grid_run_button(run2, 9)
        _make_delay_slot(9, run_delay_vars[1])
        profile_btn_2 = _make_rounded_button(
            left_panel,
            "Profile",
            lambda: _open_run_profile_editor(2),
            width=160,
            height=72,
            radius=22,
            bg_rgb=(92, 122, 201),
            font_size=16,
            parent_bg="#CFD9EA",
        )
        profile_btn_2.grid(row=9, column=2, columnspan=2, sticky="ew", padx=(6, 12), pady=6)

        run3 = _make_rounded_button(
            left_panel,
            "Run 3rd Experiment",
            lambda: _on_run_k(3),
            width=run_col_w,
            height=run_btn_h,
            radius=run_radius,
            bg_rgb=(12, 158, 94),
            font_size=run_font,
            parent_bg="#CFD9EA",
        )
        _grid_run_button(run3, 10)
        _make_delay_slot(10, run_delay_vars[2])
        profile_btn_3 = _make_rounded_button(
            left_panel,
            "Profile",
            lambda: _open_run_profile_editor(3),
            width=160,
            height=72,
            radius=22,
            bg_rgb=(92, 122, 201),
            font_size=16,
            parent_bg="#CFD9EA",
        )
        profile_btn_3.grid(row=10, column=2, columnspan=2, sticky="ew", padx=(6, 12), pady=6)

        run4 = _make_rounded_button(
            left_panel,
            "Run 4th Experiment",
            lambda: _on_run_k(4),
            width=run_col_w,
            height=run_btn_h,
            radius=run_radius,
            bg_rgb=(12, 158, 94),
            font_size=run_font,
            parent_bg="#CFD9EA",
        )
        _grid_run_button(run4, 11)
        _make_delay_slot(11, run_delay_vars[3])
        profile_btn_4 = _make_rounded_button(
            left_panel,
            "Profile",
            lambda: _open_run_profile_editor(4),
            width=160,
            height=72,
            radius=22,
            bg_rgb=(92, 122, 201),
            font_size=16,
            parent_bg="#CFD9EA",
        )
        profile_btn_4.grid(row=11, column=2, columnspan=2, sticky="ew", padx=(6, 12), pady=6)

        run5 = _make_rounded_button(
            left_panel,
            "Run 5th Experiment",
            lambda: _on_run_k(5),
            width=run_col_w,
            height=run_btn_h,
            radius=run_radius,
            bg_rgb=(12, 158, 94),
            font_size=run_font,
            parent_bg="#CFD9EA",
        )
        _grid_run_button(run5, 12)
        _make_delay_slot(12, run_delay_vars[4])
        profile_btn_5 = _make_rounded_button(
            left_panel,
            "Profile",
            lambda: _open_run_profile_editor(5),
            width=160,
            height=72,
            radius=22,
            bg_rgb=(92, 122, 201),
            font_size=16,
            parent_bg="#CFD9EA",
        )
        profile_btn_5.grid(row=12, column=2, columnspan=2, sticky="ew", padx=(6, 12), pady=6)

        start_sequence_btn = _make_rounded_button(
            left_panel,
            "Start Scheduled Sequence",
            _start_experiment_sequence,
            width=run_col_w,
            height=84,
            radius=24,
            bg_rgb=(22, 98, 212),
            font_size=19,
            parent_bg="#CFD9EA",
        )
        start_sequence_btn.grid(
            row=13, column=0, columnspan=2, sticky="ew", padx=12, pady=(10, 6)
        )

        left_panel.rowconfigure(14, weight=1)

        close_exp = _make_rounded_button(
            left_panel,
            "Close Panel",
            _close_popup,
            width=run_col_w,
            height=72,
            radius=26,
            bg_rgb=(194, 77, 0),
            font_size=22,
            parent_bg="#CFD9EA",
        )
        close_exp.grid(row=15, column=0, columnspan=2, sticky="ew", padx=12, pady=(10, 14))

        def _sync_run_buttons(*_args):
            try:
                n = int(run_count_var.get())
            except (tk.TclError, ValueError):
                n = 5
            n = max(1, min(5, n))
            for i, b in enumerate((full_btn, run2, run3, run4, run5), start=1):
                b.config(state=tk.NORMAL if i <= n else tk.DISABLED)

        run_count_var.trace_add("write", _sync_run_buttons)
        _sync_run_buttons()

        popup.bind("<Escape>", lambda _e: _close_popup())

    def run_specific_step(self, step_no):
        if self.is_busy:
            return
        if step_no < 1 or step_no > 15:
            return
        self._last_step_success = None
        self.set_busy(True, f"Running step {step_no}/15...")
        self.root.after(10, lambda: self._run_specific_step_worker(step_no))

    def run_incubate_and_picture_flow(self):
        if self.is_busy:
            return
        popup = tk.Toplevel(self.root)
        self._apply_app_icon(popup)
        popup.title("Incubation Profile Setup")
        popup.geometry("980x560")
        popup.minsize(900, 520)
        popup.transient(self.root)

        frame = ttk.Frame(popup, padding=12, style="App.TFrame")
        frame.pack(fill=tk.BOTH, expand=True)
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(2, weight=1)
        ttk.Label(frame, text="Stage", style="Status.TLabel").grid(row=0, column=0, sticky="w", padx=6, pady=(4, 10))
        ttk.Label(frame, text="Temperature (C)", style="Status.TLabel").grid(row=0, column=1, sticky="w", padx=6, pady=(4, 10))
        ttk.Label(frame, text="Time (min)", style="Status.TLabel").grid(row=0, column=2, sticky="w", padx=6, pady=(4, 10))

        temp_vars = []
        time_vars = []

        def _spinbox(parent, var, step, min_v, max_v, precision):
            box = ttk.Frame(parent, style="App.TFrame")
            box.columnconfigure(1, weight=1)

            def _adjust(delta):
                try:
                    value = float(var.get())
                except Exception:
                    value = float(min_v)
                value = max(float(min_v), min(float(max_v), value + delta))
                var.set(f"{value:.{precision}f}" if precision > 0 else f"{int(round(value))}")

            minus_btn = tk.Button(
                box,
                text="-",
                width=3,
                bg="#D85151",
                fg="white",
                activebackground="#C44141",
                font=("TkDefaultFont", 13, "bold"),
                command=lambda: _adjust(-step),
            )
            minus_btn.grid(row=0, column=0, padx=(0, 6))

            value_lbl = tk.Label(
                box,
                textvariable=var,
                width=7,
                bg="#E8EEF8",
                fg="#1B2F4A",
                relief=tk.RIDGE,
                bd=2,
                font=("TkDefaultFont", 13, "bold"),
            )
            value_lbl.grid(row=0, column=1, sticky="ew")

            plus_btn = tk.Button(
                box,
                text="+",
                width=3,
                bg="#1C8E56",
                fg="white",
                activebackground="#187A4A",
                font=("TkDefaultFont", 13, "bold"),
                command=lambda: _adjust(step),
            )
            plus_btn.grid(row=0, column=2, padx=(6, 0))
            return box

        for i in range(5):
            stage_no = i + 1
            t_var = tk.StringVar(value="37")
            m_var = tk.StringVar(value="1" if i == 0 else "0")
            temp_vars.append(t_var)
            time_vars.append(m_var)

            ttk.Label(frame, text=f"Stage {stage_no}", style="Status.TLabel").grid(
                row=stage_no, column=0, sticky="w", padx=6, pady=8
            )
            _spinbox(frame, t_var, step=0.5, min_v=10.0, max_v=50.0, precision=1).grid(
                row=stage_no, column=1, sticky="w", padx=6, pady=8
            )
            _spinbox(frame, m_var, step=1, min_v=0, max_v=1440, precision=0).grid(
                row=stage_no, column=2, sticky="w", padx=6, pady=8
            )

        def _start_flow():
            try:
                profiles = []
                for t_var, m_var in zip(temp_vars, time_vars):
                    temp = float(t_var.get().strip())
                    mins = float(m_var.get().strip())
                    if mins > 0:
                        profiles.append((temp, mins))
            except Exception:
                messagebox.showerror("Input Error", "Please enter valid numbers for temperatures and times.")
                return
            if not profiles:
                messagebox.showerror("Input Error", "Set at least one round with time > 0.")
                return

            popup.destroy()
            self.set_busy(True, "Running incubation profile + picture capture...")
            self.root.after(10, lambda: self._run_incubate_and_picture_worker(profiles))

        btn_start = _make_rounded_button(
            frame, "Start", _start_flow, 260, 72, 24, (12, 158, 94), font_size=24, parent_bg="#E9EEF7"
        )
        btn_start.grid(row=6, column=1, sticky="ew", pady=(16, 4), padx=6)
        btn_cancel = _make_rounded_button(
            frame, "Cancel", popup.destroy, 260, 72, 24, (212, 106, 9), font_size=24, parent_bg="#E9EEF7"
        )
        btn_cancel.grid(row=6, column=2, sticky="ew", pady=(16, 4), padx=6)

    def _run_incubate_and_picture_worker(self, profiles):
        try:
            self.write_log("Running combined flow: Shift -> Incubate -> Picture")
            exp_dir = self._create_next_experiment_dir(".")
            self.write_log(f"Experiment image root: {exp_dir}")
            for idx, (target_temp, minutes) in enumerate(profiles, start=1):
                self.write_log(f"Stage {idx}: shift to incubation region")
                self.step_11()
                self.write_log(f"Stage {idx}: incubate at {target_temp:.1f}C for {minutes:.2f} min")
                self._run_incubation(target_temp, minutes, stage_name=f"Stage {idx}")
                self.write_log(f"Stage {idx}: incubation complete, starting pictures")
                stage_folder = self._stage_capture_folder_name(target_temp, minutes)
                self.step_13(experiment_dir=exp_dir, stage_subdir=stage_folder)
            self.write_log("Final: returning incubator and stage home")
            incubator_lid_home()
            petri_dishes_home()
            self.write_log("Combined flow complete")
            self.root.after(0, lambda: self.set_busy(False, "Ready. Combined incubation+pictures completed."))
        except Exception as exc:
            self.write_log(f"ERROR: {exc}")
            self.root.after(0, lambda: self.set_busy(False, "Error occurred in combined flow."))

    def _run_specific_step_worker(self, step_no):
        try:
            self.ensure_initialized()
            step_fn = self.steps[int(step_no) - 1]
            step_fn()
            self._last_step_success = True
            self.write_log(f"Step {step_no} complete")
            self.root.after(0, lambda: self.set_busy(False, f"Ready. Step {step_no} completed."))
        except Exception as exc:
            self._last_step_success = False
            self.write_log(f"ERROR: {exc}")
            self.root.after(0, lambda: self.set_busy(False, "Error occurred. Check log."))

    def run_waste_solenoid_pulse(self):
        if self.is_busy:
            return
        self._last_step_success = None
        self.set_busy(True, "Running waste solenoid for 5 seconds...")
        self.root.after(10, self._run_waste_solenoid_pulse_worker)

    def _run_waste_solenoid_pulse_worker(self):
        try:
            self.write_log("Waste solenoid: ON for 5 seconds")
            solinoid_waste_on()
            time.sleep(5)
            solinoid_waste_off()
            self._last_step_success = True
            self.write_log("Waste solenoid: OFF")
            self.root.after(0, lambda: self.set_busy(False, "Ready. Waste solenoid pulse completed."))
        except Exception as exc:
            self._last_step_success = False
            try:
                solinoid_waste_off()
            except Exception:
                pass
            self.write_log(f"ERROR: {exc}")
            self.root.after(0, lambda: self.set_busy(False, "Error occurred during waste solenoid pulse."))

    def _create_next_experiment_dir(self, output_root="."):
        os.makedirs(output_root, exist_ok=True)
        idx = 1
        while True:
            path = os.path.join(output_root, f"exp_{idx:02d}")
            if not os.path.exists(path):
                os.makedirs(path, exist_ok=False)
                return path
            idx += 1

    def _stage_capture_folder_name(self, target_temp, minutes):
        hours = float(minutes) / 60.0
        temp = float(target_temp)
        if abs(hours - round(hours)) < 1e-6:
            h_txt = str(int(round(hours)))
        else:
            h_txt = f"{hours:.1f}".rstrip("0").rstrip(".")
        if abs(temp - round(temp)) < 1e-6:
            t_txt = str(int(round(temp)))
        else:
            t_txt = f"{temp:.1f}".rstrip("0").rstrip(".")
        safe_h = h_txt.replace(".", "p")
        safe_t = t_txt.replace(".", "p")
        return f"{safe_h}hours{safe_t}degree"

    def run_all_steps(self):
        if self.is_busy:
            return
        total = len(self.full_experiment_sequence)
        self.set_busy(True, f"Running full experiment ({total} steps)...")
        self.root.after(10, self._run_all_worker)

    def _run_all_worker(self):
        try:
            self.ensure_initialized()
            total = len(self.full_experiment_sequence)
            for run_idx, step_no in enumerate(self.full_experiment_sequence, start=1):
                step_label = self.step_labels[step_no - 1]
                self.status_var.set(f"Running {run_idx}/{total}: {step_label}")
                self.write_log(f"Running {run_idx}/{total}: {step_label} (Step {step_no})")
                self.steps[step_no - 1]()
                self.write_log(f"Completed {run_idx}/{total}: {step_label} (Step {step_no})")
                if run_idx < total:
                    time.sleep(1)  # Required delay between steps
            self.root.after(
                0,
                lambda: self.set_busy(
                    False, f"Ready. Full experiment completed ({total}/{total})."
                ),
            )
        except Exception as exc:
            self.write_log(f"ERROR: {exc}")
            self.root.after(0, lambda: self.set_busy(False, "Error occurred during full run."))

    def open_camera_test(self):
        if self.is_busy or self._camera_test_active:
            return
        if self._camera_test_done_once:
            self._ask_camera_retest_confirmation()
            return
        self._start_camera_test_launch()

    def _ask_camera_retest_confirmation(self):
        popup = tk.Toplevel(self.root)
        self._apply_app_icon(popup)
        popup.title("Confirm Camera Test")
        popup.geometry("520x220")
        popup.minsize(500, 200)
        popup.transient(self.root)
        popup.grab_set()

        frame = ttk.Frame(popup, padding=14, style="Card.TFrame")
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(
            frame,
            text="Do you want to test camera again?",
            style="CardTitle.TLabel",
        ).pack(anchor="w", pady=(4, 14))

        row = ttk.Frame(frame, style="Card.TFrame")
        row.pack(fill=tk.X, pady=(6, 0))
        row.columnconfigure(0, weight=1)
        row.columnconfigure(1, weight=1)

        def _yes():
            popup.destroy()
            self._start_camera_test_launch()

        btn_yes = _make_rounded_button(
            row, "Yes", _yes, 220, 68, 22, (12, 158, 94), font_size=22, parent_bg="#F7FAFF"
        )
        btn_yes.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        btn_no = _make_rounded_button(
            row, "No", popup.destroy, 220, 68, 22, (212, 106, 9), font_size=22, parent_bg="#F7FAFF"
        )
        btn_no.grid(row=0, column=1, sticky="ew", padx=(8, 0))

    def _show_camera_loading_popup(self):
        popup = tk.Toplevel(self.root)
        self._apply_app_icon(popup)
        popup.title("Loading Camera")
        popup.geometry("520x220")
        popup.minsize(500, 200)
        popup.transient(self.root)
        popup.grab_set()

        frame = tk.Frame(popup, bg="#F7FAFF")
        frame.pack(fill=tk.BOTH, expand=True, padx=14, pady=14)
        tk.Label(
            frame,
            text="Switching on camera",
            bg="#F7FAFF",
            fg="#1D3557",
            font=("TkDefaultFont", 16, "bold"),
        ).pack(anchor="w", pady=(2, 0))
        tk.Label(
            frame,
            text="and loading stream...",
            bg="#F7FAFF",
            fg="#1D3557",
            font=("TkDefaultFont", 16, "bold"),
        ).pack(anchor="w", pady=(0, 10))
        bar = ttk.Progressbar(frame, mode="indeterminate", length=420)
        bar.pack(fill=tk.X, pady=(6, 2))
        bar.start(14)
        tk.Label(
            frame,
            text="Please wait...",
            bg="#F7FAFF",
            fg="#173C6A",
            font=("TkDefaultFont", 14, "bold"),
        ).pack(anchor="w", pady=(8, 0))
        self._camera_loading_popup = popup

    def _show_camera_closing_popup(self):
        if self._camera_closing_popup is not None:
            return
        popup = tk.Toplevel(self.root)
        self._apply_app_icon(popup)
        popup.title("Closing Camera")
        popup.geometry("520x200")
        popup.minsize(480, 180)
        popup.transient(self.root)
        popup.grab_set()

        frame = tk.Frame(popup, bg="#F7FAFF")
        frame.pack(fill=tk.BOTH, expand=True, padx=14, pady=14)
        tk.Label(
            frame,
            text="Switching off camera",
            bg="#F7FAFF",
            fg="#1D3557",
            font=("TkDefaultFont", 16, "bold"),
        ).pack(anchor="w", pady=(2, 0))
        tk.Label(
            frame,
            text="via relay (about 3 seconds)...",
            bg="#F7FAFF",
            fg="#1D3557",
            font=("TkDefaultFont", 16, "bold"),
        ).pack(anchor="w", pady=(0, 10))
        bar = ttk.Progressbar(frame, mode="indeterminate", length=420)
        bar.pack(fill=tk.X, pady=(6, 2))
        bar.start(14)
        tk.Label(
            frame,
            text="Please wait...",
            bg="#F7FAFF",
            fg="#173C6A",
            font=("TkDefaultFont", 14, "bold"),
        ).pack(anchor="w", pady=(8, 0))
        self._camera_closing_popup = popup

    def _hide_camera_closing_popup(self):
        if self._camera_closing_popup is None:
            return
        try:
            self._camera_closing_popup.grab_release()
        except Exception:
            pass
        try:
            self._camera_closing_popup.destroy()
        except Exception:
            pass
        self._camera_closing_popup = None

    def _start_camera_test_launch(self):
        self._camera_test_active = True
        self.btn_camera.config(state=tk.DISABLED)
        self._show_camera_loading_popup()
        worker = threading.Thread(target=self._camera_open_worker, daemon=True)
        worker.start()

    def _camera_open_worker(self):
        cap = open_usb_camera_with_recovery(
            device_index=0,
            direct_tries=3,
            retry_wait_s=1.0,
            post_relay_wait_s=4.0,
            post_relay_tries=6,
        )
        self.root.after(0, lambda: self._finish_camera_open(cap))

    def _finish_camera_open(self, cap):
        try:
            if self._camera_loading_popup is not None:
                try:
                    self._camera_loading_popup.grab_release()
                except Exception:
                    pass
                self._camera_loading_popup.destroy()
                self._camera_loading_popup = None
        except Exception:
            pass

        if cap is None:
            self.write_log("Camera error: could not open stream after recovery retries.")
            messagebox.showerror("Camera", "Error in loading camera. See the console.")
            self._camera_test_active = False
            self.btn_camera.config(state=tk.NORMAL)
            return

        CameraTestWindow(self.root, cap=cap, on_close=self._on_camera_test_closed, app=self)

    def _on_camera_test_closed(self):
        self._camera_test_active = False
        self._camera_test_done_once = True
        self.btn_camera.config(state=tk.NORMAL)

    def open_take_images(self):
        if self.is_busy or self._camera_test_active:
            return
        self.set_busy(True, "Running image capture module...")
        worker = threading.Thread(target=self._take_images_worker, daemon=True)
        worker.start()

    def _take_images_worker(self):
        try:
            self.write_log("Take Images: preparing imaging sequence")
            self.step_13()
            self.root.after(0, lambda: self.set_busy(False, "Ready. Image capture completed."))
        except Exception as exc:
            self.write_log(f"Take Images ERROR: {exc}")
            self.root.after(0, lambda: self.set_busy(False, "Error occurred in Take Images module."))

    # ---------- 15 experiment steps ----------
    def step_1(self):
        self.write_log("Step 1: All Module Home")
        incubator_lid_home()
        suction_pipe_home()
        filteration_unit_config()
        filteration_flask_config()
        petri_dishes_home()
        petri_dishes_down(1035)
        suction_pump_home()
        suction_pump_up(400)

    def step_2(self):
        self.write_log("Step 2: Change media")
        Media_dispensor_home()
        Media_dispensor_up(3500)

    def step_3(self):
        self.write_log("Step 3: Adjust syringe position")
        Media_dispensor_down(800)

    def step_4(self):
        self.write_log("Step 4: Bring petri dishes home")
        incubator_lid_home()
        petri_dishes_home()
        petri_dishes_down(1035)

    def step_5(self):
        self.write_log("Step 5: Put filter paper on filtration flask")
        suction_pipe_home()
        suction_pump_home()
        filteration_unit_config()
        filteration_flask_config()
        Filteration_flask_up(1140)
        suction_pipe_up(900)
        upper_suction_pump_on(22)
        time.sleep(2)
        suction_pipe_down(600)
        time.sleep(1)
        suction_pipe_home()
        suction_pump_up(1245)
        filteration_suction_pump_on(100)
        upper_suction_pump_off()
        suction_pipe_up(400)
        time.sleep(2)
        suction_pipe_home()

    def step_6(self):
        self.write_log("Step 6: Send filter paper to assembly")
        filteration_unit_config()
        filteration_flask_config()
        Filteration_flask_up(10)
        Filteration_unit_up(850)
        filteration_suction_pump_off()
        time.sleep(1)
        solinoid_value_to_filteration()
        filteration_suction_pump_on(90)
        time.sleep(20)

        retries = 0
        while water_level_reached():
            retries += 1
            filteration_suction_pump_off()
            self.write_log("Water level still FULL, retrying filtration pump cycle")
            if retries >= 5:
                raise RuntimeError("Water level still FULL after 5 retries in step 6")
            filteration_suction_pump_on(90)
            time.sleep(20)
        filteration_suction_pump_off()

    def step_7(self):
        self.write_log("Step 7: Pick up media pad and petri dishes")
        suction_pump_home()
        suction_pipe_home()
        suction_pipe_up(1025)
        upper_suction_pump_on(100)
        time.sleep(2)
        suction_pipe_down(1025)
        suction_pump_up(3065)
        suction_pipe_up(300)
        upper_suction_pump_off()
        time.sleep(5)

    def step_8(self):
        self.write_log("Step 8: Pouring media")
        petri_dishes_home()
        petri_dishes_down(300)
        Media_dispensor_down(800)
        time.sleep(2)
        petri_dishes_down(725)

    def step_9(self):
        self.write_log("Step 9: Pick up filtration unit")
        filteration_unit_config()
        filteration_flask_config()
        Filteration_flask_up(1130)

    def step_10(self):
        self.write_log("Step 10: Pick filter paper from filtration flask")
        suction_pipe_home()
        suction_pump_home()
        suction_pump_up(1265)
        suction_pipe_up(670)
        upper_suction_pump_on(30)
        time.sleep(3)
        suction_pipe_down(670)
        suction_pump_up(1805)
        suction_pipe_up(710)
        upper_suction_pump_off()
        time.sleep(3)
        suction_pipe_home()

    def step_11(self):
        self.write_log("Step 11: Shift for incubation")
        incubator_lid_home()
        petri_dishes_home()
        petri_dishes_down(3280)
        incubator_lid_up(200)

    def step_12(self):
        self.write_log("Step 12: Start incubation")
        run_relay(P1, 1)
        self._run_incubation(37, 1, stage_name="Step 12")

    def _read_ds18b20_c(self, sensor_glob="/sys/bus/w1/devices/28-*/w1_slave"):
        paths = glob.glob(sensor_glob)
        if not paths:
            raise RuntimeError("DS18B20 sensor not found")
        with open(paths[0], "r", encoding="utf-8") as f:
            lines = f.read().strip().splitlines()
        if len(lines) < 2 or not lines[0].strip().endswith("YES"):
            raise RuntimeError("DS18B20 CRC invalid")
        marker = "t="
        if marker not in lines[1]:
            raise RuntimeError("DS18B20 data missing")
        return int(lines[1].split(marker, 1)[1]) / 1000.0

    def _draw_pie(self, canvas, center_x, center_y, radius, frac, color, bg):
        canvas.create_oval(
            center_x - radius,
            center_y - radius,
            center_x + radius,
            center_y + radius,
            fill=bg,
            outline="",
        )
        canvas.create_arc(
            center_x - radius,
            center_y - radius,
            center_x + radius,
            center_y + radius,
            start=90,
            extent=-360.0 * max(0.0, min(1.0, float(frac))),
            fill=color,
            outline="",
        )

    def _run_incubation(self, target_temp, minutes, stage_name="Incubation"):
        target_temp = float(target_temp)
        duration_s = max(0.0, float(minutes) * 60.0)
        lower = target_temp - 0.3
        upper = target_temp + 0.3
        poll_seconds = 1.0

        parent_win = self.root
        try:
            if self._run_experiment_popup is not None and self._run_experiment_popup.winfo_exists():
                parent_win = self._run_experiment_popup
        except Exception:
            parent_win = self.root

        win = tk.Toplevel(parent_win)
        self._apply_app_icon(win)
        win.title(f"{stage_name} Monitor")
        win.geometry("900x520")
        win.minsize(860, 480)
        win.transient(parent_win)

        root_frame = ttk.Frame(win, padding=10, style="App.TFrame")
        root_frame.pack(fill=tk.BOTH, expand=True)
        root_frame.columnconfigure(0, weight=1)
        root_frame.columnconfigure(1, weight=1)

        stage_var = tk.StringVar(value=f"{stage_name} incubation")
        temp_var = tk.StringVar(value="--.- C")
        rem_var = tk.StringVar(value="--:--:--")
        target_var = tk.StringVar(value=f"Target {target_temp:.1f} C")

        ttk.Label(root_frame, textvariable=stage_var, style="Title.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 8)
        )
        ttk.Label(root_frame, textvariable=target_var, style="Status.TLabel").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(0, 8)
        )

        temp_canvas = tk.Canvas(root_frame, width=360, height=320, bg="#F3F6FB", highlightthickness=0)
        time_canvas = tk.Canvas(root_frame, width=360, height=320, bg="#F3F6FB", highlightthickness=0)
        temp_canvas.grid(row=2, column=0, padx=6, pady=6, sticky="nsew")
        time_canvas.grid(row=2, column=1, padx=6, pady=6, sticky="nsew")

        temp_label = ttk.Label(root_frame, textvariable=temp_var, style="Status.TLabel")
        rem_label = ttk.Label(root_frame, textvariable=rem_var, style="Status.TLabel")
        temp_label.grid(row=3, column=0, pady=(2, 8))
        rem_label.grid(row=3, column=1, pady=(2, 8))

        self._incubation_stop_requested = False

        def _request_stop():
            should_stop = messagebox.askyesno(
                "Confirm Stop",
                f"Stop {stage_name} now?\nThis will cancel the current incubation stage.",
                parent=win,
            )
            if should_stop:
                self._incubation_stop_requested = True

        stop_btn = _make_rounded_button(
            root_frame, "Stop", _request_stop, 760, 82, 28, (212, 106, 9), font_size=30, parent_bg="#F3F6FB"
        )
        stop_btn.grid(row=4, column=0, columnspan=2, sticky="ew", padx=8, pady=(4, 0))

        start = time.time()
        heater_on = False
        last_temp = None
        try:
            while True:
                elapsed = time.time() - start
                if elapsed >= duration_s:
                    break
                if self._incubation_stop_requested:
                    raise RuntimeError(f"{stage_name} stopped by user")

                temp_c = self._read_ds18b20_c()
                last_temp = temp_c
                if temp_c <= lower and not heater_on:
                    set_relay(P1, True)
                    heater_on = True
                elif temp_c >= upper and heater_on:
                    set_relay(P1, False)
                    heater_on = False

                remain = max(0.0, duration_s - elapsed)
                h = int(remain // 3600)
                m = int((remain % 3600) // 60)
                s = int(remain % 60)
                rem_var.set(f"{h:02d}:{m:02d}:{s:02d}")
                temp_var.set(f"{temp_c:.2f} C")

                temp_frac = (temp_c - 10.0) / 40.0
                time_frac = remain / duration_s if duration_s > 0 else 0.0

                temp_canvas.delete("all")
                time_canvas.delete("all")
                self._draw_pie(temp_canvas, 180, 160, 120, temp_frac, "#0C9E5E", "#DCE7F8")
                self._draw_pie(time_canvas, 180, 160, 120, time_frac, "#1662D4", "#DCE7F8")
                temp_canvas.create_text(180, 160, text="Temp", fill="#10253F", font=("TkDefaultFont", 16, "bold"))
                time_canvas.create_text(180, 160, text="Time Left", fill="#10253F", font=("TkDefaultFont", 16, "bold"))
                temp_canvas.create_text(180, 280, text=f"{temp_c:.1f} / 50.0 C", fill="#10253F", font=("TkDefaultFont", 12))
                time_canvas.create_text(180, 280, text=rem_var.get(), fill="#10253F", font=("TkDefaultFont", 12))

                win.update_idletasks()
                win.update()
                time.sleep(poll_seconds)

            self.write_log(f"{stage_name}: completed at {last_temp:.2f}C" if last_temp is not None else f"{stage_name}: completed")
        finally:
            try:
                set_relay(P1, False)
            except Exception:
                pass
            try:
                win.destroy()
            except Exception:
                pass

    def _detect_camera_index(self, candidates=(0, 1, 2, 3)):
        """Return first currently openable USB camera index, else None."""
        for idx in candidates:
            cap = open_usb_camera(idx)
            if cap is None:
                continue
            try:
                ok, frame = cap.read()
                if ok and frame is not None:
                    return int(idx)
            finally:
                try:
                    cap.release()
                except Exception:
                    pass
        return None

    def step_13(self, experiment_dir=None, stage_subdir=None):
        self.write_log("Step 13: Start pictures")
        cam_idx = self._detect_camera_index()
        if cam_idx is None:
            # Recovery with relay on primary index, then probe again.
            cap = open_usb_camera_with_recovery(
                device_index=0,
                direct_tries=3,
                retry_wait_s=1.0,
                post_relay_wait_s=4.0,
                post_relay_tries=6,
            )
            if cap is not None:
                cam_idx = 0
                cap.release()
            else:
                cam_idx = self._detect_camera_index()
        if cam_idx is None:
            raise RuntimeError("Camera not available for imaging")
        self.write_log(f"Imaging camera index selected: /dev/video{cam_idx}")
        # Let camera stream stabilize before imaging sequence.
        time.sleep(3)

        Camera_home()
        Camera_down(2430)
        incubator_lid_home()
        petri_dishes_home()
        petri_dishes_down(3290)
        petri_dishes_up(330)
        imaging_ok = False
        imaging_errors = []
        for try_no in range(1, 4):
            try:
                start_imaging_capture_pattern(
                    camera_device_index=cam_idx,
                    experiment_dir=experiment_dir,
                    stage_subdir=stage_subdir,
                )
                imaging_ok = True
                break
            except Exception as exc:
                imaging_errors.append(str(exc))
                self.write_log(f"Imaging attempt {try_no}/3 failed: {exc}")
                # Device index can change after reconnect; probe before retry.
                new_idx = self._detect_camera_index()
                if new_idx is not None and new_idx != cam_idx:
                    cam_idx = new_idx
                    self.write_log(f"Switched imaging camera index to /dev/video{cam_idx}")
                time.sleep(2)
        if not imaging_ok:
            raise RuntimeError(f"Imaging failed after retries: {imaging_errors[-1]}")
        time.sleep(0.5)
        petri_dishes_home()
        petri_dishes_down(3290)
        incubator_lid_up(200)
        pulse_camera_relay(3)
        time.sleep(3)

    def step_14(self):
        self.write_log("Step 14: Put in trash")
        incubator_lid_home()
        petri_dishes_home()
        petri_dishes_down(1025)
        suction_pipe_home()
        suction_pump_home()
        suction_pump_up(3055)
        suction_pipe_up(1010)
        upper_suction_pump_on(100)
        time.sleep(2)
        suction_pipe_home()
        suction_pump_down(930)
        upper_suction_pump_off()
        suction_pipe_up(800)
        for _ in range(20):
            suction_pump_up(120)
            suction_pump_down(120)
            time.sleep(0.01)
        time.sleep(2)

    def step_15(self):
        self.write_log("Step 15: Sterilize (placeholder)")

    def on_exit(self):
        shutdown_all()
        self.root.destroy()


def main():
    root = tk.Tk()
    ExperimentApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
