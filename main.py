"""
Main script for Filteration Flask, Filteration Unit and Suction Pump control.
Runs homing (down until limit switch via PCF8574) and then movements.

Filteration flask: STEP=18, DIR=23 (BCM); EN tied on hardware (see filteration_flask.py).
Filteration unit: STEP=13, DIR=19 (BCM); EN tied on hardware (see filteration_unit.py).
Suction pump lift (stepper): STEP=21, DIR=12 (BCM); EN tied on hardware (see suction_pump_up_down.py). Flask/upper DC pump: GPIO 11 RPWM (see upper_suction_pump.py); leave GPIO 4 for DS18B20.
Petri dishes: STEP=10, DIR=22 (BCM); EN tied on hardware (see petri_dishes.py).
Media dispensor: STEP=24, DIR=27 (BCM); physical pins 18 & 13 (see Media_dispensor.py).
Suction pipe: STEP=8, DIR=20 (BCM); no limit switch — use up/down with steps only (see suction_pipe.py).
Incubator lid: STEP=6, DIR=16, LIMIT=17 (BCM); physical pins 31, 36 & 11 (see incubator_lid.py).
Filtration solenoid: GPIO 26 (BCM), pin 37 (see solinoid_value_to_filteration.py).

Shutdown: Ctrl+C runs full cleanup (see shutdown_all). SIGTERM (kill) also cleans up.
"""
import atexit
import gc
import signal
import sys
import time
import cv2

def _missing_function(module_name, func_name):
    def _inner(*_args, **_kwargs):
        raise RuntimeError(f"Missing module '{module_name}': cannot run '{func_name}()'")
    return _inner


def _missing_cleanup(*_args, **_kwargs):
    return None


try:
    from suction_pump_up_down import (
        suction_pump_up,
        suction_pump_down,
        suction_pump_home,
        cleanup as suction_lift_cleanup,
    )
except ModuleNotFoundError:
    suction_pump_up = _missing_function("suction_pump_up_down", "suction_pump_up")
    suction_pump_down = _missing_function("suction_pump_up_down", "suction_pump_down")
    suction_pump_home = _missing_function("suction_pump_up_down", "suction_pump_home")
    suction_lift_cleanup = _missing_cleanup

try:
    from filteration_flask import (
        Filteration_flask_up,
        Filteration_flask_down,
        filteration_flask_config,
        cleanup as filteration_cleanup,
    )
except ModuleNotFoundError:
    Filteration_flask_up = _missing_function("filteration_flask", "Filteration_flask_up")
    Filteration_flask_down = _missing_function("filteration_flask", "Filteration_flask_down")
    filteration_flask_config = _missing_function("filteration_flask", "filteration_flask_config")
    filteration_cleanup = _missing_cleanup

try:
    from filteration_unit import (
        Filteration_unit_up,
        Filteration_unit_down,
        filteration_unit_config,
        cleanup as filteration_unit_cleanup,
    )
except ModuleNotFoundError:
    Filteration_unit_up = _missing_function("filteration_unit", "Filteration_unit_up")
    Filteration_unit_down = _missing_function("filteration_unit", "Filteration_unit_down")
    filteration_unit_config = _missing_function("filteration_unit", "filteration_unit_config")
    filteration_unit_cleanup = _missing_cleanup

try:
    from upper_suction_pump import (
        upper_suction_pump_on,
        upper_suction_pump_off,
        cleanup as suction_cleanup,
    )
except ModuleNotFoundError:
    upper_suction_pump_on = _missing_function("upper_suction_pump", "upper_suction_pump_on")
    upper_suction_pump_off = _missing_function("upper_suction_pump", "upper_suction_pump_off")
    suction_cleanup = _missing_cleanup

try:
    from consumable import cleanup as consumable_cleanup
except ModuleNotFoundError:
    consumable_cleanup = _missing_cleanup

from incubation_module import keep_temperature_pid
from imaging import start_imaging_capture_pattern

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

from petri_dishes import (
    petri_dishes_home,
    petri_dishes_up,
    petri_dishes_down,
    cleanup as petri_dishes_cleanup,
)
from camera_module import (
    Camera_home,
    Camera_up,
    Camera_down,
    cleanup as camera_cleanup,
)

try:
    from media_dispensor import (
        Media_dispensor_home,
        Media_dispensor_up,
        Media_dispensor_down,
        cleanup as media_dispensor_cleanup,
    )
