import RPi.GPIO as GPIO
import time
import smbus

# Petri Dishes motor pins (BCM) — STEP + DIR only (same idea as filteration_flask / Media_dispensor).
# Hardware: tie EN+ on the stepper driver to GND so the driver is always enabled (typical: EN active-LOW).
STEP_PIN = 10   # CLK+
DIR_PIN = 22    # CW+

# PCF8574 I2C expander (limit switch on P4 — swapped with media_dispensor, which uses P5)
PCF8574_ADDRESS = 0x20  # Adjust if your module uses a different address

delay = 0.001   # speed control

# One-time GPIO / I2C setup for this module
_initialized = False
_i2c_initialized = False
_bus = None


def _ensure_gpio():
    """Initialize GPIO for petri dishes motor (once)."""
    global _initialized
    if not _initialized:
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(STEP_PIN, GPIO.OUT)
        GPIO.setup(DIR_PIN, GPIO.OUT)
        _initialized = True


def _ensure_i2c():
    """Initialize I2C bus and PCF8574 (once)."""
    global _i2c_initialized, _bus
    if not _i2c_initialized:
        _bus = smbus.SMBus(1)  # I2C bus 1 on Raspberry Pi

        # Configure all P0–P7 as inputs with pull-ups
        _bus.write_byte(PCF8574_ADDRESS, 0xFF)

        _i2c_initialized = True


def _read_p4():
    """Read state of P4 from PCF8574 (returns 0 or 1)."""
    _ensure_i2c()
    value = _bus.read_byte(PCF8574_ADDRESS)
    return (value >> 4) & 0x01  # bit 4 = P4


def _step(steps, direction_high):
    """Run a given number of steps in one direction."""
    _ensure_gpio()
    GPIO.output(DIR_PIN, GPIO.HIGH if direction_high else GPIO.LOW)

    for _ in range(steps):
        GPIO.output(STEP_PIN, GPIO.HIGH)
        time.sleep(delay)
        GPIO.output(STEP_PIN, GPIO.LOW)
        time.sleep(delay)


def petri_dishes_up(steps):
    """Move petri dishes motor UP by the given number of steps."""
    print(f"Petri Dishes: moving UP {steps} steps")
    # Swapped vs earlier wiring — DIR HIGH = physical UP
    _step(steps, direction_high=True)


def petri_dishes_down(steps):
    """Move petri dishes motor DOWN by the given number of steps."""
    print(f"Petri Dishes: moving DOWN {steps} steps")
    # Swapped vs earlier wiring — DIR LOW = physical DOWN
    _step(steps, direction_high=False)


def petri_dishes_home():
    """
    Drive toward the limit switch on P4 until pressed (switch on opposite side from before).

    Assumes P4 is pulled HIGH normally and goes LOW (0) when the switch is pressed.
    If the stage runs away from the switch instead, flip `toward_limit` below.
    """
    _ensure_gpio()
    _ensure_i2c()

    # Direction that moves the stage toward the limit (was DOWN+inverted pulses; now UP with same _step() pattern)
    toward_limit = True  # same as petri_dishes_up after direction swap

    print("Petri Dishes: homing until P4 limit switch (PCF8574) is pressed")

    while True:
        if _read_p4() == 0:
            print("P4 limit switch detected, stopping.")
            break
        _step(1, direction_high=toward_limit)


def cleanup():
    """Release I2C resources (GPIO cleanup handled by main). No EN pin — motor idle when not stepping."""
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