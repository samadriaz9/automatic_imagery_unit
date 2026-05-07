"""
Incubator lid stepper control (direct GPIO STEP + DIR).

- STEP uses GPIO6 (physical pin 31)
- DIR/CW+ uses GPIO14 (physical pin 8)
- Limit switch uses second I2C expander PCF8574 @ 0x21, pin P1

Hardware: tie EN on the driver to GND (or per datasheet).
"""
import RPi.GPIO as GPIO
import time
import smbus

STEP_PIN = 6    # CLK+
DIR_PIN = 14    # CW+ (pin 8)

delay = 0.001

_initialized = False
_i2c_initialized = False
_bus = None

PCF8574_ADDRESS = 0x21
LIMIT_P = 1  # P1
LIMIT_ACTIVE_LOW = False  # set False because your switch reads 1 when pressed


def _ensure_gpio():
    global _initialized
    if not _initialized:
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(STEP_PIN, GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(DIR_PIN, GPIO.OUT, initial=GPIO.LOW)
        _initialized = True


def _ensure_i2c():
    """Initialize I2C bus + configure PCF8574 inputs (once)."""
    global _i2c_initialized, _bus
    if not _i2c_initialized:
        _bus = smbus.SMBus(1)
        _bus.write_byte(PCF8574_ADDRESS, 0xFF)  # all input pull-ups
        _i2c_initialized = True


def _read_limit_p1():
    """Read P1 state from PCF8574 (returns 0 or 1)."""
    _ensure_i2c()
    value = _bus.read_byte(PCF8574_ADDRESS)
    return (value >> LIMIT_P) & 0x01


def _limit_pressed():
    state = _read_limit_p1()
    return state == 0 if LIMIT_ACTIVE_LOW else state == 1


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
    print(f"Incubator lid: moving UP {steps} steps (DIR=GPIO14 HIGH)")
    # Allow UP even when limit is pressed, so lid can move away from switch.
    _step(steps, direction_high=True, stop_on_limit=False)


def incubator_lid_down(steps):
    """Move incubator lid DOWN by the given number of steps."""
    print(f"Incubator lid: moving DOWN {steps} steps (DIR=GPIO14 LOW)")
    # Block DOWN when limit is pressed to avoid pushing into the switch.
    _step(steps, direction_high=False, stop_on_limit=True)


def incubator_lid_home():
    """Move DOWN until P1 limit switch is pressed."""
    print("Incubator lid: homing DOWN until P1 limit switch is pressed")
    _ensure_gpio()
    GPIO.output(DIR_PIN, GPIO.LOW)  # same as down
    time.sleep(delay)

    while True:
        if _limit_pressed():
            print("Incubator lid: P1 limit switch detected, homing stop.")
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
    global _initialized, _i2c_initialized, _bus
    if _initialized:
        _initialized = False
    if _i2c_initialized and _bus is not None:
        try:
            _bus.close()
        except AttributeError:
            pass
        _i2c_initialized = False
        _bus = None
