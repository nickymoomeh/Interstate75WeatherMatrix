"""Open-Meteo weather source for the standalone Interstate 75 matrix.

The display code should not need to understand the Open-Meteo response format.
This module fetches weather data and translates it into the small, stable set
of fields used by the matrix.

Keeping this boundary separate makes it easier to:
- change weather providers later;
- test parsing without touching animation code;
- keep network failures from breaking the display loop;
- document exactly where each displayed value comes from.
"""

import urequests

from config import LATITUDE, LONGITUDE, TIMEZONE, TEMPERATURE_UNIT


OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

# Validate once at import time so a typo in config.py fails clearly instead of
# silently displaying values in an unexpected unit.
DISPLAY_TEMPERATURE_UNIT = str(TEMPERATURE_UNIT).upper()
if DISPLAY_TEMPERATURE_UNIT not in ("C", "F"):
    raise ValueError('TEMPERATURE_UNIT must be "C" or "F"')

OPEN_METEO_TEMPERATURE_UNIT = (
    "fahrenheit" if DISPLAY_TEMPERATURE_UNIT == "F" else "celsius"
)

# These thresholds mirror the pressure-trend behaviour in the original
# sensor-backed version of the display. The cold threshold has the same
# physical meaning in either temperature unit.
PRESSURE_SLOW_THRESHOLD = 0.5
PRESSURE_FAST_THRESHOLD = 2.0
COLD_THRESHOLD = 37.4 if DISPLAY_TEMPERATURE_UNIT == "F" else 3.0


def _safe_float(value, default=None):
    """Return value as float, or default when an API field is absent/invalid."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _classify_pressure_trend(change_hpa):
    """Convert a three-hour pressure change into the label used by the UI."""
    if change_hpa is None:
        return "unknown"
    if change_hpa >= PRESSURE_FAST_THRESHOLD:
        return "rising_fast"
    if change_hpa >= PRESSURE_SLOW_THRESHOLD:
        return "rising_slow"
    if change_hpa <= -PRESSURE_FAST_THRESHOLD:
        return "falling_fast"
    if change_hpa <= -PRESSURE_SLOW_THRESHOLD:
        return "falling_slow"
    return "steady"


def _query_url():
    """Build the compact Open-Meteo request used by the Pico W.

    Daily minimum/maximum values are forecast/model values for the whole day,
    not the minimum/maximum observed by a physical sensor so far today.
    Open-Meteo returns temperature fields directly in the configured unit.
    """
    current = (
        "temperature_2m,relative_humidity_2m,pressure_msl,"
        "precipitation,rain,showers,snowfall,weather_code,"
        "wind_speed_10m,wind_direction_10m,wind_gusts_10m"
    )
    hourly = "pressure_msl,precipitation_probability"
    daily = "temperature_2m_min,temperature_2m_max,sunrise,sunset"

    return (
        OPEN_METEO_URL
        + "?latitude=" + str(LATITUDE)
        + "&longitude=" + str(LONGITUDE)
        + "&current=" + current
        + "&hourly=" + hourly
        + "&daily=" + daily
        + "&temperature_unit=" + OPEN_METEO_TEMPERATURE_UNIT
        + "&forecast_days=1"
        + "&past_hours=3"
        + "&timezone=" + TIMEZONE.replace("/", "%2F")
    )


def _value_at_current_hour(payload, field_name):
    """Return an hourly value aligned with Open-Meteo's current hour."""
    current = payload.get("current") or {}
    current_time = current.get("time")
    hourly = payload.get("hourly") or {}
    times = hourly.get("time") or []
    values = hourly.get(field_name) or []

    if not current_time:
        return None

    target = current_time[:13] + ":00"
    try:
        index = times.index(target)
        return values[index]
    except (ValueError, IndexError):
        return None


def _pressure_change_3h(payload):
    """Estimate the three-hour mean-sea-level pressure tendency.

    Open-Meteo supplies recent hourly pressure values, so the Pico does not
    need to retain its own three-hour pressure history across refreshes.
    """
    hourly = payload.get("hourly") or {}
    times = hourly.get("time") or []
    pressures = hourly.get("pressure_msl") or []
    current = payload.get("current") or {}
    current_time = current.get("time")

    if not current_time or not times or not pressures:
        return None

    target_hour = current_time[:13] + ":00"
    try:
        current_index = times.index(target_hour)
    except ValueError:
        return None

    old_index = current_index - 3
    if old_index < 0:
        return None

    try:
        latest = float(pressures[current_index])
        previous = float(pressures[old_index])
    except (IndexError, TypeError, ValueError):
        return None

    return round(latest - previous, 1)


