"""
Six-step automation workflow — callable from CLI (main.py) or procedure_gui.py.
"""
"abc commit"
import os
import time

from device_config import (
    CAMERA_DISH_PRE_UP,
    CAMERA_DISH_PRE_UP_ROW2,
    CAMERA_STEPSIZE,
    DEFAULT_ROUND_ENABLED,
    DEFAULT_ROUND_TEMPS,
    DEFAULT_ROUND_TIMES_MIN,
    IMAGING_COLS,
    IMAGING_ROWS,
    MAX_PETRI_DISHES,
    NUM_INCUBATION_SLOTS,
    NUM_STUDY_ROUNDS,
    STEP_INCUBATION_MINUTES,
    STEP_INCUBATION_TEMP_C,
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
    incubator_lid_down(550)


def step_02_insert_petri_dishes():
    """Step 2: Insert petri dishes (lid up, petri home)."""
    incubator_lid_home()
    petri_dishes_home()


def step_03_shift_for_incubation():
    """Step 3: Shift stage for incubation region."""
    incubator_lid_home()
    petri_dishes_home()
    petri_dishes_up(2400)
    incubator_lid_down(550)


def step_04_incubation(on_tick=None):
    """Step 4: Hold sample at 37 °C for 2 minutes."""
    print(
        f"[Step 4] Incubation {STEP_INCUBATION_TEMP_C:g}°C "
        f"for {STEP_INCUBATION_MINUTES:g} min"
    )
    Start_incubation(
        STEP_INCUBATION_TEMP_C,
        STEP_INCUBATION_MINUTES,
        on_tick=on_tick,
    )


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
    incubator_lid_down(550)


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
        target_c = DEFAULT_ROUND_TEMPS[0]

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
    round_temps,
    round_times_min,
    rounds_enabled=None,
    on_tick=None,
    on_log=None,
    on_round_start=None,
):
    """
    For each enabled round: incubate at round temp/time, then capture petri dishes.

    Images are saved under ``data/exp_XX/{MM}min/`` using that round's time (minutes).
    Duplicate folder names get a ``_rN`` suffix.
    """
    temps = [float(t) for t in round_temps[:NUM_STUDY_ROUNDS]]
    times = [float(t) for t in round_times_min[:NUM_STUDY_ROUNDS]]
    enabled = list(rounds_enabled or DEFAULT_ROUND_ENABLED)
    while len(temps) < NUM_STUDY_ROUNDS:
        temps.append(37.0)
    while len(times) < NUM_STUDY_ROUNDS:
        times.append(4.0)
    while len(enabled) < NUM_STUDY_ROUNDS:
        enabled.append(False)

    if not any(enabled[:NUM_STUDY_ROUNDS]):
        raise ValueError("Enable at least one round")

    exp_dir = _next_exp_dir(data_root())

    def _log(msg):
        print(msg)
        if on_log:
            on_log(msg)

    active = [i + 1 for i in range(NUM_STUDY_ROUNDS) if enabled[i]]
    _log(f"Incubation + imaging: {len(active)} round(s), petri={num_petri_dishes}")

    for idx, rnd in enumerate(active):
        temp = temps[rnd - 1]
        mins = times[rnd - 1]
        label = f"{int(round(mins)):02d}min"
        subdir = label
        if os.path.exists(os.path.join(exp_dir, subdir)):
            subdir = f"{label}_r{rnd}"

        _log(f"  Round {rnd}: {temp:g}°C, {mins:g} min → capture → {subdir}/")
        if on_round_start:
            try:
                on_round_start(rnd)
            except Exception:
                pass

        Start_incubation(temp, mins, on_tick=on_tick)
        step_05_prepare_imaging()
        capture_petri_dishes(
            num_petri_dishes,
            experiment_dir=exp_dir,
            time_point_subdir=subdir,
        )

        if idx < len(active) - 1:
            next_rnd = active[idx + 1]
            _log(f"  Round {rnd} complete — all home before round {next_rnd}")
            step_01_all_home()

    step_05_post_imaging_cleanup()
    _log(f"Incubation + imaging complete: {exp_dir}")
    return exp_dir
