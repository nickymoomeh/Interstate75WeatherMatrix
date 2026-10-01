"""Standalone horizontally chained weather matrix for the Pimoroni Interstate 75 W.

The rendering and animation code is intentionally kept close to the original
sensor-backed display so the standalone edition looks and behaves the same.
Weather acquisition is isolated in weather_source.py and static pixel artwork
lives in sprites.py.

Normal users should only need to edit config.py and create secrets.py.
"""

from interstate75 import Interstate75, SWITCH_A
import interstate75
import time
from network_recovery import Recovery
from ambient_motion import UIDrift, start_fish_motion, move_fish, CLOUD_ROWS, FIN_ROWS, compile_glyph_runs, rainbow_profile
import gc

from secrets import WIFI_SSID, WIFI_PASSWORD
from config import (
    SCREEN_COUNT,
    AMBIENT_ACTIVITY,
    UI_DRIFT_MINUTES,
    WIND_LEAF_THRESHOLD_KMH,
    TIMEZONE,
    TEMPERATURE_UNIT,
    CLOCK_FORMAT,
    WEATHER_REFRESH_SECONDS,
    TARGET_FRAME_MS,
    NIGHT_DIM_FACTOR,
    PERFORMANCE_LOGGING,
)
from weather_source import fetch_weather
from sprites import (
    FISH_COLOURS, FISH_ACCENTS, FISH_WIDTHS, FISH_HEIGHTS, FISH_TAIL_SHIFT,
    FESTIVE_COLOURS, FESTIVE_BRIGHT,
    UFO_WIDTHS, UFO_DOMES, UFO_ROWS, UFO_LIGHTS, UFO_LIGHT_Y, UFO_BEAM_Y,
    UFO_COLOURS, UFO_DIM_LIGHTS, UFO_DAY_LIGHTS,
    FESTIVE_UFO_COLOURS, FESTIVE_UFO_DIM_LIGHTS, FESTIVE_UFO_DAY_LIGHTS,
    UFO_BOB,
    BIRD_COLOURS, BIRD_PECK_BODY, BIRD_BODY, BIRD_WING_FRAMES,
    BIRD_WING_SEQUENCE,
    DUCK_BODY, DUCK_HEAD, DUCK_WING, DUCK_BILL, DUCKLING_BODY,
    DUCKLING_BILL, DUCK_COLOURS, DUCK_FAMILY_WIDTH,
    FESTIVE_FAMILY_WIDTH, SANTA_RED, SANTA_WHITE, SANTA_SKIN,
    SLEIGH_RED, SLEIGH_GOLD, REINDEER_BODY, REINDEER_ANTLERS,
    ABDUCTION_COLOURS, ABDUCTION_DIM_LIGHTS, ABDUCTION_BEAM_SHADES,
    ABDUCTION_DAY_LIGHTS, ABDUCTION_DAY_BEAM_SHADES,
    LEAF_FRAMES, LEAF_FRAME_SEQUENCE,
)

# Give the power supply and HUB75 panel a moment to settle after boot.
time.sleep(3)


# ---------------------------------------------------------------------------
# Runtime settings and animation timing
# ---------------------------------------------------------------------------

DEMO_REFRESH_SECONDS = 2
DEMO_MODE = False

PULSE_DURATION_MS = 1500
STORM_PULSE_PERIOD_MS = 1800
LIGHTNING_PULSE_PERIOD_MS = 2400
ACCUMULATION_STEP_MS = 30000
ACCUMULATION_DRAIN_MS = 60000

DISPLAY_TEMPERATURE_UNIT = str(TEMPERATURE_UNIT).upper()
if DISPLAY_TEMPERATURE_UNIT not in ("C", "F"):
    raise ValueError('TEMPERATURE_UNIT must be "C" or "F"')
try:
    DISPLAY_CLOCK_FORMAT = int(CLOCK_FORMAT)
except (TypeError, ValueError):
    raise ValueError("CLOCK_FORMAT must be 12 or 24")
if DISPLAY_CLOCK_FORMAT not in (12, 24):
    raise ValueError("CLOCK_FORMAT must be 12 or 24")


# ---------------------------------------------------------------------------
# Display and runtime state
# ---------------------------------------------------------------------------

if type(SCREEN_COUNT) is not int or not 1 <= SCREEN_COUNT <= 4:
    raise ValueError("SCREEN_COUNT must be an integer from 1 to 4")
WIDTH = 64 * SCREEN_COUNT
HEIGHT = 64
RAINBOW_DURATION_MS = 6000
RAINBOW_COLOURS = ((52, 8, 8), (52, 24, 4), (48, 40, 4), (6, 40, 12),
                   (6, 25, 52), (19, 10, 42), (38, 9, 42))
RAINBOW_ROWS = rainbow_profile(WIDTH, HEIGHT)
RAINBOW = {"start_ms": None, "last_key": None}
try:
    display_mode = getattr(interstate75, "DISPLAY_INTERSTATE75_{}X64".format(WIDTH))
except AttributeError:
    raise RuntimeError("Install Interstate75 firmware supporting {}x64".format(WIDTH))
i75 = Interstate75(display=display_mode)
if i75.display.get_bounds() != (WIDTH, HEIGHT):
    raise RuntimeError("Unexpected framebuffer dimensions")
# Preserve the 60-pixel single-panel platform; add scenery without full-width bars.
BAR_WIDTH = 60 + (WIDTH - 64) * 3 // 4
BAR_LEFT = (WIDTH - BAR_WIDTH) // 2
UI_SHIFT = (WIDTH - 64) // 2
UI_DRIFT = UIDrift(UI_DRIFT_MINUTES * 60000)
BIRD_LIMIT = 3 if SCREEN_COUNT > 1 and AMBIENT_ACTIVITY else 1
UFO_LIMIT = 2 if SCREEN_COUNT > 1 and AMBIENT_ACTIVITY else 1
FISH_LIMIT = 2 if SCREEN_COUNT > 1 and AMBIENT_ACTIVITY else 1
graphics = i75.display

BLACK = graphics.create_pen(0, 0, 0)
WARM_PULSE_RGB = (180, 115, 35)

# Pens are relatively expensive to create on every frame. Static colours are
# cached separately for daytime and dimmed night mode.
PEN_CACHE = ({}, {})

# NTP keeps the Pico clock in UTC. Open-Meteo returns utc_offset_seconds for
# the configured IANA timezone, so this works outside the UK and follows DST
# without embedding country-specific clock-change rules in the firmware.
LOCAL_TIME_CACHE = {
    "epoch_second": None,
    "utc_offset_seconds": 0,
    "parts": (2000, 1, 1, 0, 0, 0, 0, 1),
    "clock_text": "--:--",
    "night": False,
    "festive": False,
}
SUN_EVENT_CACHE = {"sunrise": None, "sunset": None, "minutes": (None, None)}
PERF_STATS = {
    "started_ms": 0, "frames": 0, "frame_total_ms": 0,
    "frame_max_ms": 0, "update_total_ms": 0, "update_max_ms": 0,
    "overruns": 0, "last_fetch_ms": 0,
}
GROUND_STATE = {"kind": None, "level": 0, "last_ms": 0}
FISH_STATE = {
    "active": False,
    "next_ms": 0,
    "start_ms": 0,
    "right": True,
    "y": 55,
    "colour": 0,
    "species": 0,
    "travel_ms": 10000,
}
SHOOTING_STAR = {"active": False, "next_ms": 0, "start_ms": 0, "right": True, "y": 8}
UFO_STATE = {
    "active": False, "next_ms": 0, "start_ms": 0, "right": True,
    "y": 8, "colour": 0, "style": 0, "mode": 0,
    "duration_ms": 6000, "hover_x": 28, "daylight": False, "festive": False,
}
DAY_CREATURE = {
    "active": False, "next_ms": 0, "start_ms": 0, "kind": "bird",
    "species": 0, "perch": 16, "right": True, "duration_ms": 10000,
    "interact": False, "interaction_done": False, "interaction_start_ms": 0,
    "turnaround": False,
}
ABDUCTION = {"active": False, "start_ms": 0, "last_key": None, "colour": 0}
FESTIVE_BUTTON = {"previous": False, "manual": None, "last_ms": 0}
# Independent state only; sprites, palettes and framebuffer remain shared.
BIRD_STATES = tuple(dict(DAY_CREATURE) for _ in range(BIRD_LIMIT))
UFO_STATES = tuple(dict(UFO_STATE) for _ in range(UFO_LIMIT))
FISH_STATES = tuple(dict(FISH_STATE) for _ in range(FISH_LIMIT))
for pool in (BIRD_STATES, UFO_STATES, FISH_STATES):
    for slot, state in enumerate(pool):
        state["slot"] = slot
DAY_CREATURE, UFO_STATE, FISH_STATE = BIRD_STATES[0], UFO_STATES[0], FISH_STATES[0]
SURFACE_EVENT = {"active": False, "next_ms": 0, "start_ms": 0, "kind": "fin", "right": True}
CLOUD_STATE = {"active": False, "next_ms": 0, "start_ms": 0, "right": True, "y": 6, "duration_ms": 45000}



# ---------------------------------------------------------------------------
# Basic helpers
# ---------------------------------------------------------------------------

def clear_screen():
    graphics.set_pen(BLACK)
    graphics.clear()


def show_message(line1, line2=""):
    clear_screen()
    graphics.set_pen(pen_white())
    graphics.text(line1, 2, 18, scale=1)
    if line2:
        graphics.text(line2, 2, 32, scale=1)
    i75.update(graphics)


def clamp(value, low, high):
    if value < low:
        return low
    if value > high:
        return high
    return value


def safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def is_night_time():
    return LOCAL_TIME_CACHE["night"]


def night_adjust_rgb(rgb):
    factor = NIGHT_DIM_FACTOR if LOCAL_TIME_CACHE["night"] else 1.0
    return (
        int(rgb[0] * factor),
        int(rgb[1] * factor),
        int(rgb[2] * factor),
    )


def make_pen(rgb):
    adjusted = night_adjust_rgb(rgb)
    return graphics.create_pen(adjusted[0], adjusted[1], adjusted[2])


def cached_pen(rgb):
    cache = PEN_CACHE[1 if LOCAL_TIME_CACHE["night"] else 0]
    pen = cache.get(rgb)
    if pen is None:
        pen = make_pen(rgb)
        cache[rgb] = pen
    return pen