except ModuleNotFoundError:
    Media_dispensor_home = _missing_function("media_dispensor", "Media_dispensor_home")
    Media_dispensor_up = _missing_function("media_dispensor", "Media_dispensor_up")
    Media_dispensor_down = _missing_function("media_dispensor", "Media_dispensor_down")
    media_dispensor_cleanup = _missing_cleanup

try:
    from suction_pipe import (
        suction_pipe_home,
        suction_pipe_up,
        suction_pipe_down,
        cleanup as suction_pipe_cleanup,
    )
except ModuleNotFoundError:
    suction_pipe_home = _missing_function("suction_pipe", "suction_pipe_home")
    suction_pipe_up = _missing_function("suction_pipe", "suction_pipe_up")
    suction_pipe_down = _missing_function("suction_pipe", "suction_pipe_down")
    suction_pipe_cleanup = _missing_cleanup

from incubator_lid import (
    incubator_lid_home,
    incubator_lid_up,
    incubator_lid_down,
    cleanup as incubator_lid_cleanup,
)

try:
    from usb_camera_thread import stop_usb_camera_thread
except ModuleNotFoundError:
    def stop_usb_camera_thread(_worker):
        return None

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
    from solinoid_value_drain import cleanup as drain_solenoid_cleanup
except ModuleNotFoundError:
    drain_solenoid_cleanup = _missing_cleanup

try:
    from solinoid_waste import cleanup as waste_solenoid_cleanup
except ModuleNotFoundError:
    waste_solenoid_cleanup = _missing_cleanup
import RPi.GPIO as GPIO

# Camera relay control (direct GPIO, no smbus/PCF8574).
# Your wiring: physical pin 22 -> BCM25, active-low (relay OFF = HIGH).
CAMERA_RELAY_GPIO = 25
CAMERA_RELAY_ACTIVE = GPIO.LOW
CAMERA_RELAY_INACTIVE = GPIO.HIGH
CAMERA_RELAY_PULSE_S = 4.0
CAMERA_BOOT_WAIT_S = 10.0
CAMERA_READY_TIMEOUT_S = 30.0
CAMERA_READY_POLL_S = 0.5


def _setup_camera_relay_output():
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(CAMERA_RELAY_GPIO, GPIO.OUT, initial=CAMERA_RELAY_INACTIVE)


def _release_camera_relay_pin():
    """Stop driving the relay line (relay board / latch holds camera state)."""
    try:
        GPIO.setup(CAMERA_RELAY_GPIO, GPIO.IN)
    except Exception:
        pass


def pulse_camera_relay(contact_seconds=CAMERA_RELAY_PULSE_S):
    """
    Momentary relay contact then release GPIO (toggle / latch wiring).

    Active-low: LOW for contact_seconds, return to HIGH, then set pin INPUT so
    the coil is not held energized. Same pulse toggles camera ON or OFF.
    """
    _setup_camera_relay_output()
    GPIO.output(CAMERA_RELAY_GPIO, CAMERA_RELAY_ACTIVE)
    time.sleep(max(0.0, float(contact_seconds)))
    GPIO.output(CAMERA_RELAY_GPIO, CAMERA_RELAY_INACTIVE)
    _release_camera_relay_pin()


def power_on_usb_camera(device_index=0):
    """
    Toggle camera ON (4 s relay pulse, pin released), wait for USB boot, verify stream.
    Assumes camera starts powered off before imaging.
    """
    print(f"[Camera] Relay ON pulse ({CAMERA_RELAY_PULSE_S:.0f}s), pin released...")
    pulse_camera_relay(CAMERA_RELAY_PULSE_S)
    print(f"[Camera] Waiting {CAMERA_BOOT_WAIT_S:.0f}s for USB boot...")
    time.sleep(CAMERA_BOOT_WAIT_S)
    if _wait_for_camera_ready(device_index=device_index):
        print("[Camera] USB camera ready")
        return True
    print("[Camera] USB camera not ready after power-on")
    return False


def power_off_usb_camera():
    """Toggle camera OFF (4 s relay pulse, pin released)."""
    print(f"[Camera] Relay OFF pulse ({CAMERA_RELAY_PULSE_S:.0f}s), pin released...")
    pulse_camera_relay(CAMERA_RELAY_PULSE_S)


