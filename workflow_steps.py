"""
Six-step automation workflow — callable from CLI (main.py) or procedure_gui.py.
"""

import os
import time

from device_config import (
    CAMERA_DISH_PRE_UP,
    CAMERA_DISH_PRE_UP_ROW2,
    CAMERA_STEPSIZE,
    DEFAULT_INCUBATION_COUNT,
    DEFAULT_INCUBATION_MINUTES,
    DEFAULT_INCUBATION_TEMP_C,
    IMAGING_COLS,
    IMAGING_ROWS,
    MAX_PETRI_DISHES,
    PETRI_DISH_PRE_UP,
    PETRI_DISH_PRE_UP_ROW2,
    PETRI_STEPSIZE,
    PETRI_TRAY_COLS,
)
from camera_module import Camera_home, Camera_up
from incubator_lid import incubator_lid_down, incubator_lid_home
from incubation_module import Start_incubation
from imaging import _next_exp_dir, data_root, start_multi_petri_imaging
from petri_dishes import petri_dishes_home, petri_dishes_up


def step_01_all_home():
    """Step 1: All modules home."""
    Camera_home()
    incubator_lid_home()
    petri_dishes_home()
    petri_dishes_up(2400)
    incubator_lid_down(300)


def step_02_insert_petri_dishes():
    """Step 2: Insert petri dishes (lid up, petri home)."""
    incubator_lid_home()
    petri_dishes_home()


def step_03_shift_for_incubation():
    """Step 3: Shift stage for incubation region."""
    incubator_lid_home()
    petri_dishes_home()
    petri_dishes_up(2400)
    incubator_lid_down(400)


def step_04_incubation(
    target_c=DEFAULT_INCUBATION_TEMP_C,
    minutes=DEFAULT_INCUBATION_MINUTES,
    count=DEFAULT_INCUBATION_COUNT,
    on_tick=None,
):
    """Step 4: Run incubation cycle(s) at target temperature."""
    n = max(1, int(count))
    for i in range(1, n + 1):
        print(f"[Step 4] Incubation {i}/{n}: {target_c}°C for {minutes} min")
        Start_incubation(float(target_c), float(minutes), on_tick=on_tick)


def step_05_prepare_imaging():
    """Step 5a: Move to imaging start (before camera / capture)."""
    incubator_lid_home()
    petri_dishes_home()
    petri_dishes_up(PETRI_DISH_PRE_UP)
    Camera_home()
    Camera_up(CAMERA_DISH_PRE_UP)


def step_05_post_imaging_cleanup():
    """Step 5b: Park after imaging."""
    incubator_lid_home()
    petri_dishes_home()
    petri_dishes_up(2400)
    incubator_lid_down(300)


def step_06_sterilize():
    """Step 6: Return incubator and petri to home."""
    incubator_lid_home()
    petri_dishes_home()


def capture_petri_dishes(
    num_petri_dishes,
    experiment_dir=None,
    time_point_subdir=None,
):
    """
    Power on camera if needed, run multi-petri capture, power off camera.

    Returns experiment directory path used for captures.
    """
    from main import ensure_usb_camera_ready, power_off_usb_camera

    num = max(1, min(MAX_PETRI_DISHES, int(num_petri_dishes)))
    if experiment_dir is None:
        experiment_dir = _next_exp_dir(data_root())
    capture_root = experiment_dir
    if time_point_subdir:
        capture_root = os.path.join(experiment_dir, str(time_point_subdir))
        os.makedirs(capture_root, exist_ok=True)

    ready, _relay_used = ensure_usb_camera_ready(device_index=0)
    if not ready:
        raise RuntimeError("USB camera not available")

    try:
        start_multi_petri_imaging(
            num_petri_dishes=num,
            experiment_dir=capture_root,
            tray_cols=PETRI_TRAY_COLS,
            petri_pre_up_row2=PETRI_DISH_PRE_UP_ROW2,
            camera_pre_up_row2=CAMERA_DISH_PRE_UP_ROW2,
            petri_offset_per_dish=PETRI_STEPSIZE * 7,
            camera_offset_per_dish=CAMERA_STEPSIZE,
            rows=IMAGING_ROWS,
            cols=IMAGING_COLS,
            camera_step_per_col=CAMERA_STEPSIZE,
            petri_step_per_row=PETRI_STEPSIZE,
        )
    finally:
        power_off_usb_camera()

    return experiment_dir


def run_timed_picture_study(
    num_petri_dishes,
    num_rounds,
    interval_minutes,
    target_c=DEFAULT_INCUBATION_TEMP_C,
    on_tick=None,
    on_log=None,
):
    """
    Incubate for each interval, then capture all petri dishes.

    Folders: ``data/exp_XX/03min/``, ``data/exp_XX/06min/`` (cumulative minutes).

    ``interval_minutes``: length-6 list of minutes per round (first ``num_rounds`` used).

    Returns parent experiment directory.
    """
    num_rounds = max(1, min(6, int(num_rounds)))
    intervals = list(interval_minutes)[:6]
    while len(intervals) < 6:
        intervals.append(intervals[-1] if intervals else 3)

    exp_dir = _next_exp_dir(data_root())
    cumulative = 0.0

    def _log(msg):
        print(msg)
        if on_log:
            on_log(msg)

    for rnd in range(1, num_rounds + 1):
        mins = float(intervals[rnd - 1])
        cumulative += mins
        label = f"{int(round(cumulative)):02d}min"
        _log(f"Round {rnd}/{num_rounds}: incubate {mins:g} min → capture → {label}/")

        Start_incubation(float(target_c), mins, on_tick=on_tick)

        step_05_prepare_imaging()
        capture_petri_dishes(
            num_petri_dishes,
            experiment_dir=exp_dir,
            time_point_subdir=label,
        )

    step_05_post_imaging_cleanup()
    _log(f"Timed study complete: {exp_dir}")
    return exp_dir