def record_performance(now_ms, frame_ms, update_ms, fetch_ms):
    if not PERFORMANCE_LOGGING:
        return
    stats = PERF_STATS
    if stats["started_ms"] == 0:
        stats["started_ms"] = now_ms
    stats["frames"] += 1
    stats["frame_total_ms"] += frame_ms
    stats["update_total_ms"] += update_ms
    stats["frame_max_ms"] = max(stats["frame_max_ms"], frame_ms)
    stats["update_max_ms"] = max(stats["update_max_ms"], update_ms)
    if frame_ms > TARGET_FRAME_MS:
        stats["overruns"] += 1
    if fetch_ms:
        stats["last_fetch_ms"] = fetch_ms
    if time.ticks_diff(now_ms, stats["started_ms"]) < 10000:
        return
    frames = max(1, stats["frames"])
    print(
        "Perf frames/10s={}, frame avg/max={}/{}, update avg/max={}/{}, overruns={}, fetch={}".format(
            frames,
            stats["frame_total_ms"] // frames,
            stats["frame_max_ms"],
            stats["update_total_ms"] // frames,
            stats["update_max_ms"],
            stats["overruns"],
            stats["last_fetch_ms"],
        )
    )
    stats["started_ms"] = now_ms
    stats["frames"] = 0
    stats["frame_total_ms"] = 0
    stats["frame_max_ms"] = 0
    stats["update_total_ms"] = 0
    stats["update_max_ms"] = 0
    stats["overruns"] = 0


def blend_rgb(start_rgb, end_rgb, amount):
    amount = clamp(amount, 0.0, 1.0)
    return (
        int(start_rgb[0] + (end_rgb[0] - start_rgb[0]) * amount),
        int(start_rgb[1] + (end_rgb[1] - start_rgb[1]) * amount),
        int(start_rgb[2] + (end_rgb[2] - start_rgb[2]) * amount),
    )


def animated_pen(normal_rgb, amount):
    return make_pen(blend_rgb(normal_rgb, WARM_PULSE_RGB, amount))


def change_pulse_amount(elapsed_ms):
    if elapsed_ms < 0 or elapsed_ms >= PULSE_DURATION_MS:
        return 0.0
    progress = elapsed_ms / PULSE_DURATION_MS
    if progress < 0.2:
        return progress / 0.2
    return (1.0 - progress) / 0.8


def storm_pulse_amount(now_ms):
    phase = (now_ms % STORM_PULSE_PERIOD_MS) / STORM_PULSE_PERIOD_MS
    return 1.0 - abs((phase * 2.0) - 1.0)


def lightning_pulse_amount(now_ms):
    phase = (now_ms % LIGHTNING_PULSE_PERIOD_MS) / LIGHTNING_PULSE_PERIOD_MS
    return 1.0 - abs((phase * 2.0) - 1.0)


class PulseTracker:
    """Briefly warm-pulse readings when their displayed value changes."""

    def __init__(self):
        self.previous = {}
        self.started = {}

    def update_display(self, clock, humidity, temperature, minimum, maximum, pressure, now_ms):
        # Avoid allocating a fresh dictionary on every animation frame.
        for name, value in (
            ("clock", clock), ("humidity", humidity),
            ("temperature", temperature), ("min", minimum),
            ("max", maximum), ("pressure", pressure),
        ):
            if name in self.previous and self.previous[name] != value:
                self.started[name] = now_ms
            self.previous[name] = value

    def amount(self, name, now_ms):
        if name not in self.started:
            return 0.0
        elapsed_ms = time.ticks_diff(now_ms, self.started[name])
        return change_pulse_amount(elapsed_ms)


# ---------------------------------------------------------------------------
# Dynamic colour pens
# ---------------------------------------------------------------------------

def pen_white():
    return cached_pen((85, 85, 85))


def pen_secondary():
    return cached_pen((55, 55, 55))


def pen_blue():
    return cached_pen((0, 35, 120))


def pen_red():
    return cached_pen((120, 0, 0))


def pressure_trend_rgb(trend):
    if trend in ("rising_fast", "rising_slow"):
        return (20, 100, 35)
    if trend == "falling_slow":
        return (115, 75, 0)
    if trend == "falling_fast":
        return (120, 25, 0)
    return (85, 85, 85)


def temperature_rgb(value):
    try:
        temp = float(value)
        # Keep the existing colour bands physically identical in Fahrenheit
        # mode by converting only for colour classification.
        if DISPLAY_TEMPERATURE_UNIT == "F":
            temp = (temp - 32.0) * 5.0 / 9.0
    except Exception:
        return (85, 85, 85)

    cold_white = (90, 90, 90)
    blue = (0, 35, 110)
    yellow = (110, 90, 0)
    orange = (120, 45, 0)
    red = (120, 0, 0)
    purple = (90, 0, 100)

    if temp <= 1:
        return cold_white
    if temp <= 3:
        return blue
    if temp <= 14:
        amount = (temp - 3) / 11
        return tuple(int(blue[i] + (yellow[i] - blue[i]) * amount) for i in range(3))
    if temp <= 24:
        amount = (temp - 14) / 10
        return tuple(int(yellow[i] + (orange[i] - yellow[i]) * amount) for i in range(3))
    if temp <= 28:
        amount = (temp - 24) / 4
        return tuple(int(orange[i] + (red[i] - orange[i]) * amount) for i in range(3))
    if temp <= 30:
        return red
    return purple


# ---------------------------------------------------------------------------
# Tiny 3x5 font and pressure arrows
# ---------------------------------------------------------------------------

FONT = {
    "0": ["111", "101", "101", "101", "111"],
    "1": ["010", "110", "010", "010", "111"],
    "2": ["111", "001", "111", "100", "111"],
    "3": ["111", "001", "111", "001", "111"],
    "4": ["101", "101", "111", "001", "001"],
    "5": ["111", "100", "111", "001", "111"],
    "6": ["111", "100", "111", "101", "111"],
    "7": ["111", "001", "001", "001", "001"],
    "8": ["111", "101", "111", "101", "111"],
    "9": ["111", "101", "111", "001", "111"],
    ":": ["0", "1", "0", "1", "0"],
    ".": ["0", "0", "0", "0", "1"],
    "-": ["000", "000", "111", "000", "000"],
    "%": ["101", "001", "010", "100", "101"],
    "A": ["010", "101", "111", "101", "101"],
    "C": ["111", "100", "100", "100", "111"],
    "F": ["111", "100", "110", "100", "100"],
    "H": ["101", "101", "111", "101", "101"],
    "I": ["1", "1", "1", "1", "1"],
    "M": ["101", "111", "111", "101", "101"],
    "N": ["101", "111", "111", "111", "101"],
    "X": ["101", "101", "010", "101", "101"],
    " ": ["0", "0", "0", "0", "0"],
}
GLYPH_WIDTHS = {character: max(len(row) for row in glyph) for character, glyph in FONT.items()}
# Packed once at boot: fewer driver calls and no repeated glyph-bit scanning.
GLYPH_RUNS = compile_glyph_runs(FONT)

ARROWS = {
    "rising_fast": [
        "0001000", "0011100", "0111110", "0001000", "0001000",
        "0001000", "0001000", "0001000", "0001000",
    ],
    "rising_slow": [
        "0001111", "0000011", "0000101", "0001000", "0010000",
        "0100000", "1000000", "0000000", "0000000",
    ],
    "steady": [
        "0000000", "0001000", "0001100", "1111110", "1111111",
        "0001100", "0001000", "0000000", "0000000",
    ],
    "falling_slow": [
        "1000000", "0100000", "0010000", "0001000", "0000101",
        "0000011", "0001111", "0000000", "0000000",
    ],
    "falling_fast": [
        "0001000", "0001000", "0001000", "0001000", "0001000",
        "0111110", "0011100", "0001000", "0000000",
    ],
}


def pixel_text_width(text, scale=1):
    width = 0
    text = str(text).upper()
    for index, character in enumerate(text):
        glyph_width = GLYPH_WIDTHS.get(character, 1)
        width += glyph_width * scale
        if index < len(text) - 1:
            width += scale
    return width


def draw_pixel_text(text, x, y, pen, scale=1):
    cursor_x = x
    text = str(text).upper()
    graphics.set_pen(pen)
    for index, character in enumerate(text):
        runs = GLYPH_RUNS.get(character, GLYPH_RUNS[" "])
        for run in range(0, len(runs), 3):
            graphics.rectangle(cursor_x + runs[run + 1] * scale,
                               y + runs[run] * scale,
                               runs[run + 2] * scale, scale)
        cursor_x += GLYPH_WIDTHS.get(character, 1) * scale
        if index < len(text) - 1:
            cursor_x += scale


def outline_pixel_text(text, x, y, scale=1):
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        draw_pixel_text(text, x + dx, y + dy, BLACK, scale=scale)


def draw_bitmap(bitmap, x, y, pen, thickness=1):
    graphics.set_pen(pen)
    for row_i, row in enumerate(bitmap):
        for col_i, bit in enumerate(row):
            if bit == "1":
                graphics.rectangle(x + col_i, y + row_i, thickness, thickness)


def outline_bitmap(bitmap, x, y, thickness=1):
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        draw_bitmap(bitmap, x + dx, y + dy, BLACK, thickness=thickness)


# ---------------------------------------------------------------------------
# Wi-Fi and local time
# ---------------------------------------------------------------------------

def set_weather_timezone_offset(data):
    """Adopt the UTC offset supplied for the configured Open-Meteo timezone."""
    try:
        offset = int(data.get("utc_offset_seconds"))
    except (TypeError, ValueError):
        return
    if LOCAL_TIME_CACHE["utc_offset_seconds"] != offset:
        LOCAL_TIME_CACHE["utc_offset_seconds"] = offset
        # Force the same UTC second to be recalculated using the new offset.
        LOCAL_TIME_CACHE["epoch_second"] = None


DST_CACHE = {"year": None, "march": None, "october": None}

def is_leap_year(year):
    if year % 400 == 0:
        return True
    if year % 100 == 0:
        return False
    return year % 4 == 0


def days_in_month(year, month):
    if month in [1, 3, 5, 7, 8, 10, 12]:
        return 31
    if month in [4, 6, 9, 11]:
        return 30
    if is_leap_year(year):
        return 29
    return 28


def day_of_week(year, month, day):
    t = time.mktime((year, month, day, 0, 0, 0, 0, 0))
    return time.localtime(t)[6]


def last_sunday(year, month):
    day = days_in_month(year, month)
    while day > 0:
        if day_of_week(year, month, day) == 6:
            return day
        day -= 1
    return 31


def uk_utc_offset_hours(utc=None):
    if utc is None:
        utc = time.localtime()
    year = utc[0]
    month = utc[1]
    day = utc[2]
    hour = utc[3]

    if DST_CACHE["year"] != year:
        DST_CACHE["year"] = year
        DST_CACHE["march"] = last_sunday(year, 3)
        DST_CACHE["october"] = last_sunday(year, 10)
    march_change_day = DST_CACHE["march"]
    october_change_day = DST_CACHE["october"]

    if month < 3 or month > 10:
        return 0
    if month > 3 and month < 10:
        return 1

    if month == 3:
        if day > march_change_day:
            return 1
        if day < march_change_day:
            return 0
        return 1 if hour >= 1 else 0

    if month == 10:
        if day < october_change_day:
            return 1
        if day > october_change_day:
            return 0
        return 0 if hour >= 1 else 1

    return 0