def _wait_for_camera_ready(device_index=0, timeout_s=CAMERA_READY_TIMEOUT_S, poll_s=CAMERA_READY_POLL_S):
    """Poll until USB camera delivers a frame or timeout."""
    deadline = time.time() + max(0.0, float(timeout_s))
    while time.time() < deadline:
        if _camera_ready(device_index=device_index, tries=3, wait_s=0.1):
            return True
        time.sleep(max(0.05, float(poll_s)))
    return False

# --- Run once: stops PWM/relays/solenoid and releases GPIO (helps avoid drivers heating when idle) ---
_shutdown_done = False
_usb_camera_worker = None


def _open_usb_camera(device_index=0):
    """Open USB camera with Linux V4L2 backend to avoid GStreamer instability."""
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


def _camera_ready(device_index=0, tries=10, wait_s=0.1):
    """Best-effort camera readiness check with guaranteed release."""
    cap = _open_usb_camera(device_index=device_index)
    if cap is None:
        return False
    try:
        for _ in range(max(1, int(tries))):
            ok, frame = cap.read()
            if ok and frame is not None:
                return True
            time.sleep(float(wait_s))
        return False
    finally:
        try:
            cap.release()
        except Exception:
            pass


def shutdown_all():
    """Idempotent full cleanup. Call on exit, Ctrl+C, or SIGTERM."""
    global _shutdown_done
    if _shutdown_done:
        return
    _shutdown_done = True
    print("\n[Shutdown] Releasing GPIO and stopping outputs...")

    # Stop DC/PWM and relays first; then stepper modules; solenoid off; GPIO.cleanup last.
    for name, fn in (
        ("filteration_suction_pump", filteration_suction_cleanup),
    ("upper_suction_pump (DC)", suction_cleanup),
        ("suction_pump_up_down", suction_lift_cleanup),
        ("solenoid", solenoid_cleanup),
        ("drain_solenoid", drain_solenoid_cleanup),
        ("waste_solenoid", waste_solenoid_cleanup),
        ("consumable", consumable_cleanup),
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
        except Exception as e:
            print(f"  Cleanup warning ({name}): {e}")

    # Finalize PWM wrappers while GPIO is still valid (avoids RPi.GPIO PWM.__del__ after cleanup).
    gc.collect()

    try:
        GPIO.cleanup()
    except Exception:
        pass
    print("[Shutdown] Done.")


def _on_sigterm(signum, frame):
    shutdown_all()
    sys.exit(0)


# kill / systemd stop without -9 This is the kill signal handler
signal.signal(signal.SIGTERM, _on_sigterm)
atexit.register(shutdown_all)

try:
    x = input ('Enter to shift for incubation: ')
    incubator_lid_home()
    petri_dishes_home()
    petri_dishes_up(2400)
    incubator_lid_down(500)

    x = input ('Enter to start pictures: ')
    incubator_lid_home()
    petri_dishes_home()
    petri_dishes_up(700) 
    Camera_home()
    Camera_up(3700)
    
    x = input ('Enter to start all modules home: ')
    print("Step 01: All modules home")
    Camera_home()
    incubator_lid_home()
    petri_dishes_home()
    petri_dishes_up(2400)
    incubator_lid_down(300)

    x = input ('Enter to keep petri dishes home: ')
    print("Step 02: ")
    incubator_lid_home()
    petri_dishes_home()

    x = input ('Enter to shift for incubation: ')
    incubator_lid_home()
    petri_dishes_home()
    petri_dishes_up(2400)
    incubator_lid_down(400)

    x = input ('Enter to start incubation: ')
    keep_temperature_pid(37, 1)

    x = input ('Enter to start pictures: ')
    incubator_lid_home()
    petri_dishes_home()
    petri_dishes_up(500) 
    Camera_home()
    Camera_up(3200)

    x = input("Step 13: Enter to start pictures")
    camera_powered = False
    try:
        if not power_on_usb_camera(device_index=0):
            print("Camera not available — skipping imaging capture")
        else:
            camera_powered = True
            print("Starting imaging capture pattern")
            start_imaging_capture_pattern()
            time.sleep(0.5)
            print("Imaging capture pattern completed")
    except Exception as e:
        print(f"Imaging failed: {e}")
    finally:
        if camera_powered:
            power_off_usb_camera()
    incubator_lid_home()
    petri_dishes_home()
    petri_dishes_up(2400)
    incubator_lid_down(300)

    x = input ('Step 15: Enter to Steriliz: ')

except KeyboardInterrupt:
    print("\nInterrupted (Ctrl+C).")

finally:
    stop_usb_camera_thread(_usb_camera_worker)
    shutdown_all()
