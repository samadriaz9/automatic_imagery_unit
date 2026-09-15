import glob
import os
import time
import RPi.GPIO as GPIO

try:
    from simple_pid import PID
except Exception:
    PID = None


LOWER_HEATER_PIN = 12  # BCM 12, physical pin 32
UPPER_HEATER_PIN = 26  # BCM 26, physical pin 37
UPPER_HEATER_DUTY_BOOST = 1.60  # upper runs 60% hotter than lower (same PID base)
LOWER_HEATER_OFF_REMAINING_MIN = 4.0  # last N min: lower off, upper only until incubation ends
# Once sample is this many °C below target, lower stays off (upper finishes ramp / hold).
# Example: target 37 °C → lower off from 29 °C onward to reduce lid vapour.
LOWER_HEATER_OFF_BELOW_TARGET_C = 8.0
HEATER_DUTY_SCALE = {
    LOWER_HEATER_PIN: 1.0,
    UPPER_HEATER_PIN: UPPER_HEATER_DUTY_BOOST,
}
DEFAULT_HEATER_PINS = (LOWER_HEATER_PIN, UPPER_HEATER_PIN)
# Legacy alias (first / lower heater)
RPWM_PIN = LOWER_HEATER_PIN

_held_upper_channels = []
# Reuse PWM objects across rounds. Recreating RPi.GPIO.PWM after pwm.stop()
# glitches nearby GPIO and often drops the DS18B20 1-Wire slave until restart.
_pwm_by_pin = {}
_cached_ds18b20_path = None
DS18B20_READ_RETRIES = 8
DS18B20_RETRY_DELAY_S = 0.25
DS18B20_MAX_CONSECUTIVE_FAILS = 5


def _stop_channel(ch, destroy=False):
    try:
        ch["pwm"].ChangeDutyCycle(0)
        ch["duty"] = 0.0
        if destroy:
            ch["pwm"].stop()
    except Exception:
        pass
    if destroy:
        _pwm_by_pin.pop(ch.get("pin"), None)


def release_incubation_heaters(destroy=False):
    """Turn off heaters. Keep PWM objects unless destroy=True (process shutdown)."""
    global _held_upper_channels
    channels = list(_pwm_by_pin.values())
    if not channels and not _held_upper_channels:
        return
    for ch in channels:
        _stop_channel(ch, destroy=destroy)
    _held_upper_channels = []
    if destroy:
        print("[Incubation] Heaters PWM stopped.")
    else:
        print("[Incubation] Heaters OFF (PWM kept for next round).")


def _stop_heater_channels(channels, pins_to_stop=None, destroy=False):
    stop_pins = pins_to_stop
    if stop_pins is None:
        stop_pins = {ch["pin"] for ch in channels}
    for ch in channels:
        if ch["pin"] in stop_pins:
            _stop_channel(ch, destroy=destroy)


def _trigger_w1_search():
    """Ask the kernel 1-Wire master to rescan; DS18B20 can drop after PWM/motor/USB noise."""
    for path in glob.glob("/sys/bus/w1/devices/w1_bus_master*/w1_master_search"):
        try:
            with open(path, "w", encoding="ascii") as f:
                f.write("1\n")
        except OSError:
            pass


def _resolve_ds18b20_path(sensor_glob):
    global _cached_ds18b20_path
    if _cached_ds18b20_path and os.path.exists(_cached_ds18b20_path):
        return _cached_ds18b20_path
    paths = sorted(glob.glob(sensor_glob))
    if not paths:
        _cached_ds18b20_path = None
        return None
    _cached_ds18b20_path = paths[0]
    return _cached_ds18b20_path