def update_local_time_cache(now_seconds=None):
    try:
        epoch_second = int(time.time() if now_seconds is None else now_seconds)
        if LOCAL_TIME_CACHE["epoch_second"] == epoch_second:
            return
        offset = uk_utc_offset_hours(time.localtime(epoch_second)) * 3600 if TIMEZONE == "Europe/London" else LOCAL_TIME_CACHE["utc_offset_seconds"]
        local = time.localtime(epoch_second + offset)
        hour = local[3]
        minute = local[4]
        previous_epoch = LOCAL_TIME_CACHE["epoch_second"]
        previous_local = LOCAL_TIME_CACHE["parts"]
        LOCAL_TIME_CACHE["epoch_second"] = epoch_second
        LOCAL_TIME_CACHE["parts"] = local
        if previous_epoch is None or minute != previous_local[4] or hour != previous_local[3]:
            if DISPLAY_CLOCK_FORMAT == 12:
                display_hour = hour % 12 or 12
                LOCAL_TIME_CACHE["clock_text"] = "{}:{:02d}".format(display_hour, minute)
            else:
                LOCAL_TIME_CACHE["clock_text"] = "{:02d}:{:02d}".format(hour, minute)
        # Night dimming deliberately remains a display preference rather than
        # astronomical night: 20:30 to 06:59 in the configured local timezone.
        LOCAL_TIME_CACHE["night"] = hour > 20 or (hour == 20 and minute >= 30) or hour < 7
        LOCAL_TIME_CACHE["festive"] = local[1] == 12 or (local[1] == 1 and local[2] <= 14)
    except Exception:
        pass


def get_clock_parts():
    try:
        t = LOCAL_TIME_CACHE["parts"]
        return LOCAL_TIME_CACHE["clock_text"], t[5]
    except Exception:
        return "--:--", 0


def local_time_parts():
    return LOCAL_TIME_CACHE["parts"]


def is_festive_period():
    manual = FESTIVE_BUTTON["manual"]
    return LOCAL_TIME_CACHE["festive"] if manual is None else manual


def update_festive_button(now_ms):
    # Rear button A toggles normal/festive mode for this boot. It is edge
    # detected and debounced, avoiding flash writes and repeated toggles.
    try:
        pressed = i75.switch_pressed(SWITCH_A)
        if (
            pressed
            and not FESTIVE_BUTTON["previous"]
            and time.ticks_diff(now_ms, FESTIVE_BUTTON["last_ms"]) >= 250
        ):
            FESTIVE_BUTTON["manual"] = not is_festive_period()
            FESTIVE_BUTTON["last_ms"] = now_ms
            print("Festive mode:", "on" if FESTIVE_BUTTON["manual"] else "off")
        FESTIVE_BUTTON["previous"] = pressed
    except Exception:
        # Older or unusual board builds should continue without the shortcut.
        pass


def event_minutes(value):
    try:
        clock = str(value).split("T", 1)[1][:5]
        hour, minute = clock.split(":")
        return int(hour) * 60 + int(minute)
    except Exception:
        return None


def sun_event_minutes(data):
    sunrise_raw = data.get("sunrise_time")
    sunset_raw = data.get("sunset_time")
    if sunrise_raw != SUN_EVENT_CACHE["sunrise"] or sunset_raw != SUN_EVENT_CACHE["sunset"]:
        SUN_EVENT_CACHE["sunrise"] = sunrise_raw
        SUN_EVENT_CACHE["sunset"] = sunset_raw
        SUN_EVENT_CACHE["minutes"] = (event_minutes(sunrise_raw), event_minutes(sunset_raw))
    return SUN_EVENT_CACHE["minutes"]


def is_after_sunset(data):
    if not data.get("forecast_ok", False):
        return False
    sunrise, sunset = sun_event_minutes(data)
    if sunrise is None or sunset is None:
        return False
    try:
        local = local_time_parts()
        now_minutes = local[3] * 60 + local[4]
        return now_minutes >= sunset or now_minutes < sunrise
    except Exception:
        return False


def is_daylight(data):
    if not data.get("forecast_ok", False):
        return False
    sunrise, sunset = sun_event_minutes(data)
    if sunrise is None or sunset is None:
        return False
    local = local_time_parts()
    now_minutes = local[3] * 60 + local[4]
    return sunrise <= now_minutes < sunset


# ---------------------------------------------------------------------------
# Demo data and formatting
# ---------------------------------------------------------------------------

def celsius_to_display_temperature(value):
    """Convert demo-only Celsius values to the configured display unit."""
    if DISPLAY_TEMPERATURE_UNIT == "F":
        return value * 9.0 / 5.0 + 32.0
    return value


