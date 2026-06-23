import glob
import time
import RPi.GPIO as GPIO

try:
    from simple_pid import PID
except Exception:
    PID = None


LOWER_HEATER_PIN = 12  # BCM 12, physical pin 32
UPPER_HEATER_PIN = 26  # BCM 26, physical pin 37
UPPER_HEATER_DUTY_BOOST = 1.30  # upper runs 30% hotter than lower (same PID base)
HEATER_DUTY_SCALE = {
    LOWER_HEATER_PIN: 1.0,
    UPPER_HEATER_PIN: UPPER_HEATER_DUTY_BOOST,
}
DEFAULT_HEATER_PINS = (LOWER_HEATER_PIN, UPPER_HEATER_PIN)
# Legacy alias (first / lower heater)
RPWM_PIN = LOWER_HEATER_PIN


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


def _set_heaters_duty_smooth(channels, current_base, target_base, max_duty, ramp_step, ramp_delay):
    """Ramp PID base duty; each heater gets base * its scale (capped at max_duty)."""
    target_base = max(0.0, min(float(max_duty), float(target_base)))
    base = float(current_base)
    if abs(target_base - base) < 0.001:
        return base

    direction = 1.0 if target_base > base else -1.0
    step = abs(float(ramp_step)) * direction
    while (direction > 0 and base < target_base) or (direction < 0 and base > target_base):
        base += step
        if direction > 0 and base > target_base:
            base = target_base
        if direction < 0 and base < target_base:
            base = target_base
        for ch in channels:
            level = max(0.0, min(float(max_duty), base * ch["scale"]))
            ch["pwm"].ChangeDutyCycle(level)
            ch["duty"] = level
        time.sleep(float(ramp_delay))
    return base


def _start_heater_channels(heater_pins, pwm_freq, duty_scale=None):
    duty_scale = duty_scale or HEATER_DUTY_SCALE
    GPIO.setmode(GPIO.BCM)
    channels = []
    for pin in heater_pins:
        pin = int(pin)
        GPIO.setup(pin, GPIO.OUT)
        pwm = GPIO.PWM(pin, int(pwm_freq))
        pwm.start(0)
        channels.append(
            {
                "pin": pin,
                "pwm": pwm,
                "scale": float(duty_scale.get(pin, 1.0)),
                "duty": 0.0,
            }
        )
    return channels


def _stop_heater_channels(channels):
    for ch in channels:
        try:
            ch["pwm"].ChangeDutyCycle(0)
            ch["pwm"].stop()
        except Exception:
            pass


def _format_heater_duties(channels):
    return ", ".join(f"GPIO{ch['pin']}={ch['duty']:.1f}%" for ch in channels)


def Start_incubation(
    target_temp_c,
    duration_minutes,
    poll_seconds=2.0,
    on_tick=None,
    heater_pins=None,
    pwm_pin=None,
    heater_duty_scale=None,
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

    Both heaters use the same DS18B20 reading and PID output. The upper heater
    (GPIO 26 / pin 37) receives 30% more duty than the lower (GPIO 12 / pin 32).

    Args:
        target_temp_c: target temperature in Celsius.
        duration_minutes: how long to maintain incubation.
        heater_pins: BCM pin tuple for BTS PWM inputs (default lower + upper).
        pwm_pin: legacy single-pin alias; ignored when heater_pins is set.
        heater_duty_scale: optional dict {bcm_pin: multiplier} overriding defaults.
        pwm_freq: PWM frequency in Hz.
        kp, ki, kd: PID gains.
        max_duty: safety cap per heater duty cycle (%).
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

    scale_map = dict(HEATER_DUTY_SCALE)
    if heater_duty_scale:
        scale_map.update({int(k): float(v) for k, v in heater_duty_scale.items()})

    print(
        f"[Incubation] Start PID: target={target_temp_c:.2f}C, duration={duration_minutes} min"
    )
    scale_desc = ", ".join(
        f"GPIO{p}×{scale_map.get(p, 1.0):g}" for p in heater_pins
    )
    print(
        f"[Incubation] Heater PWM pins={heater_pins}, duty scale: {scale_desc}, "
        f"freq={int(pwm_freq)}Hz, PID(Kp={kp}, Ki={ki}, Kd={kd}), max_duty={max_duty:.1f}%"
    )

    heater_channels = _start_heater_channels(heater_pins, pwm_freq, scale_map)

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
                heater_channels,
                current_base=current_duty,
                target_base=requested_duty,
                max_duty=max_duty,
                ramp_step=ramp_step,
                ramp_delay=ramp_delay,
            )
            print(
                f"[Incubation] {temp_c:.2f}C -> base {current_duty:.1f}% "
                f"({_format_heater_duties(heater_channels)})"
            )
            _notify_tick(temp_c)
            time.sleep(poll_seconds)
    finally:
        _stop_heater_channels(heater_channels)
        print("[Incubation] Completed. All heaters OFF.")


def keep_temperature_pid(temperature_to_keep_c, minutes, **kwargs):
    """
    Convenience wrapper for main usage.

    Example:
        keep_temperature_pid(37.0, 60)  # keep 37C for 60 minutes
    """
    return Start_incubation(temperature_to_keep_c, minutes, **kwargs)


