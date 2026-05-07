"""
Main script for Filteration Flask, Filteration Unit and Suction Pump control.
Runs homing (down until limit switch via PCF8574) and then movements.

Filteration flask: STEP=18, DIR=23 (BCM); EN tied on hardware (see filteration_flask.py).
Filteration unit: STEP=13, DIR=19 (BCM); EN tied on hardware (see filteration_unit.py).
Suction pump lift (stepper): STEP=21, DIR=12 (BCM); EN tied on hardware (see suction_pump_up_down.py). Flask/upper DC pump: GPIO 11 RPWM (see upper_suction_pump.py); leave GPIO 4 for DS18B20.
Petri dishes: STEP=10, DIR=22 (BCM); EN tied on hardware (see petri_dishes.py).
Media dispensor: STEP=24, DIR=27 (BCM); physical pins 18 & 13 (see Media_dispensor.py).
Suction pipe: STEP=8, DIR=20 (BCM); no limit switch — use up/down with steps only (see suction_pipe.py).
Incubator lid: STEP=6, DIR=16 (BCM); physical pins 31 & 36; no limit (see incubator_lid.py).
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

from relay_control import P1, P7, run_relay, cleanup as relay_cleanup
from incubation_module import Start_incubation
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
        ("relay", relay_cleanup),
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
    x = input ('Enter to start camera: ')
    Camera_home()

    x = input ('Enter to start incubator lid: ')
    incubator_lid_home()





    x = input ('Enter to bring all home : ')
    Media_dispensor_home()
    incubator_lid_home()
    suction_pipe_home()
    filteration_unit_config()
    filteration_flask_config()
    petri_dishes_home()
    petri_dishes_down(1035)
    suction_pump_home()
    suction_pump_up(400)

 
    x = input ('step 1: Enter to Empty Syringe: ')
    Media_dispensor_home()
    x= input ('step 2: Enter to change the media: ')
    Media_dispensor_home()
    Media_dispensor_up(3500)
    x = input ('step 3: Enter to adjust syringe position: ')
    Media_dispensor_down(800)
    
    
    x = input ("step 4: Enter to bring petri dishes home")
    incubator_lid_home()
    petri_dishes_home()
    petri_dishes_down(1035)
    
    x = input ("step 5: Enter to put filter paper on filteration flask")
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

    x = input ("Step 6: Enter to send filter paper to assembly")
    filteration_unit_config()
    filteration_flask_config()
    Filteration_flask_up(10)
    Filteration_unit_up(850)
    time.sleep(1)
    solinoid_value_to_filteration()
    filteration_suction_pump_on(90)
    time.sleep(20)
    while water_level_reached():
        filteration_suction_pump_off()
        print(
            "Water level sensor still reads FULL after filtration pump run — pump may not be drawing. "
            "Fix the pump or plumbing before continuing."
        )
        input("Press Enter after fixing to re-run pump (90% for 20 s) and re-check...")
        filteration_suction_pump_on(90)
        time.sleep(20)

    filteration_suction_pump_off()
    
    x = input ("Step 7: Enter for picking up media pad plus petri dishes")
    suction_pump_home()
    suction_pipe_home()
    suction_pipe_up(1025)
    upper_suction_pump_on(100)
    time.sleep(2)
    suction_pipe_down(1025)
    suction_pump_up(3065)
    suction_pipe_up(300)
    upper_suction_pump_off()
    
    x = input ("Step 8: Enter for poruing media")
    petri_dishes_home()
    petri_dishes_down(300)
    Media_dispensor_down(800)
    time.sleep(2)
    petri_dishes_down(725)
    
    
    x = input ("Step 9: Enter to pick up filteration unit")
    filteration_unit_config()
    filteration_flask_config()
    Filteration_flask_up(1130)
    
    
    x = input ("Step 10: Picking up filter paper from filteration flask")
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
    
    x = input ("Step 11: Enter to shift it for incubation")
    incubator_lid_home()
    petri_dishes_home()
    petri_dishes_down(3280)
    incubator_lid_up(200)
    
    x = input ("Step 12: Enter to start incubation")
    run_relay(P1, 1)
    Start_incubation(37, 1)

    x  = input ("Step 13: Enter to start pictures")
    try:
        ok = _camera_ready(device_index=0, tries=2, wait_s=0.05)
        if ok:
            print("camera on")
        else:
            run_relay(P7, 3)
            time.sleep(3)
            print("camera switched on")
    except Exception as e:
        print(f"Camera not found")
        sys.exit(1)
    Camera_home()
    Camera_down(2430)
    incubator_lid_home()
    petri_dishes_home()
    petri_dishes_down(3290)
    petri_dishes_up(330)
    ok = False
    for i in range(10):
        if _camera_ready(device_index=0, tries=1, wait_s=0.05):
            print("camera on")
            ok = True
            break
        else:
            print("camera off")
            time.sleep(0.1)
    if ok:
        print("Starting imaging capture pattern")
        start_imaging_capture_pattern()
        time.sleep(0.5)
        print("Imaging capture pattern completed")
    else:
        print("camera not on")
    petri_dishes_home()
    petri_dishes_down(3290)
    incubator_lid_up(200)
    run_relay(P7, 3)
    time.sleep(3)

    x = input ('Step 14: Enter to put in trash: ')
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
    for i in range(20):
        suction_pump_up(120)
        suction_pump_down(120)
        time.sleep(0.01)
    time.sleep(2)

    x = input ('Step 15: Enter to Steriliz: ')

except KeyboardInterrupt:
    print("\nInterrupted (Ctrl+C).")

finally:
    stop_usb_camera_thread(_usb_camera_worker)
    shutdown_all()
