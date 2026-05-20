"""
Six-step automation workflow — callable from CLI (main.py) or procedure_gui.py.
"""

import os
import time

from device_config import (
    CAMERA_DISH_PRE_UP,
    CAMERA_DISH_PRE_UP_ROW2,
    CAMERA_STEPSIZE,
    DEFAULT_INCUBATION_SLOT_ENABLED,
    DEFAULT_INCUBATION_SLOT_TEMPS,
    DEFAULT_INCUBATION_SLOT_TIMES,
    DEFAULT_PICTURE_ROUND_ENABLED,
    IMAGING_COLS,
    IMAGING_ROWS,
    MAX_PETRI_DISHES,
    MIN_ROUND3_ABOVE_ROUND1_MIN,
    NUM_INCUBATION_SLOTS,
    NUM_PICTURE_SLOTS,
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
    incubation_temps=None,
    incubation_times=None,
    incubation_enabled=None,
    on_tick=None,
):
    """Step 4: Run enabled incubation slots (temp + duration each)."""
    temps = list(incubation_temps or DEFAULT_INCUBATION_SLOT_TEMPS)
    times = list(incubation_times or DEFAULT_INCUBATION_SLOT_TIMES)
    enabled = list(incubation_enabled or DEFAULT_INCUBATION_SLOT_ENABLED)
    while len(temps) < NUM_INCUBATION_SLOTS:
        temps.append(temps[-1] if temps else 37.0)
    while len(times) < NUM_INCUBATION_SLOTS:
        times.append(times[-1] if times else 1.0)
    while len(enabled) < NUM_INCUBATION_SLOTS:
        enabled.append(False)
    if not any(enabled[:NUM_INCUBATION_SLOTS]):
        raise ValueError("Enable at least one incubation slot")
    for i in range(NUM_INCUBATION_SLOTS):
        if not enabled[i]:
            continue
        print(f"[Step 4] Slot {i + 1}: {temps[i]:g}°C for {times[i]:g} min")
        Start_incubation(float(temps[i]), float(times[i]), on_tick=on_tick)


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
    target_c=None,
    on_tick=None,
    on_log=None,
):
    """
    Incubate for each interval, then capture all petri dishes.

    Folders: ``data/exp_XX/03min/``, ``data/exp_XX/06min/`` (cumulative minutes).

    ``interval_minutes``: length-6 list of minutes per round (first ``num_rounds`` used).

    Returns parent experiment directory.
    """
    if target_c is None:
        target_c = DEFAULT_INCUBATION_SLOT_TEMPS[0]

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


def run_incubation_imaging_study(
    num_petri_dishes,
    incubation_temps,
    incubation_times,
    picture_times_min,
    incubation_enabled=None,
    picture_rounds_enabled=None,
    on_tick=None,
    on_log=None,
):
    """
    Full automated study: enabled incubation slots, then enabled picture rounds.

    Each picture round incubates at the matching slot temperature (rounds 4–5 use
    slot 3 temperature) for ``picture_times_min[round]`` minutes, then captures.

    Cumulative folder names: ``03min``, ``06min``, … (enabled rounds only).

    Raises ValueError if enabled round 3 time is not at least 5 minutes after round 1.
    """
    temps = [float(t) for t in incubation_temps[:3]]
    slot_times = [float(t) for t in incubation_times[:3]]
    pic_times = [float(t) for t in picture_times_min[:5]]
    inc_on = list(incubation_enabled or DEFAULT_INCUBATION_SLOT_ENABLED)
    rnd_on = list(picture_rounds_enabled or DEFAULT_PICTURE_ROUND_ENABLED)
    while len(temps) < 3:
        temps.append(temps[-1] if temps else 37.0)
    while len(slot_times) < 3:
        slot_times.append(slot_times[-1] if slot_times else 1.0)
    while len(pic_times) < 5:
        pic_times.append(pic_times[-1] if pic_times else 3.0)
    while len(inc_on) < 3:
        inc_on.append(False)
    while len(rnd_on) < 5:
        rnd_on.append(False)

    if not any(rnd_on[:NUM_PICTURE_SLOTS]):
        raise ValueError("Enable at least one picture round")

    if rnd_on[0] and rnd_on[2]:
        min_r3 = pic_times[0] + MIN_ROUND3_ABOVE_ROUND1_MIN
        if pic_times[2] < min_r3:
            raise ValueError(
                f"Round 3 time ({pic_times[2]:g} min) must be at least "
                f"{min_r3:g} min (Round 1 + {MIN_ROUND3_ABOVE_ROUND1_MIN:g} min)"
            )

    exp_dir = _next_exp_dir(data_root())
    cumulative = 0.0

    def _log(msg):
        print(msg)
        if on_log:
            on_log(msg)

    if any(inc_on[:3]):
        _log("Phase 1: incubation slots")
        for i in range(3):
            if not inc_on[i]:
                continue
            _log(f"  Slot {i + 1}: {temps[i]:g}°C for {slot_times[i]:g} min")
            Start_incubation(temps[i], slot_times[i], on_tick=on_tick)
    else:
        _log("Phase 1: skipped (no incubation slots enabled)")

    _log("Phase 2: imagery rounds")
    active_rounds = [i + 1 for i in range(5) if rnd_on[i]]
    for rnd in active_rounds:
        temp = temps[min(rnd - 1, 2)]
        mins = pic_times[rnd - 1]
        cumulative += mins
        label = f"{int(round(cumulative)):02d}min"
        _log(f"  Round {rnd}/5: {temp:g}°C, {mins:g} min → capture → {label}/")

        Start_incubation(temp, mins, on_tick=on_tick)
        step_05_prepare_imaging()
        capture_petri_dishes(
            num_petri_dishes,
            experiment_dir=exp_dir,
            time_point_subdir=label,
        )

    step_05_post_imaging_cleanup()
    _log(f"Incubation + imaging complete: {exp_dir}")
    return exp_dir
