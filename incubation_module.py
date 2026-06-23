import glob
import time
import RPi.GPIO as GPIO

try:
    from simple_pid import PID
except Exception:
    PID = None


UPPER_HEATER_PIN = 12  # BCM 12, physical pin 32 (upper BTS PWM)
LOWER_HEATER_PIN = 26  # BCM 26, physical pin 37 (lower BTS PWM)
DEFAULT_HEATER_PINS = (UPPER_HEATER_PIN, LOWER_HEATER_PIN)
# Legacy alias
RPWM_PIN = UPPER_HEATER_PIN


def _read_ds18b20_c(sensor_glob="/sys/bus/w1/devices/28-*/w1_slave"):
    """
    Read DS18B20 temperature in Celsius from w1 sysfs.
    Raises RuntimeError if sensor file is missing or CRC/data invalid.
    """
    paths = glob.glob(sensor_glob)
    if not paths:
        raise RuntimeError("DS18B20 not found under /sys/bus/w1/devices/28-*/w1_slave")

    with open(paths[0], "r", encoding="utf-8") as f:
        lines = f.read().strip().splitlines()

    if len(lines) < 2 or not lines[0].strip().endswith("YES"):
        raise RuntimeError("DS18B20 CRC invalid (first line does not end with YES)")

    marker = "t="
    if marker not in lines[1]:
        raise RuntimeError("DS18B20 temperature token 't=' not found")

    milli_c = int(lines[1].split(marker, 1)[1])
    return milli_c / 1000.0


def _set_heaters_duty_smooth(pwms, current_duty, target_duty, max_duty, ramp_step, ramp_delay):
    """Ramp all heater PWM channels together to the same duty cycle."""
    target_duty = max(0.0, min(float(max_duty), float(target_duty)))
    duty = float(current_duty)
    if abs(target_duty - duty) < 0.001:
        return target_duty

    direction = 1.0 if target_duty > duty else -1.0
    step = abs(float(ramp_step)) * direction
    while (direction > 0 and duty < target_duty) or (direction < 0 and duty > target_duty):
        duty += step
        if direction > 0 and duty > target_duty:
            duty = target_duty
        if direction < 0 and duty < target_duty:
            duty = target_duty
        level = max(0.0, min(float(max_duty), duty))
        for pwm in pwms:
            pwm.ChangeDutyCycle(level)
        time.sleep(float(ramp_delay))
    return duty


def _start_heater_pwms(heater_pins, pwm_freq):
    GPIO.setmode(GPIO.BCM)
    pwms = []
    for pin in heater_pins:
        GPIO.setup(int(pin), GPIO.OUT)
        pwm = GPIO.PWM(int(pin), int(pwm_freq))
        pwm.start(0)
        pwms.append(pwm)
    return pwms


def _stop_heater_pwms(pwms):
    for pwm in pwms:
        try:
            pwm.ChangeDutyCycle(0)
            pwm.stop()
        except Exception:
            pass


def Start_incubation(
    target_temp_c,
    duration_minutes,
    poll_seconds=2.0,
    on_tick=None,
    heater_pins=None,
    pwm_pin=None,
    pwm_freq=100,
    kp=10.0,
    ki=0.2,
    kd=2.0,
    max_duty=20.0,
    ramp_step=2.0,
    ramp_delay=0.1,
):
    """
    Maintain incubation temperature using PID + one or more BTS PWM heater outputs.

    Both upper and lower heaters are driven from the same DS18B20 reading and the
    same PID output so they heat together for stable chamber temperature.

    Args:
        target_temp_c: target temperature in Celsius.
        duration_minutes: how long to maintain incubation.
        heater_pins: BCM pin tuple for BTS PWM inputs (default upper + lower).
        pwm_pin: legacy single-pin alias; ignored when heater_pins is set.
        pwm_freq: PWM frequency in Hz.
        kp, ki, kd: PID gains.
        max_duty: safety cap for each heater duty cycle (%).
        ramp_step/ramp_delay: soft-ramp behavior to reduce thermal overshoot.
        poll_seconds: sensor polling interval.
        on_tick: optional callback(elapsed_s, remaining_s, temp_c, target_temp_c).
    """
    target_temp_c = float(target_temp_c)
    duration_s = max(0.0, float(duration_minutes) * 60.0)
    poll_seconds = max(0.2, float(poll_seconds))
    max_duty = max(1.0, min(100.0, float(max_duty)))

    if heater_pins is None:
        heater_pins = (int(pwm_pin),) if pwm_pin is not None else DEFAULT_HEATER_PINS
    heater_pins = tuple(int(p) for p in heater_pins)
    if not heater_pins:
        raise ValueError("At least one heater pin is required")

    print(
        f"[Incubation] Start PID: target={target_temp_c:.2f}C, duration={duration_minutes} min"
    )
    print(
        f"[Incubation] Heater PWM pins={heater_pins}, freq={int(pwm_freq)}Hz, "
        f"PID(Kp={kp}, Ki={ki}, Kd={kd}), max_duty={max_duty:.1f}% each"
    )

    heater_pwms = _start_heater_pwms(heater_pins, pwm_freq)

    pid = None
    i_term = 0.0
    prev_error = 0.0
    current_duty = 0.0
    if PID is not None:
        pid = PID(float(kp), float(ki), float(kd), setpoint=target_temp_c)
        pid.output_limits = (0.0, max_duty)
        try:
            pid.sample_time = float(poll_seconds)
        except Exception:
            pass

    start = time.time()

    def _notify_tick(temp_c):
        if on_tick is None:
            return
        elapsed = time.time() - start
        remaining = max(0.0, duration_s - elapsed)
        try:
            on_tick(elapsed, remaining, temp_c, target_temp_c)
        except Exception:
            pass

    try:
        try:
            _notify_tick(_read_ds18b20_c())
        except RuntimeError as exc:
            print(f"[Incubation] Initial sensor read failed: {exc}")
            _notify_tick(float("nan"))

        while (time.time() - start) < duration_s:
            temp_c = _read_ds18b20_c()
            if pid is not None:
                requested_duty = float(pid(temp_c))
            else:
                error = target_temp_c - temp_c
                i_term += error * poll_seconds
                d_term = (error - prev_error) / poll_seconds
                prev_error = error
                raw = (float(kp) * error) + (float(ki) * i_term) + (float(kd) * d_term)
                requested_duty = max(0.0, min(max_duty, raw))

            current_duty = _set_heaters_duty_smooth(
                heater_pwms,
                current_duty=current_duty,
                target_duty=requested_duty,
                max_duty=max_duty,
                ramp_step=ramp_step,
                ramp_delay=ramp_delay,
            )
            print(
                f"[Incubation] {temp_c:.2f}C -> heaters {current_duty:.1f}% "
                f"({len(heater_pwms)} channel(s))"
            )
            _notify_tick(temp_c)
            time.sleep(poll_seconds)
    finally:
        _stop_heater_pwms(heater_pwms)
        print("[Incubation] Completed. All heaters OFF.")


def keep_temperature_pid(temperature_to_keep_c, minutes, **kwargs):
    """
    Convenience wrapper for main usage.

    Example:
        keep_temperature_pid(37.0, 60)  # keep 37C for 60 minutes
    """
    return Start_incubation(temperature_to_keep_c, minutes, **kwargs)
