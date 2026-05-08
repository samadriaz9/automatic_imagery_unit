import glob
import time
import RPi.GPIO as GPIO

try:
    from simple_pid import PID
except Exception:
    PID = None


RPWM_PIN = 12  # BCM 12, physical pin 32 (heater BTS PWM input)


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


def _set_heater_duty_smooth(pwm, current_duty, target_duty, max_duty, ramp_step, ramp_delay):
    """Ramp duty cycle gradually to avoid aggressive heater switching."""
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
        pwm.ChangeDutyCycle(max(0.0, min(float(max_duty), duty)))
        time.sleep(float(ramp_delay))
    return duty


def Start_incubation(
    target_temp_c,
    duration_minutes,
    poll_seconds=1.0,
    pwm_pin=RPWM_PIN,
    pwm_freq=1000,
    kp=10.0,
    ki=0.2,
    kd=2.0,
    max_duty=50.0,
    # For precise control, ramp in small PWM duty increments.
    ramp_step=0.1,
    ramp_delay=0.05,
):
    """
    Maintain incubation temperature using PID + BTS PWM heater output.

    Args:
        target_temp_c: target temperature in Celsius.
        duration_minutes: how long to maintain incubation.
        pwm_pin: BCM pin used as BTS PWM input (heater channel).
        pwm_freq: PWM frequency in Hz.
        kp, ki, kd: PID gains.
        max_duty: safety cap for heater duty cycle (%).
        ramp_step/ramp_delay: soft-ramp behavior to reduce thermal overshoot.
        poll_seconds: sensor polling interval.
    """
    target_temp_c = float(target_temp_c)
    duration_s = max(0.0, float(duration_minutes) * 60.0)
    poll_seconds = max(0.2, float(poll_seconds))
    max_duty = max(1.0, min(100.0, float(max_duty)))

    print(
        f"[Incubation] Start PID: target={target_temp_c:.2f}C, duration={duration_minutes} min"
    )
    print(
        f"[Incubation] Heater PWM pin={int(pwm_pin)}, freq={int(pwm_freq)}Hz, "
        f"PID(Kp={kp}, Ki={ki}, Kd={kd}), max_duty={max_duty:.1f}%"
    )

    GPIO.setmode(GPIO.BCM)
    GPIO.setup(int(pwm_pin), GPIO.OUT)
    heater_pwm = GPIO.PWM(int(pwm_pin), int(pwm_freq))
    heater_pwm.start(0)

    pid = None
    i_term = 0.0
    prev_error = 0.0
    current_duty = 0.0
    if PID is not None:
        pid = PID(float(kp), float(ki), float(kd), setpoint=target_temp_c)
        pid.output_limits = (0.0, max_duty)
        # Run PID update at same cadence as sensor polling (for consistency).
        try:
            pid.sample_time = float(poll_seconds)
        except Exception:
            pass

    start = time.time()

    try:
        while (time.time() - start) < duration_s:
            temp_c = _read_ds18b20_c()
            if pid is not None:
                requested_duty = float(pid(temp_c))
            else:
                # Fallback PID when simple_pid is unavailable.
                error = target_temp_c - temp_c
                i_term += error * poll_seconds
                d_term = (error - prev_error) / poll_seconds
                prev_error = error
                raw = (float(kp) * error) + (float(ki) * i_term) + (float(kd) * d_term)
                requested_duty = max(0.0, min(max_duty, raw))

            current_duty = _set_heater_duty_smooth(
                heater_pwm,
                current_duty=current_duty,
                target_duty=requested_duty,
                max_duty=max_duty,
                ramp_step=ramp_step,
                ramp_delay=ramp_delay,
            )
            print(f"[Incubation] {temp_c:.2f}C -> heater {current_duty:.1f}%")

            time.sleep(poll_seconds)
    finally:
        # Safety: always leave heater OFF on function exit/error.
        try:
            heater_pwm.ChangeDutyCycle(0)
            heater_pwm.stop()
        except Exception:
            pass
        print("[Incubation] Completed. Heater OFF.")


def keep_temperature_pid(temperature_to_keep_c, minutes, **kwargs):
    """
    Convenience wrapper for main usage.

    Example:
        keep_temperature_pid(37.0, 60)  # keep 37C for 60 minutes
    """
    return Start_incubation(temperature_to_keep_c, minutes, **kwargs)

