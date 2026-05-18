"""
Incubator lid stepper control (direct GPIO STEP + DIR, no limit switch).

- STEP: GPIO6 (BCM), physical pin 31
- DIR:  GPIO16 (BCM), physical pin 36

Hardware: tie EN on the driver to GND (or per datasheet).
Tune HOMING_STEPS on the Pi if home does not reach the fully open position.
"""
import time

import RPi.GPIO as GPIO

STEP_PIN = 6
DIR_PIN = 16

STEP_DELAY = 0.001

# Full travel to open/home when no limit switch is fitted (tune on hardware).
HOMING_STEPS = 4000

UP = GPIO.HIGH
DOWN = GPIO.LOW

_initialized = False


def _ensure_gpio():
    global _initialized
    if _initialized:
        return
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    GPIO.setup(STEP_PIN, GPIO.OUT, initial=GPIO.LOW)
    GPIO.setup(DIR_PIN, GPIO.OUT, initial=GPIO.LOW)
    _initialized = True


def _pulse_step(delay=STEP_DELAY):
    GPIO.output(STEP_PIN, GPIO.HIGH)
    time.sleep(delay)
    GPIO.output(STEP_PIN, GPIO.LOW)
    time.sleep(delay)


def _move(steps, direction, delay=STEP_DELAY):
    _ensure_gpio()
    GPIO.output(DIR_PIN, direction)
    time.sleep(delay)
    for _ in range(max(0, int(steps))):
        _pulse_step(delay=delay)


def incubator_lid_up(steps):
    """Move incubator lid UP (open) by the given number of steps."""
    print(f"Incubator lid: moving UP {steps} steps")
    _move(steps, direction=UP)


def incubator_lid_down(steps):
    """Move incubator lid DOWN (close) by the given number of steps."""
    print(f"Incubator lid: moving DOWN {steps} steps")
    _move(steps, direction=DOWN)


def incubator_lid_home():
    """Drive to the open/home position using a fixed step count (no limit switch)."""
    print(f"Incubator lid: homing UP {HOMING_STEPS} steps")
    _move(HOMING_STEPS, direction=UP)


# Optional CamelCase aliases
Incubator_lid_up = incubator_lid_up
Incubator_lid_down = incubator_lid_down
Incubator_lid_home = incubator_lid_home


def cleanup():
    """Release state (GPIO cleanup handled by main)."""
    global _initialized
    _initialized = False
