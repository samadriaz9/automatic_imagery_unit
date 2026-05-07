import RPi.GPIO as GPIO
import time
import smbus

# Camera motor pins (BCM numbering)
STEP_PIN = 5    # CLK+
DIR_PIN = 7     # CW+
EN_PIN = 9      # EN+

# PCF8574 I2C expander (limit switch on P3)
PCF8574_ADDRESS = 0x20  # Adjust if your module uses a different address

delay = 0.001   # speed control

# One-time GPIO / I2C setup
_initialized = False
_i2c_initialized = False
_bus = None


def _ensure_gpio():
    """Initialize GPIO for camera motor (once)."""
    global _initialized
    if not _initialized:
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(STEP_PIN, GPIO.OUT)
        GPIO.setup(DIR_PIN, GPIO.OUT)
        GPIO.setup(EN_PIN, GPIO.OUT)
        GPIO.output(EN_PIN, GPIO.LOW)  # Enable motor (LOW = enable)
        _initialized = True


def _ensure_i2c():
    """Initialize I2C bus and PCF8574 (once)."""
    global _i2c_initialized, _bus
    if not _i2c_initialized:
        _bus = smbus.SMBus(1)

        # Configure all P0–P7 as inputs with pull-ups
        _bus.write_byte(PCF8574_ADDRESS, 0xFF)

        _i2c_initialized = True


def _read_p3():
    """Read state of P3 from PCF8574 (returns 0 or 1)."""
    _ensure_i2c()
    value = _bus.read_byte(PCF8574_ADDRESS)
    return (value >> 3) & 0x01  # bit 3 = P3


def _step(steps, direction_high):
    """Run a given number of steps in one direction."""
    _ensure_gpio()
    GPIO.output(DIR_PIN, GPIO.HIGH if direction_high else GPIO.LOW)

    for _ in range(steps):
        GPIO.output(STEP_PIN, GPIO.HIGH)
        time.sleep(delay)
        GPIO.output(STEP_PIN, GPIO.LOW)
        time.sleep(delay)


def Camera_up(steps):
    """Move camera motor UP by the given number of steps."""
    print(f"Camera: moving UP {steps} steps")
    _step(steps, direction_high=False)  # DIR LOW = UP


def Camera_down(steps):
    """Move camera motor DOWN by the given number of steps."""
    print(f"Camera: moving DOWN {steps} steps")
    _step(steps, direction_high=True)  # DIR HIGH = DOWN


def Camera_home():
    """
    Drive the camera motor DOWN until the limit switch on P3 is pressed.
    Assumes P3 is HIGH normally and LOW when pressed.
    """
    print("Camera: homing DOWN until P3 limit switch (PCF8574) is pressed")

    _ensure_gpio()
    _ensure_i2c()

    # Set direction for DOWN
    GPIO.output(DIR_PIN, GPIO.LOW)

    while True:
        p3 = _read_p3()

        if p3 == 0:
            print("P3 limit switch detected, stopping.")
            break

        GPIO.output(STEP_PIN, GPIO.LOW)
        time.sleep(delay)
        GPIO.output(STEP_PIN, GPIO.HIGH)
        time.sleep(delay)


def cleanup():
    """Disable motor and release GPIO."""
    global _initialized, _i2c_initialized, _bus

    if _initialized:
        GPIO.output(EN_PIN, GPIO.HIGH)  # disable driver
        _initialized = False

    if _i2c_initialized and _bus is not None:
        try:
            _bus.close()
        except AttributeError:
            pass
        _i2c_initialized = False
        _bus = None