def get_demo_weather():
    demo_temps_c = [-2.4, 2.5, 8.0, 13.3, 18.5, 25.0, 28.0, 31.0]
    demo_step = int(time.time() // DEMO_REFRESH_SECONDS) % len(demo_temps_c)
    temp_c = demo_temps_c[demo_step]
    temp = celsius_to_display_temperature(temp_c)
    trends = ["rising_fast", "rising_slow", "steady", "falling_slow", "falling_fast"]
    return {
        "temperature_c": temp,
        "temperature_unit": DISPLAY_TEMPERATURE_UNIT,
        "humidity": 43 + demo_step,
        "min_temperature_c": celsius_to_display_temperature(-2.4),
        "max_temperature_c": celsius_to_display_temperature(31.0),
        "is_cold": temp_c <= 3,
        "lightning_strikes_last_hour": 0,
        "lightning_strikes_last_5_min": 0,
        "pressure_trend": trends[demo_step % len(trends)],
        "storm_warning": demo_step == 7,
        "data_ok": True,
        "forecast_ok": False,
    }


def format_temperature(value):
    try:
        return "{:.1f}".format(float(value))
    except Exception:
        return "--.-"


def format_humidity(value):
    try:
        return "{}%".format(int(value))
    except Exception:
        return "--%"


def format_daily_temperature_parts(value):
    try:
        numeric = float(value)
        # Three-digit Fahrenheit values are common enough to plan for. Dropping
        # the decimal keeps MIN/MAX legible in their narrow bottom-row areas.
        if DISPLAY_TEMPERATURE_UNIT == "F" and abs(numeric) >= 100:
            return "{:.0f}".format(numeric), ""
        whole, fraction = "{:.1f}".format(numeric).split(".")
        return whole, "." + fraction
    except Exception:
        return "--", ""


def draw_daily_temperature(value, area_x, area_width, pen):
    whole, fraction = format_daily_temperature_parts(value)
    whole_width = pixel_text_width(whole, scale=2)
    fraction_width = pixel_text_width(fraction, scale=1) if fraction else 0
    gap = 1 if fraction else 0
    total_width = whole_width + gap + fraction_width
    if total_width <= area_width:
        x = area_x + (area_width - total_width) // 2
        outline_pixel_text(whole, x, 52, scale=2)
        if fraction:
            outline_pixel_text(fraction, x + whole_width + gap, 57, scale=1)
        draw_pixel_text(whole, x, 52, pen, scale=2)
        if fraction:
            draw_pixel_text(fraction, x + whole_width + gap, 57, pen, scale=1)
        return
    text = whole + fraction
    x = area_x + max(0, (area_width - pixel_text_width(text)) // 2)
    outline_pixel_text(text, x, 57, scale=1)
    draw_pixel_text(text, x, 57, pen, scale=1)


# ---------------------------------------------------------------------------
# Drawing and animation
# ---------------------------------------------------------------------------

def draw_storm_warning(x, y, pen):
    graphics.set_pen(pen)
    for row in range(9):
        half = row // 2
        graphics.rectangle(x + 4 - half, y + row, half * 2 + 1, 1)
    graphics.set_pen(BLACK)
    graphics.rectangle(x + 4, y + 3, 1, 3)
    graphics.pixel(x + 4, y + 7)


def draw_divider_line(y, second, top=True, fault=False):
    second = clamp(safe_int(second), 0, 59)
    x = BAR_LEFT + second * (BAR_WIDTH - 1) // 59
    if fault:
        base_rgb, edge_rgb, centre_rgb = (65, 0, 0), (95, 0, 0), (145, 0, 0)
    else:
        base_rgb = (0, 38, 45) if top else (55, 30, 0)
        edge_rgb = (0, 72, 82) if top else (88, 48, 0)
        centre_rgb = (0, 118, 132) if top else (138, 76, 0)

    graphics.set_pen(cached_pen(base_rgb))
    graphics.rectangle(BAR_LEFT, y, BAR_WIDTH, 1)
    if not fault and is_festive_period():
        offset = 0 if top else 2
        for bulb in range(second + 1):
            graphics.set_pen(cached_pen(FESTIVE_COLOURS[(bulb + offset) % 4]))
            graphics.pixel(BAR_LEFT + bulb * (BAR_WIDTH - 1) // 59, y)
        graphics.set_pen(cached_pen(FESTIVE_BRIGHT[(second + offset) % 4]))
        graphics.rectangle(x, y - 1, 1, 3)
        return

    graphics.set_pen(cached_pen(edge_rgb))
    if second > 0:
        graphics.pixel(x - 1, y)
    if second < 59:
        graphics.pixel(x + 1, y)
    graphics.set_pen(cached_pen(centre_rgb))
    graphics.rectangle(x, y - 1, 1, 3)


def star_seed(value):
    return (value * 1103515245 + 12345) & 0x7FFFFFFF


def draw_visible_pixel(x, y):
    if 0 <= x < WIDTH and 0 <= y < 64:
        graphics.pixel(int(x), int(y))


def schedule_shooting_star(now_ms):
    seed = star_seed((now_ms // 1000) + 97)
    SHOOTING_STAR["next_ms"] = time.ticks_add(now_ms, 300000 + (seed % 300001))


def schedule_ufo(now_ms, daylight=False, state=None):
    if state is None:
        state = UFO_STATE
    seed = star_seed((now_ms // 1000) + 313 + state["slot"] * 307)
    slot = state["slot"]
    if slot:
        wait_ms = (110000 + seed % 110001) if daylight else (70000 + seed % 70001)
    else:
        wait_ms = 30000 + (seed % 30001) if daylight else 20000 + (seed % 20001)
        if SCREEN_COUNT > 1 and AMBIENT_ACTIVITY:
            wait_ms = wait_ms * 4 // 5
    state["next_ms"] = time.ticks_add(now_ms, wait_ms)
    state["daylight"] = daylight


def draw_ufo(now_ms, daylight=False, state=None):
    if state is None:
        state = UFO_STATE
    if state["next_ms"] == 0 or (not state["active"] and state["daylight"] != daylight):
        schedule_ufo(now_ms, daylight, state)
        return
    if not state["active"]:
        if time.ticks_diff(now_ms, state["next_ms"]) < 0:
            return
        seed = star_seed((now_ms // 1000) + 719 + state["slot"] * 701)
        mode = (seed >> 3) % 3
        state["active"] = True
        state["start_ms"] = now_ms
        state["right"] = bool(seed & 1)
        state["y"] = 3 + ((seed >> 5) % 25)
        state["festive"] = is_festive_period()
        palette_size = len(FESTIVE_UFO_COLOURS) if state["festive"] else len(UFO_COLOURS)
        state["colour"] = (seed >> 10) % palette_size
        state["style"] = (seed >> 12) % len(UFO_WIDTHS)
        state["mode"] = mode
        state["duration_ms"] = (3800, 7200, 11500)[mode] + state["style"] * 650
        state["hover_x"] = 17 + ((seed >> 13) % (WIDTH - 34))

    elapsed = time.ticks_diff(now_ms, state["start_ms"])
    duration = state["duration_ms"]
    if elapsed >= duration:
        state["active"] = False
        schedule_ufo(now_ms, daylight, state)
        return

    direction = 1 if state["right"] else -1
    style = state["style"]
    width = UFO_WIDTHS[style]
    start_x = -width
    target_x = WIDTH - 1 + width
    if state["mode"] == 2:
        enter_ms = 3000
        leave_ms = 3000
        hover_x = state["hover_x"]
        if elapsed < enter_ms:
            edge_x = start_x if direction > 0 else target_x
            x = edge_x + direction * ((abs(hover_x - edge_x) * elapsed) // enter_ms)
        elif elapsed < duration - leave_ms:
            x = hover_x
        else:
            leave_x = target_x if direction > 0 else start_x
            leave_elapsed = elapsed - (duration - leave_ms)
            x = hover_x + direction * ((abs(leave_x - hover_x) * leave_elapsed) // leave_ms)
    else:
        journey = WIDTH + width * 2
        x = start_x + (elapsed * journey) // duration if direction > 0 else target_x - (elapsed * journey) // duration

    y = state["y"] + UFO_BOB[(elapsed // 300) % len(UFO_BOB)]
    colours = FESTIVE_UFO_COLOURS if state["festive"] else UFO_COLOURS
    dim_lights = FESTIVE_UFO_DIM_LIGHTS if state["festive"] else UFO_DIM_LIGHTS
    day_lights = FESTIVE_UFO_DAY_LIGHTS if state["festive"] else UFO_DAY_LIGHTS
    body, lights = colours[state["colour"]]
    graphics.set_pen(cached_pen((90, 90, 105)))
    for dx, dy in UFO_DOMES[style]:
        draw_visible_pixel(x + dx, y + dy)
    graphics.set_pen(cached_pen(body))
    for row_start, row_end, dy in UFO_ROWS[style]:
        for dx in range(row_start, row_end + 1):
            draw_visible_pixel(x + dx, y + dy)
    light_y = UFO_LIGHT_Y[style]
    light_phase = (elapsed // 375) % 3
    graphics.set_pen(cached_pen(dim_lights[state["colour"]]))
    for dx in UFO_LIGHTS[style]:
        draw_visible_pixel(x + dx, y + light_y)
    active_lights = day_lights[state["colour"]] if daylight else lights
    graphics.set_pen(cached_pen(active_lights))
    for lamp_index, dx in enumerate(UFO_LIGHTS[style]):
        if (lamp_index + light_phase) % 3 == 0:
            draw_visible_pixel(x + dx, y + light_y)
    if state["mode"] == 2 and 3000 <= elapsed < duration - 3000 and (elapsed // 700) % 2 == 0:
        graphics.set_pen(cached_pen((24, 38, 42)))
        centre_x = width // 2
        beam_y = UFO_BEAM_Y[style]
        draw_visible_pixel(x + centre_x, y + beam_y)
        draw_visible_pixel(x + centre_x, y + beam_y + 1)


def schedule_day_creature(now_ms, state=None):
    if state is None:
        state = DAY_CREATURE
    seed = star_seed((now_ms // 1000) + 911 + state["slot"] * 503)
    wait_ms = 20000 + seed % 20001
    if state["slot"]:
        wait_ms = (90000 + seed % 120001) * state["slot"]
    state["next_ms"] = time.ticks_add(now_ms, wait_ms)


def draw_large_bird_pixels(pixels, x, y, right, pen):
    graphics.set_pen(pen)
    for dx, dy in pixels:
        px = x + (dx * 2 if right else (8 - dx) * 2)
        py = y + dy * 2
        draw_visible_pixel(px, py)
        draw_visible_pixel(px + 1, py)
        draw_visible_pixel(px, py + 1)
        draw_visible_pixel(px + 1, py + 1)


def draw_duck_family(x, y, right, elapsed):
    body, head, wing, bill, duckling, duckling_accent = DUCK_COLOURS
    mirror = DUCK_FAMILY_WIDTH - 1

    graphics.set_pen(cached_pen(body))
    for dx, dy in DUCK_BODY:
        px = x + 18 + dx if right else x + mirror - 18 - dx
        draw_visible_pixel(px, y + dy)
    graphics.set_pen(cached_pen(head))
    for dx, dy in DUCK_HEAD:
        px = x + 18 + dx if right else x + mirror - 18 - dx
        draw_visible_pixel(px, y + dy)
    graphics.set_pen(cached_pen(wing))
    for dx, dy in DUCK_WING:
        px = x + 18 + dx if right else x + mirror - 18 - dx
        draw_visible_pixel(px, y + dy)
    graphics.set_pen(cached_pen(bill))
    for dx, dy in DUCK_BILL:
        px = x + 18 + dx if right else x + mirror - 18 - dx
        draw_visible_pixel(px, y + dy)
    for dx, dy in ((4,7),(4,8),(3,8),(8,7),(8,8),(7,8)):
        px = x + 18 + dx if right else x + mirror - 18 - dx
        draw_visible_pixel(px, y + dy)
    graphics.set_pen(BLACK)
    draw_visible_pixel(x + 28 if right else x + mirror - 28, y + 1)

    step = elapsed // 250
    for index, base_x in enumerate((13, 7, 1)):
        bob = -1 if (step + index * 2) % 6 == 1 else 0
        graphics.set_pen(cached_pen(duckling))
        for dx, dy in DUCKLING_BODY:
            px = x + base_x + dx if right else x + mirror - base_x - dx
            draw_visible_pixel(px, y + 4 + dy + bob)
        graphics.set_pen(cached_pen(duckling_accent))
        for dx, dy in DUCKLING_BILL:
            px = x + base_x + dx if right else x + mirror - base_x - dx
            draw_visible_pixel(px, y + 4 + dy + bob)
        draw_visible_pixel(x + base_x + 1 if right else x + mirror - base_x - 1, y + 8 + bob)
        graphics.set_pen(BLACK)
        draw_visible_pixel(x + base_x + 3 if right else x + mirror - base_x - 3, y + 4 + bob)


def draw_festive_procession(x, y, right, elapsed):
    # Fixed pixel lists keep the procession cheap enough for the 8 FPS target.
    mirror = FESTIVE_FAMILY_WIDTH - 1

    def festive_pixel(dx, dy):
        draw_visible_pixel(x + (dx if right else mirror - dx), y + dy)

    for pixels, colour in (
        (SANTA_RED, (145, 18, 22)),
        (SANTA_WHITE, (155, 155, 145)),
        (SANTA_SKIN, (150, 92, 55)),
        (SLEIGH_RED, (125, 12, 18)),
        (SLEIGH_GOLD, (165, 105, 10)),
    ):
        graphics.set_pen(cached_pen(colour))
        for dx, dy in pixels:
            festive_pixel(dx, dy)
    graphics.set_pen(BLACK)
    festive_pixel(9, 3)

    leg_phase = (elapsed // 250) & 1
    for index, base_x in enumerate((17, 29)):
        bob = -1 if ((elapsed // 375) + index) % 6 == 1 else 0
        graphics.set_pen(cached_pen((105, 62, 26)))
        for dx, dy in REINDEER_BODY:
            festive_pixel(base_x + dx, dy + bob)
        graphics.set_pen(cached_pen((72, 42, 20)))
        for dx, dy in REINDEER_ANTLERS:
            festive_pixel(base_x + dx, dy + bob)
        legs = ((2,7),(3,8),(5,7),(6,8)) if (leg_phase + index) & 1 else ((2,8),(3,7),(5,8),(6,7))
        for dx, dy in legs:
            festive_pixel(base_x + dx, dy + bob)
        graphics.set_pen(BLACK)
        festive_pixel(base_x + 8, 2 + bob)

    graphics.set_pen(cached_pen((175, 24, 18)))
    festive_pixel(38, 3)
    graphics.set_pen(cached_pen((145, 92, 8)))
    for dx in range(14, 31):
        festive_pixel(dx, 6)


def day_creature_motion(elapsed, duration, origin_right, turnaround):
    if not turnaround:
        return (elapsed * (WIDTH + 18)) // duration, origin_right, False
    phase = (elapsed * 1000) // duration
    if phase < 300:
        progress = (phase * 35) // 300
    elif phase < 450:
        progress = 35 + ((phase - 300) * 10) // 150
    elif phase < 600:
        progress = 45
    elif phase < 750:
        progress = 45 - ((phase - 600) * 10) // 150
    else:
        progress = max(0, 35 - ((phase - 750) * 35) // 250)
    return progress * (WIDTH + 18) // 82, origin_right if phase < 525 else not origin_right, 450 <= phase < 600


def draw_day_creature(data, now_ms, second, data_fault=False, state=None):
    if state is None:
        state = DAY_CREATURE
    daylight = is_daylight(data)
    festive = is_festive_period()
    if not daylight and not festive:
        state["active"] = False
        state["next_ms"] = 0
        return
    if not daylight and state["active"] and state["kind"] != "santa":
        state["active"] = False
        schedule_day_creature(now_ms, state)
        return
    if state["next_ms"] == 0:
        schedule_day_creature(now_ms, state)
        return
    if not state["active"]:
        if time.ticks_diff(now_ms, state["next_ms"]) < 0:
            return
        seed = star_seed((now_ms // 1000) + 1237 + state["slot"] * 809)
        perches = (16, 42, 63)
        if GROUND_STATE["level"]:
            surface = 64 - GROUND_STATE["level"]
            perches = (16, 42) if surface > 42 else (16,)
        santa_visit = state["slot"] == 0 and festive and ((seed >> 21) & 7) == 0
        if not daylight and not santa_visit:
            schedule_day_creature(now_ms, state)
            return
        duck_visit = state["slot"] == 0 and daylight and not santa_visit and (seed & 7) == 0
        state["active"] = True
        state["start_ms"] = now_ms
        state["kind"] = "santa" if santa_visit else ("duck" if duck_visit else "bird")
        state["species"] = (seed >> 4) % len(BIRD_COLOURS)
        state["perch"] = 16 if (duck_visit or santa_visit) else perches[(seed >> 7) % len(perches)]
        state["right"] = bool(seed & 1)
        state["duration_ms"] = (14000 + ((seed >> 11) % 4001)) if santa_visit else ((12000 + ((seed >> 11) % 4001)) if duck_visit else (7000 + ((seed >> 11) % 5001)))
        interaction_roll = (seed >> 16) % 6
        state["interact"] = not duck_visit and not santa_visit and interaction_roll < 2
        state["interaction_done"] = False
        state["interaction_start_ms"] = 0
        state["turnaround"] = False if (duck_visit or santa_visit) else ((seed >> 19) & 3) == 0

    raw_elapsed = time.ticks_diff(now_ms, state["start_ms"])
    hold_ms = 900
    interaction_age = time.ticks_diff(now_ms, state["interaction_start_ms"])
    held_ms = clamp(interaction_age, 0, hold_ms) if state["interaction_done"] else 0
    elapsed = raw_elapsed - held_ms
    duration = state["duration_ms"]
    if elapsed >= duration:
        state["active"] = False
        schedule_day_creature(now_ms, state)
        return

    if state["kind"] == "duck":
        progress = (elapsed * (WIDTH + DUCK_FAMILY_WIDTH)) // duration
        x = -DUCK_FAMILY_WIDTH + progress if state["right"] else WIDTH - progress
        draw_duck_family(x, 8, state["right"], elapsed)
        return
    if state["kind"] == "santa":
        progress = (elapsed * (WIDTH + FESTIVE_FAMILY_WIDTH)) // duration
        x = -FESTIVE_FAMILY_WIDTH + progress if state["right"] else WIDTH - progress
        draw_festive_procession(x, 6, state["right"], elapsed)
        return

    progress, right, stopped = day_creature_motion(
        elapsed, duration, state["right"], state["turnaround"]
    )
    x = -18 + progress if state["right"] else WIDTH - progress
    perch = state["perch"]
    hop = 0 if stopped else (0, 0, -1, -2, -1, 0, 0, 0)[(elapsed // 150) % 8]
    front_x = x + 16 if right else x
    if (
        state["interact"]
        and not state["interaction_done"]
        and not data_fault
        and perch in (16, 42)
        and abs(front_x - (BAR_LEFT + second * (BAR_WIDTH - 1) // 59)) <= 2
    ):
        state["interaction_done"] = True
        state["interaction_start_ms"] = now_ms
        interaction_age = 0

    interacting = state["interaction_done"] and 0 <= interaction_age < hold_ms
    y = perch - 14 + hop
    body, breast, wing, beak = BIRD_COLOURS[state["species"]]
    peck_down = interacting and ((interaction_age // 225) & 1) == 0
    draw_large_bird_pixels(BIRD_PECK_BODY if peck_down else BIRD_BODY, x, y, right, cached_pen(body))
    breast_pixels = ((6,4),(7,4),(6,5),(7,5)) if peck_down else ((5,2),(6,2),(5,3),(5,4))
    draw_large_bird_pixels(breast_pixels, x, y, right, cached_pen(breast))
    wing_frame = BIRD_WING_SEQUENCE[(elapsed // 250) % len(BIRD_WING_SEQUENCE)]
    draw_large_bird_pixels(BIRD_WING_FRAMES[wing_frame], x, y, right, cached_pen(wing))
    draw_large_bird_pixels(((3,6),(5,6)), x, y, right, cached_pen(beak))
    beak_pixels = ((8,7),) if peck_down else ((7,1),(8,1))
    draw_large_bird_pixels(beak_pixels, x, y, right, cached_pen(beak))
    graphics.set_pen(BLACK)
    eye_x = x + (14 if right else 2) if peck_down else x + (13 if right else 4)
    eye_y = y + 9 if peck_down else y + 1
    draw_visible_pixel(eye_x, eye_y)
    draw_visible_pixel(eye_x, eye_y + 1)

def draw_day_rainbow(data, now_ms):
    """Brief half-hourly background arc; environmental coordinates stay fixed."""
    if not is_daylight(data):
        RAINBOW["start_ms"] = None
        return
    local = local_time_parts()
    # Allow a slow weather request at the boundary, but never replay mid-minute.
    if local[4] in (0, 30) and local[5] < 10:
        key = (local[0], local[1], local[2], local[3], local[4])
        if key != RAINBOW["last_key"]:
            RAINBOW["last_key"] = key
            RAINBOW["start_ms"] = now_ms
    start = RAINBOW["start_ms"]
    if start is None:
        return
    elapsed = time.ticks_diff(now_ms, start)
    if elapsed < 0 or elapsed >= RAINBOW_DURATION_MS:
        RAINBOW["start_ms"] = None
        return
    fade_ms = min(750, RAINBOW_DURATION_MS // 2)
    brightness = min(100, elapsed * 100 // fade_ms,
                     (RAINBOW_DURATION_MS - elapsed) * 100 // fade_ms)
    if brightness <= 0:
        return
    for band, rgb in enumerate(RAINBOW_COLOURS):
        # Fade shades are transient; don't grow the persistent pen cache.
        graphics.set_pen(cached_pen(rgb) if brightness == 100 else
                         make_pen(tuple(channel * brightness // 100 for channel in rgb)))
        x = 0
        while x < WIDTH:
            row = RAINBOW_ROWS[x]
            end = x + 1
            while end < WIDTH and RAINBOW_ROWS[end] == row:
                end += 1
            if row + band < HEIGHT:
                graphics.rectangle(x, row + band, end - x, 1)
            x = end


def update_abduction(data, now_ms):
    if not is_after_sunset(data):
        ABDUCTION["active"] = False
        return
    local = local_time_parts()
    key = (local[0], local[1], local[2], local[3], local[4])
    if local[4] in (0, 30) and local[5] < 2 and ABDUCTION["last_key"] != key:
        ABDUCTION["active"] = True
        ABDUCTION["start_ms"] = now_ms
        ABDUCTION["last_key"] = key
        ABDUCTION["colour"] = (local[2] + local[3] + local[4]) % len(ABDUCTION_COLOURS)
    if ABDUCTION["active"] and time.ticks_diff(now_ms, ABDUCTION["start_ms"]) >= 10500:
        ABDUCTION["active"] = False


def abduction_temperature(now_ms):
    if not ABDUCTION["active"]:
        return 0, 1.0, True
    elapsed = time.ticks_diff(now_ms, ABDUCTION["start_ms"])
    if elapsed < 3200:
        return 0, 1.0, True
    if elapsed < 5000:
        p = elapsed - 3200
        return -(p * 13 // 1800), max(0.25, 1.0 - p / 2400.0), True
    if elapsed < 6000:
        return -13, 0.0, False
    if elapsed < 7800:
        p = elapsed - 6000
        return -13 + p * 13 // 1800, min(1.0, 0.25 + p / 2400.0), True
    return 0, 1.0, True


def draw_abduction(now_ms):
    if not ABDUCTION["active"]:
        return
    elapsed = time.ticks_diff(now_ms, ABDUCTION["start_ms"])
    if elapsed < 1500:
        x = -23 + ((45 + UI_SHIFT) * elapsed // 1500)
    elif elapsed < 9000:
        x = UI_SHIFT + 22
    else:
        x = UI_SHIFT + 22 + ((WIDTH - UI_SHIFT - 16) * (elapsed - 9000) // 1500)
    y = 17 + UFO_BOB[(elapsed // 260) % len(UFO_BOB)]
    colour_index = ABDUCTION["colour"]
    dome, body, lights, beam = ABDUCTION_COLOURS[colour_index]
    if 1600 <= elapsed < 8800:
        beam_phase = (elapsed // 250) % 4
        beam_shades = ABDUCTION_BEAM_SHADES if is_night_time() else ABDUCTION_DAY_BEAM_SHADES
        graphics.set_pen(cached_pen(beam_shades[colour_index][beam_phase]))
        for by in range(22, 42):
            half = min(10, (by - 21) // 2)
            if (by + beam_phase) % 3 == 0:
                for bx in range(UI_SHIFT + 31 - half, UI_SHIFT + 32 + half):
                    if (bx + by) % 2 == 0:
                        draw_visible_pixel(bx, by)
    graphics.set_pen(cached_pen(dome))
    graphics.rectangle(x + 6, y, 11, 2)
    graphics.set_pen(cached_pen(body))
    graphics.rectangle(x + 2, y + 2, 19, 2)
    graphics.rectangle(x, y + 4, 23, 2)
    abduction_lamps = (2, 6, 11, 16, 20)
    lamp_phase = (elapsed // 250) % len(abduction_lamps)
    graphics.set_pen(cached_pen(ABDUCTION_DIM_LIGHTS[colour_index]))
    for dx in abduction_lamps:
        draw_visible_pixel(x + dx, y + 6)
    active_lights = lights if is_night_time() else ABDUCTION_DAY_LIGHTS[colour_index]
    graphics.set_pen(cached_pen(active_lights))
    draw_visible_pixel(x + abduction_lamps[lamp_phase], y + 6)


def draw_night_sky(data, now_ms):
    if not is_after_sunset(data):
        SHOOTING_STAR["active"] = False
        SHOOTING_STAR["next_ms"] = 0
        return

    for index in range(16 * SCREEN_COUNT):
        cadence = 23000 + index * 3700
        epoch = now_ms // cadence
        seed = star_seed(epoch + index * 101)
        x = 2 + (seed % (WIDTH - 4))
        y = 1 + ((seed >> 7) % 59)
        period = 2600 + index * 310
        phase = (now_ms + index * 557) % period
        triangle = phase if phase < period // 2 else period - phase
        brightness = 28 + (triangle * 72) // max(1, period // 2)
        graphics.set_pen(cached_pen((brightness, brightness, brightness + 18)))
        draw_visible_pixel(x, y)
        if index % 5 == 0 and brightness >= 84:
            arm = brightness // 3
            graphics.set_pen(cached_pen((arm, arm, arm + 10)))
            draw_visible_pixel(x - 1, y)
            draw_visible_pixel(x + 1, y)
            draw_visible_pixel(x, y - 1)
            draw_visible_pixel(x, y + 1)

    if SHOOTING_STAR["next_ms"] == 0:
        schedule_shooting_star(now_ms)
        return
    if not SHOOTING_STAR["active"]:
        if time.ticks_diff(now_ms, SHOOTING_STAR["next_ms"]) < 0:
            return
        seed = star_seed(now_ms // 1000)
        SHOOTING_STAR["active"] = True
        SHOOTING_STAR["start_ms"] = now_ms
        SHOOTING_STAR["right"] = bool(seed & 1)
        SHOOTING_STAR["y"] = 4 + ((seed >> 3) % 32)

    elapsed = time.ticks_diff(now_ms, SHOOTING_STAR["start_ms"])
    if elapsed >= 2000:
        SHOOTING_STAR["active"] = False
        schedule_shooting_star(now_ms)
        return
    travel = (elapsed * (WIDTH + 6)) // 2000
    x = -3 + travel if SHOOTING_STAR["right"] else WIDTH + 2 - travel
    direction = 1 if SHOOTING_STAR["right"] else -1
    y = SHOOTING_STAR["y"] + travel // 12
    for index, colour in enumerate(((110, 110, 120), (65, 70, 82), (32, 38, 50))):
        graphics.set_pen(cached_pen(colour))
        draw_visible_pixel(x - direction * index, y - index)


# Horizontal movement for 16 compass sectors. Direction is where the wind
# comes from, hence an easterly wind moves particles towards the left.
WIND_DX_BY_SECTOR = (
    0, -38, -71, -92, -100, -92, -71, -38,
    0, 38, 71, 92, 100, 92, 71, 38,
)
LEAF_Y_WAVE = (0, 2, 4, 2, 0, -2, -4, -2)
SNOW_FLUTTER = (0, 1, 2, 1, 0, -1, -2, -1)
RAIN_COLUMNS = (
    7, 43, 19, 56, 31, 11, 50, 24, 38, 4,
    59, 16, 46, 28, 9, 35, 53, 21, 41, 13,
    61, 26, 48, 6, 33, 18, 55, 29, 44, 2,
    52,
)


def wind_dx_percent(direction):
    sector = int((safe_float(direction) + 11.25) // 22.5) % 16
    return WIND_DX_BY_SECTOR[sector]


def draw_weather_particles(data, now_ms):
    if not data.get("forecast_ok", False):
        return

    rain_mm = safe_float(data.get("rain_mm")) + safe_float(data.get("showers_mm"))
    snow_cm = safe_float(data.get("snowfall_cm"))
    wind_speed = safe_float(data.get("wind_speed_kmh"))
    wind_gust = safe_float(data.get("wind_gust_kmh"))
    effective_wind = max(wind_speed, wind_gust * 0.65)
    wind_dx = wind_dx_percent(data.get("wind_direction_deg"))

    if rain_mm > 0:
        if rain_mm < 0.3:
            count, cycle_ms = 3, 3200
        elif rain_mm < 1.5:
            count, cycle_ms = 5, 2500
        else:
            count, cycle_ms = 7, 1800
        drift_tenths = (wind_dx * min(180, int(effective_wind * 4.2))) // 100
        tail_dx = 1 if wind_dx > 20 else -1 if wind_dx < -20 else 0
        width_dx = -tail_dx if tail_dx else 1
        for index in range(count * SCREEN_COUNT):
            shifted_ms = now_ms + index * 337
            phase_ms = shifted_ms % cycle_ms
            y = (phase_ms * 72) // cycle_ms - 5
            cycle_index = shifted_ms // cycle_ms
            seed_x = RAIN_COLUMNS[(cycle_index + index * 7) % len(RAIN_COLUMNS)] + (index % SCREEN_COUNT) * 64
            drift_x = (phase_ms * drift_tenths) // (cycle_ms * 10)
            x = 2 + ((seed_x - 2 + drift_x) % (WIDTH - 4))
            graphics.set_pen(cached_pen((0, 100, 145)))
            draw_visible_pixel(x, y)
            draw_visible_pixel(x + width_dx, y)
            graphics.set_pen(cached_pen((0, 68, 105)))
            draw_visible_pixel(x - tail_dx, y - 1)
            draw_visible_pixel(x - tail_dx + width_dx, y - 1)
            graphics.set_pen(cached_pen((0, 42, 72)))
            draw_visible_pixel(x - (tail_dx * 2), y - 2)
            draw_visible_pixel(x - (tail_dx * 2) + width_dx, y - 2)
            graphics.set_pen(cached_pen((0, 28, 52)))
            draw_visible_pixel(x - (tail_dx * 3), y - 3)
            draw_visible_pixel(x - (tail_dx * 3) + width_dx, y - 3)
        return

    if snow_cm > 0:
        count = 3 if snow_cm < 0.3 else 5
        cycle_ms = 5200
        drift_tenths = (wind_dx * min(220, int(effective_wind * 5.5))) // 100
        for index in range(count * SCREEN_COUNT):
            phase_ms = (now_ms + index * 911) % cycle_ms
            y = (phase_ms * 70) // cycle_ms - 3
            seed_x = 3 + ((index * 23 + 11) % (WIDTH - 6))
            drift_x = (phase_ms * drift_tenths) // (cycle_ms * 10)
            wave_index = ((phase_ms * 8) // cycle_ms + index) % 8
            x = 2 + ((seed_x - 2 + drift_x + SNOW_FLUTTER[wave_index]) % (WIDTH - 4))
            side_dx = 1 if wave_index < 4 else -1
            graphics.set_pen(cached_pen((92, 110, 125)))
            draw_visible_pixel(x, y)
            graphics.set_pen(cached_pen((125, 138, 145)))
            draw_visible_pixel(x, y - 1)
            graphics.set_pen(cached_pen((52, 72, 96)))
            draw_visible_pixel(x + side_dx, y)
            draw_visible_pixel(x - side_dx, y)
            draw_visible_pixel(x, y + 1)
        return

    if effective_wind >= WIND_LEAF_THRESHOLD_KMH:
        leaf_count = 1 if effective_wind < 20 else 2 if effective_wind < 40 else 4
        travel_ms = max(3600, 7600 - int(effective_wind * 65))
        interval_ms = travel_ms + (18000 if effective_wind < 8 else 3000)
        travels_right = wind_dx >= 0
        for index in range(leaf_count * SCREEN_COUNT):
            phase_ms = (now_ms + index * 1900) % interval_ms
            if phase_ms >= travel_ms:
                continue
            if travels_right:
                x = -3 + (phase_ms * (WIDTH + 6)) // travel_ms
                tip_dx = 1
            else:
                x = WIDTH + 2 - (phase_ms * (WIDTH + 6)) // travel_ms
                tip_dx = -1
            wave_index = ((phase_ms * 8) // travel_ms + index) % 8
            y = 18 + ((index * 13) % 28) + LEAF_Y_WAVE[wave_index]
            leaf_slot = (phase_ms // 625 + index * 3) % len(LEAF_FRAME_SEQUENCE)
            core, tip, lower, stem = LEAF_FRAMES[LEAF_FRAME_SEQUENCE[leaf_slot]]
            graphics.set_pen(cached_pen((122, 66, 0)))
            draw_visible_pixel(x + core[0] * tip_dx, y + core[1])
            graphics.set_pen(cached_pen((105, 88, 0)))
            draw_visible_pixel(x + tip[0] * tip_dx, y + tip[1])
            graphics.set_pen(cached_pen((82, 34, 0)))
            draw_visible_pixel(x + lower[0] * tip_dx, y + lower[1])
            graphics.set_pen(cached_pen((55, 25, 0)))
            draw_visible_pixel(x + stem[0] * tip_dx, y + stem[1])


def precipitation_target(data):
    """Map the current Open-Meteo precipitation intensity to visual depth."""
    rain_mm = safe_float(data.get("rain_mm")) + safe_float(data.get("showers_mm"))
    snow_cm = safe_float(data.get("snowfall_cm"))
    if snow_cm > 0:
        return "snow", 4 if snow_cm < 0.3 else 12 if snow_cm < 1.0 else 21
    if rain_mm > 0:
        return "rain", 2 if rain_mm < 0.3 else 10 if rain_mm < 1.5 else 32
    return None, 0


def update_ground_state(data, now_ms):
    if not data.get("forecast_ok", False):
        GROUND_STATE["kind"] = None
        GROUND_STATE["level"] = 0
        GROUND_STATE["last_ms"] = now_ms
        return

    target_kind, target_level = precipitation_target(data)
    current_kind = GROUND_STATE["kind"]
    current_level = GROUND_STATE["level"]

    if target_kind and target_kind != current_kind:
        GROUND_STATE["kind"] = target_kind
        GROUND_STATE["level"] = 1
        GROUND_STATE["last_ms"] = now_ms
        return

    elapsed = time.ticks_diff(now_ms, GROUND_STATE["last_ms"])
    interval = ACCUMULATION_STEP_MS if target_level > current_level else ACCUMULATION_DRAIN_MS
    if elapsed < interval:
        return
    if target_level > current_level:
        GROUND_STATE["level"] = current_level + 1
    elif target_level < current_level:
        GROUND_STATE["level"] = current_level - 1
        if GROUND_STATE["level"] <= 0:
            GROUND_STATE["kind"] = None
    GROUND_STATE["last_ms"] = now_ms


def draw_ground_accumulation(data, now_ms):
    update_ground_state(data, now_ms)
    kind = GROUND_STATE["kind"]
    level = GROUND_STATE["level"]
    if not kind or level <= 0:
        return

    if kind == "snow":
        bank = (0, 1, 0, 0, 1, 1, 0, 1)
        graphics.set_pen(cached_pen((54, 68, 82)))
        for x in range(WIDTH):
            height = min(21, level + bank[(x // 4) % len(bank)])
            graphics.rectangle(x, 64 - height, 1, height)
        graphics.set_pen(cached_pen((112, 125, 134)))
        for x in range(WIDTH):
            height = min(21, level + bank[(x // 4) % len(bank)])
            draw_visible_pixel(x, 64 - height)
        return

    surface_y = 64 - level
    water_colours = ((0, 48, 78), (0, 36, 68), (0, 27, 57), (0, 19, 44))
    for band in range(4):
        band_start = (level * band) // 4
        band_end = (level * (band + 1)) // 4
        band_height = band_end - band_start
        if band_height <= 0:
            continue
        graphics.set_pen(cached_pen(water_colours[band]))
        graphics.rectangle(0, surface_y + band_start, WIDTH, band_height)
    graphics.set_pen(cached_pen((0, 72, 102)))
    graphics.rectangle(0, surface_y, WIDTH, 1)

    wind_dx = wind_dx_percent(data.get("wind_direction_deg"))
    for ripple in range(2):
        phase = (now_ms + ripple * 1900) % 4400
        if phase >= 2100:
            continue
        centre = (18, 45)[ripple] * WIDTH // 64 + (wind_dx * phase) // 21000
        radius = 1 + (phase * 10) // 2100
        graphics.set_pen(cached_pen((0, 105, 132)))
        for side in (-1, 1):
            edge = centre + side * radius
            draw_visible_pixel(edge, surface_y)
            draw_visible_pixel(edge - side, surface_y)
        if radius >= 4:
            graphics.set_pen(cached_pen((0, 72, 102)))
            draw_visible_pixel(centre - radius + 2, surface_y + 1)
            draw_visible_pixel(centre + radius - 2, surface_y + 1)

    if level >= 6:
        bubble_span = max(2, level - 2)
        for bubble in range(min(7, 2 + level // 5) * SCREEN_COUNT):
            cycle = 2600 + bubble * 370
            phase = (now_ms + bubble * 641) % cycle
            rise = (phase * bubble_span) // cycle
            bx = 4 + ((bubble * 17 + 9 + (bubble % SCREEN_COUNT) * 64) % (WIDTH - 8)) + UFO_BOB[(phase // 300 + bubble) % len(UFO_BOB)]
            by = 62 - rise
            graphics.set_pen(cached_pen((20, 88, 112) if bubble % 3 else (34, 112, 138)))
            draw_visible_pixel(bx, by)
            if bubble % 3 == 0 and level >= 14:
                draw_visible_pixel(bx + 1, by - 1)


def fish_seed(now_ms):
    seed = (now_ms // 1000) & 0x7FFFFFFF
    return (seed * 1103515245 + 12345) & 0x7FFFFFFF


def schedule_next_fish(now_ms, state=None):
    if state is None:
        state = FISH_STATE
    seed = fish_seed(now_ms + state["slot"] * 997)
    wait_ms = 20000 + seed % 20001 if not state["slot"] else 110000 + seed % 130001
    state["next_ms"] = time.ticks_add(now_ms, wait_ms)


def draw_flood_fish(now_ms, state=None):
    if state is None:
        state = FISH_STATE
    if GROUND_STATE["kind"] != "rain" or GROUND_STATE["level"] < 8:
        state["active"] = False
        state["next_ms"] = 0
        return

    surface_y = 64 - GROUND_STATE["level"]
    min_y = surface_y + 1
    if state["active"] and state["y"] < min_y:
        state["y"] = min_y
    if state["next_ms"] == 0:
        schedule_next_fish(now_ms, state)
        return
    if not state["active"]:
        if time.ticks_diff(now_ms, state["next_ms"]) < 0:
            return
        seed = fish_seed(now_ms + state["slot"] * 1291)
        species = (seed >> 7) % len(FISH_WIDTHS)
        fish_height = FISH_HEIGHTS[species]
        if min_y + fish_height > HEIGHT:
            schedule_next_fish(now_ms, state)
            return
        y_span = max(1, (64 - fish_height) - min_y + 1)
        state["active"] = True
        state["start_ms"] = now_ms
        state["right"] = bool(seed & 1)
        state["y"] = min_y + ((seed >> 3) % y_span)
        state["species"] = species
        state["colour"] = (seed >> 11) % len(FISH_COLOURS)
        state["travel_ms"] = (7600, 9800, 12400)[species] + ((seed >> 15) % 1800)
        start_fish_motion(state, now_ms, WIDTH, FISH_WIDTHS[species])
        if not AMBIENT_ACTIVITY:
            state["quirky"] = False

    elapsed_ms = time.ticks_diff(now_ms, state["start_ms"])
    species = state["species"]
    width = FISH_WIDTHS[species]
    height = FISH_HEIGHTS[species]
    # Keep the entire sprite submerged as the water drains.
    state["y"] = clamp(state["y"], min_y, HEIGHT - height)
    centre, direction, finished = move_fish(state, now_ms, WIDTH, width)
    if finished:
        state["active"] = False
        schedule_next_fish(now_ms, state)
        return
    x = centre - direction * (width // 2)

    y = state["y"]
    graphics.set_pen(cached_pen(FISH_COLOURS[state["colour"]]))
    middle = height // 2
    for dy in range(height):
        distance = abs(middle - dy)
        row_start = 2 + (distance // 2)
        row_end = width - 1 - distance
        for dx in range(row_start, row_end + 1):
            draw_visible_pixel(x + direction * dx, y + dy)

    tail_shift = FISH_TAIL_SHIFT[(elapsed_ms // 375) % len(FISH_TAIL_SHIFT)]
    graphics.set_pen(cached_pen(FISH_ACCENTS[state["colour"]]))
    for dx, dy in ((0, 0), (1, 1), (2, middle), (1, height - 2), (0, height - 1)):
        if dx < 2:
            dy = clamp(dy + tail_shift, 0, height - 1)
        draw_visible_pixel(x + direction * dx, y + dy)
    fin_y = height - 1 if tail_shift >= 0 else height - 2
    draw_visible_pixel(x + direction * (width // 2), y + fin_y)
    if species > 0:
        draw_visible_pixel(x + direction * (width // 2 + 1), y + fin_y)
    graphics.set_pen(BLACK)
    draw_visible_pixel(x + direction * (width - 2), y + max(1, middle - 1))
    graphics.set_pen(cached_pen((105, 105, 92)))
    draw_visible_pixel(x + direction * (width - 3), y + middle)


def draw_clouds(data, now_ms):
    """One dim, slow cloud on dry overcast days; never a second weather layer."""
    quiet = (safe_float(data.get("rain_mm")) + safe_float(data.get("showers_mm")) <= 0
             and safe_float(data.get("snowfall_cm")) <= 0
             and not data.get("storm_warning", False))
    code = safe_int(data.get("weather_code"), -1)
    cloud_cover = safe_float(data.get("cloud_cover"), -1)
    cloudy = data.get("forecast_ok", False) and (code in (2, 3, 45, 48) or cloud_cover >= 65)
    if not AMBIENT_ACTIVITY or not quiet or not cloudy or not is_daylight(data):
        CLOUD_STATE["active"] = False
        CLOUD_STATE["next_ms"] = 0
        return
    if CLOUD_STATE["next_ms"] == 0:
        roll = star_seed(now_ms // 1000 + 1999)
        wait = (150000 if SCREEN_COUNT > 1 else 300000) + roll % 180001
        CLOUD_STATE["next_ms"] = time.ticks_add(now_ms, wait)
        return
    if not CLOUD_STATE["active"]:
        if time.ticks_diff(now_ms, CLOUD_STATE["next_ms"]) < 0:
            return
        roll = star_seed(now_ms // 100 + 2137)
        CLOUD_STATE["active"] = True
        CLOUD_STATE["start_ms"] = now_ms
        CLOUD_STATE["right"] = bool(roll & 1)
        CLOUD_STATE["y"] = 6 + ((roll >> 3) % 25)
        # Keep cloud speed gentle even on a wider display.
        CLOUD_STATE["duration_ms"] = (WIDTH + 46) * (380 + ((roll >> 7) % 151))
    elapsed = time.ticks_diff(now_ms, CLOUD_STATE["start_ms"])
    duration = CLOUD_STATE["duration_ms"]
    if elapsed >= duration:
        CLOUD_STATE["active"] = False
        CLOUD_STATE["next_ms"] = 0
        return
    progress = elapsed * (WIDTH + 46) // duration
    x = -23 + progress if CLOUD_STATE["right"] else WIDTH + 23 - progress
    graphics.set_pen(cached_pen((19, 23, 28)))
    for dy, (left, right) in enumerate(CLOUD_ROWS):
        graphics.rectangle(x + left, CLOUD_STATE["y"] + dy, right - left + 1, 1)


def draw_surface_event(now_ms):
    """Rare fin/periscope; shares one small state and tracks the live surface."""
    if not AMBIENT_ACTIVITY or GROUND_STATE["kind"] != "rain" or GROUND_STATE["level"] < 8:
        SURFACE_EVENT["active"] = False
        SURFACE_EVENT["next_ms"] = 0
        return
    if SURFACE_EVENT["next_ms"] == 0:
        roll = star_seed(now_ms // 1000 + 3181)
        SURFACE_EVENT["next_ms"] = time.ticks_add(now_ms, 720000 + roll % 780001)
        SURFACE_EVENT["kind"] = "periscope" if ((roll >> 8) % 10) == 0 else "fin"
        return
    if not SURFACE_EVENT["active"]:
        if time.ticks_diff(now_ms, SURFACE_EVENT["next_ms"]) < 0:
            return
        SURFACE_EVENT["active"] = True
        SURFACE_EVENT["start_ms"] = now_ms
        SURFACE_EVENT["right"] = bool(star_seed(now_ms // 100) & 1)
    elapsed = time.ticks_diff(now_ms, SURFACE_EVENT["start_ms"])
    duration = (WIDTH + 24) * 150
    if elapsed >= duration:
        SURFACE_EVENT["active"] = False
        SURFACE_EVENT["next_ms"] = 0
        return
    progress = elapsed * (WIDTH + 24) // duration
    x = -12 + progress if SURFACE_EVENT["right"] else WIDTH + 12 - progress
    direction = 1 if SURFACE_EVENT["right"] else -1
    surface = HEIGHT - GROUND_STATE["level"]
    graphics.set_pen(cached_pen((46, 58, 64)))
    if SURFACE_EVENT["kind"] == "fin":
        for dy, (left, right) in enumerate(FIN_ROWS):
            for dx in range(left, right + 1):
                draw_visible_pixel(x + direction * dx, surface - 4 + dy)
    else:
        # A three-pixel neck and tiny forward-facing eyepiece.
        for dy in range(4):
            draw_visible_pixel(x + direction * 4, surface - 3 + dy)
        draw_visible_pixel(x + direction * 5, surface - 3)
        draw_visible_pixel(x + direction * 6, surface - 3)
        graphics.set_pen(cached_pen((86, 105, 109)))
        draw_visible_pixel(x + direction * 6, surface - 2)
    graphics.set_pen(cached_pen((0, 92, 112)))
    draw_visible_pixel(x - direction * 2, surface)
    draw_visible_pixel(x - direction * 4, surface)


def draw_warning_edges(data, now_ms):
    is_cold = bool(data.get("is_cold", False))
    lightning_hour = safe_int(data.get("lightning_strikes_last_hour", 0)) > 0
    lightning_now = safe_int(data.get("lightning_strikes_last_5_min", 0)) > 0

    # These lightning edge effects remain for visual compatibility with the
    # sensor-backed edition. Open-Meteo cannot provide individual strikes, so
    # the standalone weather source normally leaves both strike counts at zero.
    if lightning_hour and not lightning_now:
        graphics.set_pen(pen_red())
        graphics.rectangle(0, 0, 8, 2)
        graphics.rectangle(0, 0, 2, 8)
        graphics.rectangle(WIDTH - 8, 0, 8, 2)
        graphics.rectangle(WIDTH - 2, 0, 2, 8)
    if lightning_now:
        graphics.set_pen(make_pen(blend_rgb((28, 0, 0), (120, 0, 0), lightning_pulse_amount(now_ms))))
        graphics.rectangle(0, 0, WIDTH, 2)
        graphics.rectangle(0, 62, WIDTH, 2)
        graphics.rectangle(0, 0, 2, 64)
        graphics.rectangle(WIDTH - 2, 0, 2, 64)
    if is_cold:
        graphics.set_pen(pen_blue())
        graphics.rectangle(0, 62, 8, 2)
        graphics.rectangle(0, 56, 2, 8)
        graphics.rectangle(WIDTH - 8, 62, 8, 2)
        graphics.rectangle(WIDTH - 2, 56, 2, 8)


def draw_weather(data, now_ms, pulses, data_fault=False):
    clear_screen()
    drift_step = UI_DRIFT.update(now_ms, min(3, SCREEN_COUNT)) if UI_DRIFT_MINUTES > 0 else 0
    header_drift = clamp(drift_step, -1, 1)
    ui_shift = UI_SHIFT + drift_step
    update_abduction(data, now_ms)
    draw_night_sky(data, now_ms)
    draw_day_rainbow(data, now_ms)
    draw_weather_particles(data, now_ms)
    draw_ground_accumulation(data, now_ms)
    draw_clouds(data, now_ms)
    draw_surface_event(now_ms)

    temperature = data.get("temperature_c", "--")
    humidity = data.get("humidity", "--")
    min_temp = data.get("min_temperature_c", "--")
    max_temp = data.get("max_temperature_c", "--")
    clock_text, clock_second = get_clock_parts()
    humidity_text = format_humidity(humidity)
    temp_text = format_temperature(temperature)
    min_whole, min_fraction = format_daily_temperature_parts(min_temp)
    max_whole, max_fraction = format_daily_temperature_parts(max_temp)
    trend = data.get("pressure_trend", "steady")
    pressure_state = "storm" if data.get("storm_warning", False) else trend

    pulses.update_display(
        clock_text, humidity_text, temp_text,
        min_whole + min_fraction, max_whole + max_fraction,
        pressure_state, now_ms,
    )

    clock_pen = animated_pen((85, 85, 85), pulses.amount("clock", now_ms))
    draw_pixel_text(
        clock_text, 2 + header_drift, 3,
        clock_pen,
        scale=2,
    )
    humidity_x = WIDTH - 2 + header_drift - pixel_text_width(humidity_text, scale=2)
    draw_pixel_text(
        humidity_text, humidity_x, 3,
        animated_pen((0, 95, 105), pulses.amount("humidity", now_ms)),
        scale=2,
    )
    draw_divider_line(16, clock_second, top=True, fault=NETWORK_FAULTS[0])

    temp_scale = 3 if pixel_text_width(temp_text, scale=3) <= 40 else 2
    temp_width = pixel_text_width(temp_text, scale=temp_scale)
    temp_x = ui_shift + max(3, (49 - temp_width) // 2 + 3)
    temp_y = 21 if temp_scale == 3 else 24
    lift_y, beam_fade, temp_visible = abduction_temperature(now_ms)
    temp_y += lift_y
    temp_rgb = blend_rgb(temperature_rgb(temperature), WARM_PULSE_RGB, pulses.amount("temperature", now_ms))
    temp_rgb = tuple(int(channel * beam_fade) for channel in temp_rgb)
    if temp_visible:
        outline_pixel_text(temp_text, temp_x, temp_y, scale=temp_scale)
        draw_pixel_text(temp_text, temp_x, temp_y, make_pen(temp_rgb), scale=temp_scale)

    degree_x = temp_x + temp_width + 1
    if temp_visible:
        graphics.set_pen(BLACK)
        graphics.rectangle(degree_x - 1, temp_y - 1, 4, 4)
        outline_pixel_text(DISPLAY_TEMPERATURE_UNIT, degree_x + 4, temp_y + 2, scale=1)
        unit_rgb = tuple(int(channel * beam_fade) for channel in (85, 85, 85))
        unit_pen = make_pen(unit_rgb)
        graphics.set_pen(unit_pen)
        graphics.rectangle(degree_x, temp_y, 2, 2)
        draw_pixel_text(DISPLAY_TEMPERATURE_UNIT, degree_x + 4, temp_y + 2, unit_pen, scale=1)

    draw_divider_line(42, clock_second, top=False, fault=(NETWORK_FAULTS[1] or not data.get("data_ok", True)))

    # Standalone MIN/MAX are Open-Meteo's forecast minimum and maximum for the
    # complete local calendar day, not observations collected since midnight.
    outline_pixel_text("MIN", ui_shift + 4, 45, scale=1)
    outline_pixel_text("MAX", ui_shift + 26, 45, scale=1)
    draw_pixel_text("MIN", ui_shift + 4, 45, clock_pen, scale=1)
    draw_pixel_text("MAX", ui_shift + 26, 45, clock_pen, scale=1)
    draw_daily_temperature(
        min_temp, ui_shift + 4, 20,
        animated_pen(temperature_rgb(min_temp), pulses.amount("min", now_ms)),
    )
    draw_daily_temperature(
        max_temp, ui_shift + 25, 23,
        animated_pen(temperature_rgb(max_temp), pulses.amount("max", now_ms)),
    )

    # In this edition the triangle is driven by Open-Meteo's WMO thunderstorm
    # codes rather than the home station's local pressure/lightning heuristics.
    if data.get("storm_warning", False):
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            draw_storm_warning(ui_shift + 52 + dx, 50 + dy, BLACK)
        draw_storm_warning(ui_shift + 52, 50, animated_pen((120, 65, 0), storm_pulse_amount(now_ms)))
    else:
        arrow = ARROWS.get(trend, ARROWS["steady"])
        outline_bitmap(arrow, ui_shift + 52, 50, thickness=2)
        draw_bitmap(
            arrow, ui_shift + 52, 50,
            animated_pen(pressure_trend_rgb(trend), pulses.amount("pressure", now_ms)),
            thickness=2,
        )

    for state in FISH_STATES:
        draw_flood_fish(now_ms, state)
    for state in BIRD_STATES:
        draw_day_creature(data, now_ms, clock_second, data_fault, state)
    after_sunset = is_after_sunset(data)
    daylight = is_daylight(data)
    if (after_sunset or daylight) and not ABDUCTION["active"]:
        for state in UFO_STATES:
            draw_ufo(now_ms, daylight=daylight and not after_sunset, state=state)
    draw_abduction(now_ms)
    draw_warning_edges(data, now_ms)

    update_started_ms = time.ticks_ms() if PERFORMANCE_LOGGING else 0
    i75.update(graphics)
    if PERFORMANCE_LOGGING:
        return time.ticks_diff(time.ticks_ms(), update_started_ms)
    return 0


# ---------------------------------------------------------------------------
# Main program
# ---------------------------------------------------------------------------

EMPTY_WEATHER = {
    "temperature_c": "--",
    "temperature_unit": DISPLAY_TEMPERATURE_UNIT,
    "humidity": "--",
    "min_temperature_c": "--",
    "max_temperature_c": "--",
    "is_cold": False,
    "lightning_strikes_last_hour": 0,
    "lightning_strikes_last_5_min": 0,
    "pressure_trend": "steady",
    "storm_warning": False,
    "forecast_ok": False,
    "data_ok": False,
}

show_message("Starting", "weather")
time.sleep(1)

latest_data = dict(EMPTY_WEATHER)
recovery = Recovery(WIFI_SSID, WIFI_PASSWORD)
next_fetch_ms = time.ticks_ms()
last_weather_success_ms = None
weather_day = None
last_day = None
api_failed = False
pulses = PulseTracker()
next_frame_ms = time.ticks_ms()

while True:
    frame_started_ms = time.ticks_ms()
    now_ms = frame_started_ms
    previously_synced = recovery.synced
    connected, recovered = recovery.poll(now_ms) if not DEMO_MODE else (True, False)
    now = time.time()
    if recovery.synced and not previously_synced:
        LOCAL_TIME_CACHE["epoch_second"] = None
    update_local_time_cache(now)
    if not recovery.synced and not DEMO_MODE:
        LOCAL_TIME_CACHE["clock_text"] = "--:--"
    update_festive_button(now_ms)
    local = LOCAL_TIME_CACHE["parts"]
    day = "{:04d}-{:02d}-{:02d}".format(local[0], local[1], local[2])
    day_changed = last_day is not None and day != last_day
    last_day = day
    refresh_seconds = DEMO_REFRESH_SECONDS if DEMO_MODE else WEATHER_REFRESH_SECONDS
    fetch_elapsed_ms = 0
    if recovered or day_changed:
        next_fetch_ms = now_ms
    if connected and time.ticks_diff(now_ms, next_fetch_ms) >= 0:
        fetch_started_ms = time.ticks_ms()
        # A failed request retries in one minute; usable cached data stays visible.
        next_fetch_ms = time.ticks_add(now_ms, 60000)
        try:
            new_data = get_demo_weather() if DEMO_MODE else fetch_weather()
            set_weather_timezone_offset(new_data)
            latest_data = new_data
            weather_day = new_data.get("weather_day") or day
            last_weather_success_ms = time.ticks_ms()
            next_fetch_ms = time.ticks_add(last_weather_success_ms, refresh_seconds * 1000)
            api_failed = False
        except Exception as error:
            api_failed = True
            print("Weather retry deferred:", error)
        fetch_elapsed_ms = time.ticks_diff(time.ticks_ms(), fetch_started_ms)
        gc.collect()

    stale = last_weather_success_ms is None or time.ticks_diff(now_ms, last_weather_success_ms) >= 1800000
    if stale:
        last_weather_success_ms = None  # Latch stale across ticks counter wraps.
    # Do not label cached yesterday extrema as today's values.
    wrong_day = recovery.synced and weather_day is not None and weather_day != day
    if wrong_day:
        latest_data["min_temperature_c"] = "--"
        latest_data["max_temperature_c"] = "--"
    data_fault = not DEMO_MODE and (not connected or api_failed or stale or wrong_day)
    # Upper red bar: Wi-Fi; lower red bar: API/stale/day mismatch.
    NETWORK_FAULTS = (not connected, api_failed or stale or wrong_day)
    update_elapsed_ms = draw_weather(latest_data, now_ms, pulses, data_fault=data_fault)

    # TARGET_FRAME_MS is a complete frame budget, not an additional sleep.
    # Subtract rendering/network time so a 125 ms target is genuinely ~8 FPS.
    frame_elapsed_ms = time.ticks_diff(time.ticks_ms(), frame_started_ms)
    record_performance(now_ms, frame_elapsed_ms, update_elapsed_ms, fetch_elapsed_ms)
    next_frame_ms = time.ticks_add(next_frame_ms, TARGET_FRAME_MS)
    frame_sleep_ms = time.ticks_diff(next_frame_ms, time.ticks_ms())
    if frame_sleep_ms > 0:
        time.sleep_ms(frame_sleep_ms)
    else:
        # Network delays should not cause a burst of catch-up frames.
        next_frame_ms = time.ticks_ms()