def _read_ds18b20_once(path):
    with open(path, "r", encoding="utf-8") as f:
        lines = f.read().strip().splitlines()

    if len(lines) < 2 or not lines[0].strip().endswith("YES"):
        raise RuntimeError("DS18B20 CRC invalid (first line does not end with YES)")

    marker = "t="
    if marker not in lines[1]:
        raise RuntimeError("DS18B20 temperature token 't=' not found")

    milli_c = int(lines[1].split(marker, 1)[1])
    return milli_c / 1000.0


def _read_ds18b20_c(
    sensor_glob="/sys/bus/w1/devices/28-*/w1_slave",
    retries=DS18B20_READ_RETRIES,
    retry_delay=DS18B20_RETRY_DELAY_S,
):
    """
    Read DS18B20 temperature in Celsius from w1 sysfs.
    Retries CRC misses and a vanished sysfs node (common after imaging / PWM restart).
    Raises RuntimeError if the sensor is still missing or invalid after retries.
    """
    global _cached_ds18b20_path
    last_err = None
    searched = False
    attempts = max(1, int(retries))
    for attempt in range(attempts):
        path = _resolve_ds18b20_path(sensor_glob)
        if not path:
            last_err = RuntimeError(
                "DS18B20 not found under /sys/bus/w1/devices/28-*/w1_slave"
            )
            if not searched:
                print("[Incubation] DS18B20 missing — triggering 1-Wire bus search")
                _trigger_w1_search()
                searched = True
                _cached_ds18b20_path = None
            time.sleep(float(retry_delay))
            continue
        try:
            return _read_ds18b20_once(path)
        except (OSError, RuntimeError, ValueError) as exc:
            last_err = exc
            if isinstance(exc, OSError):
                _cached_ds18b20_path = None
                if not searched:
                    print("[Incubation] DS18B20 sysfs error — triggering 1-Wire bus search")
                    _trigger_w1_search()
                    searched = True
            if attempt + 1 < attempts:
                time.sleep(float(retry_delay))
    raise RuntimeError(
        f"DS18B20 read failed after {attempts} tries: {last_err}"
    ) from last_err


def _ensure_ds18b20_ready(sensor_glob="/sys/bus/w1/devices/28-*/w1_slave"):
    """Rescan 1-Wire if the slave vanished after imaging / heater PWM."""
    global _cached_ds18b20_path
    if _resolve_ds18b20_path(sensor_glob):
        return
    print("[Incubation] DS18B20 not on bus — searching 1-Wire (can happen after imaging)")
    _cached_ds18b20_path = None
    _trigger_w1_search()
    for _ in range(12):
        time.sleep(0.5)
        if _resolve_ds18b20_path(sensor_glob):
            print(f"[Incubation] DS18B20 restored: {_cached_ds18b20_path}")
            return


def _apply_heater_duties(channels, base, max_duty, lower_active=True):
    for ch in channels:
        if ch["pin"] == LOWER_HEATER_PIN and not lower_active:
            level = 0.0
        else:
            heater_max = min(100.0, float(max_duty) * float(ch["scale"]))
            level = max(0.0, min(heater_max, float(base) * ch["scale"]))
        ch["pwm"].ChangeDutyCycle(level)
        ch["duty"] = level


def _set_heaters_duty_smooth(
    channels, current_base, target_base, max_duty, ramp_step, ramp_delay, lower_active=True
):
    """Ramp PID base duty; each heater gets base * its scale (capped at max_duty * scale)."""
    target_base = max(0.0, min(float(max_duty), float(target_base)))
    base = float(current_base)
    if abs(target_base - base) < 0.001:
        _apply_heater_duties(channels, base, max_duty, lower_active)
        return base

    direction = 1.0 if target_base > base else -1.0
    step = abs(float(ramp_step)) * direction
    while (direction > 0 and base < target_base) or (direction < 0 and base > target_base):
        base += step
        if direction > 0 and base > target_base:
            base = target_base
        if direction < 0 and base < target_base:
            base = target_base
        _apply_heater_duties(channels, base, max_duty, lower_active)
        time.sleep(float(ramp_delay))
    return base


