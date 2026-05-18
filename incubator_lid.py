"""
Incubator lid stepper control (direct GPIO STEP + DIR).

- STEP uses GPIO18
- DIR/CW+ uses GPIO17
- Limit switch uses direct Raspberry Pi GPIO6

Hardware: tie EN on the driver to GND (or per datasheet).
"""
import RPi.GPIO as GPIO
import time

DIR_PIN   = 17
STEP_PIN  = 18
LIMIT_PIN = 6

delay = 0.001

_initialized = False


def _ensure_gpio():
    global _initialized
    if not _initialized:
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(STEP_PIN, GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(DIR_PIN, GPIO.OUT, initial=GPIO.LOW)
        # Direct limit switch: not pressed=HIGH, pressed=LOW.
        GPIO.setup(LIMIT_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        _initialized = True


def _limit_pressed():
    _ensure_gpio()
    return GPIO.input(LIMIT_PIN) == GPIO.LOW


def _step(steps, direction_high, stop_on_limit=False):
    _ensure_gpio()
    GPIO.output(DIR_PIN, GPIO.HIGH if direction_high else GPIO.LOW)
    # Some stepper drivers need a short DIR setup time before the first step edge.
    time.sleep(delay)
    for _ in range(steps):
        if stop_on_limit and _limit_pressed():
            print("Incubator lid: limit switch pressed -> stopping.")
            break
        GPIO.output(STEP_PIN, GPIO.HIGH)
        time.sleep(delay)
        GPIO.output(STEP_PIN, GPIO.LOW)
        time.sleep(delay)


def incubator_lid_up(steps):
    """Move incubator lid UP by the given number of steps."""
    print(f"Incubator lid: moving UP {steps} steps")
    # Allow UP even when limit is pressed, so lid can move away from switch.
    _step(steps, direction_high=True, stop_on_limit=False)


def incubator_lid_down(steps):
    """Move incubator lid DOWN by the given number of steps."""
    print(f"Incubator lid: moving DOWN {steps} steps")
    # Block DOWN when limit is pressed to avoid pushing into the switch.
    _step(steps, direction_high=False, stop_on_limit=True)


def incubator_lid_home():
    """Move UP until direct GPIO limit switch is pressed."""
    print("Incubator lid: homing UP until limit switch is pressed")
    _ensure_gpio()
    GPIO.output(DIR_PIN, GPIO.HIGH)  # same as up — toward limit switch
    time.sleep(delay)

    while True:
        if _limit_pressed():
            print("Incubator lid: limit switch detected, homing stop.")
            break
        GPIO.output(STEP_PIN, GPIO.HIGH)
        time.sleep(delay)
        GPIO.output(STEP_PIN, GPIO.LOW)
        time.sleep(delay)


# Optional CamelCase aliases
Incubator_lid_up = incubator_lid_up
Incubator_lid_down = incubator_lid_down
Incubator_lid_home = incubator_lid_home


def cleanup():
    """Release state (GPIO cleanup handled by main)."""
    global _initialized
    if _initialized:
        _initialized = False