def fetch_weather(timeout_seconds=8):
    """Fetch and normalize one Open-Meteo update.

    The returned dictionary deliberately uses the same field names as the
    original Pi/sensor-backed display wherever practical. Keeping this small
    compatibility contract means the rendering and animation code does not
    care where its weather came from. The historical ``*_temperature_c`` key
    names are retained for that compatibility even when Fahrenheit is selected;
    ``temperature_unit`` states which unit the numeric values actually use.

    Raises an exception on network/HTTP/JSON failure. The caller should retain
    the previous successful weather data and try again at the next refresh.
    """
    response = None
    try:
        response = urequests.get(_query_url(), timeout=timeout_seconds)
        if response.status_code != 200:
            raise RuntimeError("Open-Meteo HTTP " + str(response.status_code))
        payload = response.json()
    finally:
        if response is not None:
            response.close()

    current = payload.get("current") or {}
    daily = payload.get("daily") or {}

    if not current.get("time"):
        raise ValueError("Open-Meteo response has no current conditions")

    temperature = _safe_float(current.get("temperature_2m"))
    pressure_change = _pressure_change_3h(payload)
    weather_code = current.get("weather_code")

    # WMO codes 95, 96 and 99 indicate thunderstorm conditions. This is a
    # model/forecast indication only; unlike the home version there is no
    # physical lightning receiver detecting individual nearby strikes.
    storm_warning = weather_code in (95, 96, 99)

    def first_daily(name):
        values = daily.get(name) or []
        return values[0] if values else None

    try:
        utc_offset_seconds = int(payload.get("utc_offset_seconds", 0))
    except (TypeError, ValueError):
        utc_offset_seconds = 0

    return {
        "data_ok": True,
        "forecast_ok": True,
        "temperature_c": temperature,
        "temperature_unit": DISPLAY_TEMPERATURE_UNIT,
        "humidity": _safe_float(current.get("relative_humidity_2m")),
        "min_temperature_c": _safe_float(first_daily("temperature_2m_min")),
        "max_temperature_c": _safe_float(first_daily("temperature_2m_max")),
        "is_cold": temperature is not None and temperature <= COLD_THRESHOLD,
        "pressure_hpa": _safe_float(current.get("pressure_msl")),
        "pressure_change_3h": pressure_change,
        "pressure_trend": _classify_pressure_trend(pressure_change),
        "storm_warning": storm_warning,
        # Open-Meteo calculates this for the requested IANA timezone, including
        # daylight-saving changes. main.py uses it to turn NTP's UTC clock into
        # the local wall clock without carrying country-specific DST rules.
        "utc_offset_seconds": utc_offset_seconds,
        # Keep the original names so draw_warning_edges() can remain unchanged.
        # They are always zero because Open-Meteo does not provide immediate
        # strike detections comparable with the FineOffset lightning sensor.
        "lightning_strikes_last_5_min": 0,
        "lightning_strikes_last_hour": 0,
        "forecast_time": current.get("time"),
        "precipitation_mm": _safe_float(current.get("precipitation"), 0.0),
        "precipitation_probability": _safe_float(
            _value_at_current_hour(payload, "precipitation_probability")
        ),
        "rain_mm": _safe_float(current.get("rain"), 0.0),
        "showers_mm": _safe_float(current.get("showers"), 0.0),
        "snowfall_cm": _safe_float(current.get("snowfall"), 0.0),
        "weather_code": weather_code,
        "wind_speed_kmh": _safe_float(current.get("wind_speed_10m")),
        "wind_gust_kmh": _safe_float(current.get("wind_gusts_10m")),
        "wind_direction_deg": _safe_float(current.get("wind_direction_10m")),
        "sunrise_time": first_daily("sunrise"),
        "sunset_time": first_daily("sunset"),
    }