def _start_heater_channels(heater_pins, pwm_freq, duty_scale=None):
    duty_scale = duty_scale or HEATER_DUTY_SCALE
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    channels = []
    created = False
    for pin in heater_pins:
        pin = int(pin)
        scale = float(duty_scale.get(pin, 1.0))
        existing = _pwm_by_pin.get(pin)
        if existing is not None:
            existing["scale"] = scale
            channels.append(existing)
            continue
        GPIO.setup(pin, GPIO.OUT)
        pwm = GPIO.PWM(pin, int(pwm_freq))
        pwm.start(0)
        ch = {
            "pin": pin,
            "pwm": pwm,
            "scale": scale,
            "duty": 0.0,
        }
        _pwm_by_pin[pin] = ch
        channels.append(ch)
        created = True
    if created:
        # Let 1-Wire recover after GPIO PWM is first attached.
        time.sleep(0.3)
    return channels


def _stop_heater_channels_all(channels):
    _stop_heater_channels(channels)


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
    lower_off_remaining_min=None,
    lower_off_below_target_c=None,
    keep_upper_heater_on_exit=False,
):
    """
    Maintain incubation temperature using PID + one or more BTS PWM heater outputs.

    Both heaters use the same DS18B20 reading and PID output. The upper heater
    (GPIO 26 / pin 37) receives 60% more duty than the lower (GPIO 12 / pin 32).

    Lower heater is switched off (upper only) when either:
    - temperature reaches ``target - lower_off_below_target_c`` (default 8 °C),
      then stays off for the rest of this incubation to reduce lid vapour; or
    - the last ``lower_off_remaining_min`` minutes of the hold.

    If ``keep_upper_heater_on_exit`` is True, the upper heater stays on at the
    last PID duty after incubation (for imaging). Call ``release_incubation_heaters()``
    when heating should stop.

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
        lower_off_remaining_min: minutes before end to disable lower heater (default 4).
        lower_off_below_target_c: turn lower off once temp >= target minus this
            (default 8). Set 0 or less to disable the temperature cutoff.
        keep_upper_heater_on_exit: keep upper heater PWM on after incubation ends.
        on_tick: optional callback(elapsed_s, remaining_s, temp_c, target_temp_c).
    """
    global _held_upper_channels
    # Zero duty only — do not pwm.stop(); recreating PWM drops DS18B20 on later rounds.
    release_incubation_heaters(destroy=False)
    target_temp_c = float(target_temp_c)
    duration_s = max(0.0, float(duration_minutes) * 60.0)
    poll_seconds = max(0.2, float(poll_seconds))
    max_duty = max(1.0, min(100.0, float(max_duty)))
    if lower_off_remaining_min is None:
        lower_off_remaining_min = LOWER_HEATER_OFF_REMAINING_MIN
    lower_off_remaining_s = max(0.0, float(lower_off_remaining_min) * 60.0)
    if lower_off_below_target_c is None:
        lower_off_below_target_c = LOWER_HEATER_OFF_BELOW_TARGET_C
    lower_off_below_target_c = float(lower_off_below_target_c)
    use_temp_cutoff = lower_off_below_target_c > 0
    lower_off_threshold_c = target_temp_c - lower_off_below_target_c

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
    cutoff_desc = (
        f"lower off at temp>={lower_off_threshold_c:.1f}C "
        f"(target-{lower_off_below_target_c:g}) or <= {lower_off_remaining_min:g} min remain"
        if use_temp_cutoff
        else f"lower off when <= {lower_off_remaining_min:g} min remain"
    )
    print(
        f"[Incubation] Heater PWM pins={heater_pins}, duty scale: {scale_desc}, "
        f"freq={int(pwm_freq)}Hz, PID(Kp={kp}, Ki={ki}, Kd={kd}), max_duty={max_duty:.1f}%, "
        f"{cutoff_desc}"
    )

    heater_channels = _start_heater_channels(heater_pins, pwm_freq, scale_map)
    _ensure_ds18b20_ready()

    pid = None
    i_term = 0.0
    prev_error = 0.0
    current_duty = 0.0
    lower_cutoff_logged = False
    lower_off_near_target = False
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

    last_temp = None
    consecutive_fails = 0

    def _read_temp_or_hold():
        nonlocal last_temp, consecutive_fails
        try:
            temp_c = _read_ds18b20_c(
                retries=DS18B20_READ_RETRIES if last_temp is None else 3
            )
            if consecutive_fails:
                print(
                    f"[Incubation] DS18B20 recovered after {consecutive_fails} "
                    f"failed read(s): {temp_c:.2f}C"
                )
            consecutive_fails = 0
            last_temp = temp_c
            return temp_c
        except RuntimeError as exc:
            consecutive_fails += 1
            print(f"[Incubation] Sensor read failed ({consecutive_fails}): {exc}")
            if last_temp is None or consecutive_fails >= DS18B20_MAX_CONSECUTIVE_FAILS:
                raise
            print(f"[Incubation] Holding last good reading {last_temp:.2f}C")
            return last_temp

    try:
        try:
            _notify_tick(_read_temp_or_hold())
        except RuntimeError as exc:
            print(f"[Incubation] Initial sensor read failed: {exc}")
            _notify_tick(float("nan"))

        while (time.time() - start) < duration_s:
            temp_c = _read_temp_or_hold()
            remaining = max(0.0, duration_s - (time.time() - start))
            use_lower_cutoff = duration_s > lower_off_remaining_s
            lower_active_time = remaining > lower_off_remaining_s if use_lower_cutoff else True
            if use_temp_cutoff and (lower_off_near_target or temp_c >= lower_off_threshold_c):
                if not lower_off_near_target:
                    print(
                        f"[Incubation] {temp_c:.2f}C >= {lower_off_threshold_c:.2f}C "
                        f"(target {target_temp_c:.1f}C - {lower_off_below_target_c:g}) — "
                        "lower heater OFF, upper only to reduce lid vapour"
                    )
                    lower_off_near_target = True
                lower_active_temp = False
            else:
                lower_active_temp = True
            lower_active = lower_active_time and lower_active_temp
            if not lower_active_time and not lower_cutoff_logged:
                print(
                    f"[Incubation] <= {lower_off_remaining_min:g} min remaining — "
                    "lower heater OFF, upper only until incubation ends"
                )
                lower_cutoff_logged = True

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
                lower_active=lower_active,
            )
            print(
                f"[Incubation] {temp_c:.2f}C -> base {current_duty:.1f}% "
                f"({_format_heater_duties(heater_channels)})"
            )
            _notify_tick(temp_c)
            time.sleep(poll_seconds)
    finally:
        global _held_upper_channels
        if keep_upper_heater_on_exit:
            _stop_heater_channels(heater_channels, pins_to_stop={LOWER_HEATER_PIN})
            upper_ch = next(
                (ch for ch in heater_channels if ch["pin"] == UPPER_HEATER_PIN), None
            )
            if upper_ch and upper_ch["duty"] > 0:
                _held_upper_channels = [upper_ch]
                print(
                    f"[Incubation] Completed. Upper heater held ON at "
                    f"{upper_ch['duty']:.1f}% for imaging."
                )
            else:
                _stop_heater_channels_all(heater_channels)
                print("[Incubation] Completed. All heaters OFF.")
        else:
            _stop_heater_channels_all(heater_channels)
            print("[Incubation] Completed. All heaters OFF.")


def keep_temperature_pid(temperature_to_keep_c, minutes, **kwargs):
    """
    Convenience wrapper for main usage.

    Example:
        keep_temperature_pid(37.0, 60)  # keep 37C for 60 minutes
    """
    return Start_incubation(temperature_to_keep_c, minutes, **kwargs)


