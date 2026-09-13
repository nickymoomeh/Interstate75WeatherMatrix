"""Standalone 64x64 weather matrix for the Pimoroni Interstate 75 W.

The rendering and animation code is intentionally kept close to the original
sensor-backed display so the standalone edition looks and behaves the same.
Weather acquisition is isolated in weather_source.py and static pixel artwork
lives in sprites.py.

Normal users should only need to edit config.py and create secrets.py.
"""

from interstate75 import Interstate75, DISPLAY_INTERSTATE75_64X64
import network
import time
import ntptime
import gc

from secrets import WIFI_SSID, WIFI_PASSWORD
from config import (
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
    UFO_COLOURS, UFO_DIM_LIGHTS, UFO_DAY_LIGHTS, UFO_BOB,
    BIRD_COLOURS, BIRD_PECK_BODY, BIRD_BODY, BIRD_WING_FRAMES,
    BIRD_WING_SEQUENCE,
    DUCK_BODY, DUCK_HEAD, DUCK_WING, DUCK_BILL, DUCKLING_BODY,
    DUCKLING_BILL, DUCK_COLOURS, DUCK_FAMILY_WIDTH,
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


# ---------------------------------------------------------------------------
# Display and runtime state
# ---------------------------------------------------------------------------

i75 = Interstate75(display=DISPLAY_INTERSTATE75_64X64)
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
    "duration_ms": 6000, "hover_x": 28, "daylight": False,
}
DAY_CREATURE = {
    "active": False, "next_ms": 0, "start_ms": 0, "kind": "bird",
    "species": 0, "perch": 16, "right": True, "duration_ms": 10000,
    "interact": False, "interaction_done": False, "interaction_start_ms": 0,
    "turnaround": False,
}
ABDUCTION = {"active": False, "start_ms": 0, "last_key": None, "colour": 0}


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
    "H": ["101", "101", "111", "101", "101"],
    "I": ["1", "1", "1", "1", "1"],
    "M": ["101", "111", "111", "101", "101"],
    "N": ["101", "111", "111", "111", "101"],
    "X": ["101", "101", "010", "101", "101"],
    " ": ["0", "0", "0", "0", "0"],
}
GLYPH_WIDTHS = {character: max(len(row) for row in glyph) for character, glyph in FONT.items()}

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
        glyph = FONT.get(character, FONT[" "])
        glyph_width = GLYPH_WIDTHS.get(character, 1)
        for row_i, row in enumerate(glyph):
            for col_i, bit in enumerate(row):
                if bit == "1":
                    graphics.rectangle(cursor_x + col_i * scale, y + row_i * scale, scale, scale)
        cursor_x += glyph_width * scale
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

def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if wlan.isconnected():
        print("Already connected:")
        print(wlan.ifconfig())
        return True

    show_message("WiFi", "connecting")
    print("Connecting to WiFi...")
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)

    timeout = 25
    while timeout > 0:
        if wlan.isconnected():
            print("Connected!")
            print(wlan.ifconfig())
            return True
        print("Waiting for WiFi...")
        time.sleep(1)
        timeout -= 1

    print("WiFi failed")
    return False


def sync_time():
    try:
        show_message("Syncing", "time")
        ntptime.settime()
        print("Time synced")
        print(time.localtime())
        return True
    except Exception as error:
        print("Time sync failed:")
        print(error)
        return False


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


def update_local_time_cache(now_seconds=None):
    try:
        epoch_second = int(time.time() if now_seconds is None else now_seconds)
        if LOCAL_TIME_CACHE["epoch_second"] == epoch_second:
            return
        local = time.localtime(epoch_second + LOCAL_TIME_CACHE["utc_offset_seconds"])
        hour = local[3]
        minute = local[4]
        previous_epoch = LOCAL_TIME_CACHE["epoch_second"]
        previous_local = LOCAL_TIME_CACHE["parts"]
        LOCAL_TIME_CACHE["epoch_second"] = epoch_second
        LOCAL_TIME_CACHE["parts"] = local
        if previous_epoch is None or minute != previous_local[4] or hour != previous_local[3]:
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
    return LOCAL_TIME_CACHE["festive"]


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

def get_demo_weather():
    demo_temps = [-2.4, 2.5, 8.0, 13.3, 18.5, 25.0, 28.0, 31.0]
    demo_step = int(time.time() // DEMO_REFRESH_SECONDS) % len(demo_temps)
    temp = demo_temps[demo_step]
    trends = ["rising_fast", "rising_slow", "steady", "falling_slow", "falling_fast"]
    return {
        "temperature_c": temp,
        "humidity": 43 + demo_step,
        "min_temperature_c": -2.4,
        "max_temperature_c": 31.0,
        "is_cold": temp <= 3,
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
        whole, fraction = "{:.1f}".format(float(value)).split(".")
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
    x = 2 + second
    if fault:
        base_rgb, edge_rgb, centre_rgb = (65, 0, 0), (95, 0, 0), (145, 0, 0)
    else:
        base_rgb = (0, 38, 45) if top else (55, 30, 0)
        edge_rgb = (0, 72, 82) if top else (88, 48, 0)
        centre_rgb = (0, 118, 132) if top else (138, 76, 0)

    graphics.set_pen(cached_pen(base_rgb))
    graphics.rectangle(2, y, 60, 1)
    if not fault and is_festive_period():
        offset = 0 if top else 2
        for bulb in range(second + 1):
            graphics.set_pen(cached_pen(FESTIVE_COLOURS[(bulb + offset) % 4]))
            graphics.pixel(2 + bulb, y)
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
    if 0 <= x < 64 and 0 <= y < 64:
        graphics.pixel(int(x), int(y))


def schedule_shooting_star(now_ms):
    seed = star_seed((now_ms // 1000) + 97)
    SHOOTING_STAR["next_ms"] = time.ticks_add(now_ms, 300000 + (seed % 300001))


def schedule_ufo(now_ms, daylight=False):
    seed = star_seed((now_ms // 1000) + 313)
    wait_ms = 30000 + (seed % 30001) if daylight else 20000 + (seed % 20001)
    UFO_STATE["next_ms"] = time.ticks_add(now_ms, wait_ms)
    UFO_STATE["daylight"] = daylight


def draw_ufo(now_ms, daylight=False):
    if UFO_STATE["next_ms"] == 0 or (not UFO_STATE["active"] and UFO_STATE["daylight"] != daylight):
        schedule_ufo(now_ms, daylight)
        return
    if not UFO_STATE["active"]:
        if time.ticks_diff(now_ms, UFO_STATE["next_ms"]) < 0:
            return
        seed = star_seed((now_ms // 1000) + 719)
        mode = (seed >> 3) % 3
        UFO_STATE["active"] = True
        UFO_STATE["start_ms"] = now_ms
        UFO_STATE["right"] = bool(seed & 1)
        UFO_STATE["y"] = 3 + ((seed >> 5) % 25)
        UFO_STATE["colour"] = (seed >> 10) % len(UFO_COLOURS)
        UFO_STATE["style"] = (seed >> 12) % len(UFO_WIDTHS)
        UFO_STATE["mode"] = mode
        UFO_STATE["duration_ms"] = (3800, 7200, 11500)[mode] + UFO_STATE["style"] * 650
        UFO_STATE["hover_x"] = 17 + ((seed >> 13) % 30)

    elapsed = time.ticks_diff(now_ms, UFO_STATE["start_ms"])
    duration = UFO_STATE["duration_ms"]
    if elapsed >= duration:
        UFO_STATE["active"] = False
        schedule_ufo(now_ms, daylight)
        return

    direction = 1 if UFO_STATE["right"] else -1
    style = UFO_STATE["style"]
    width = UFO_WIDTHS[style]
    start_x = -width
    target_x = 63 + width
    if UFO_STATE["mode"] == 2:
        enter_ms = 3000
        leave_ms = 3000
        hover_x = UFO_STATE["hover_x"]
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
        journey = 64 + width * 2
        x = start_x + (elapsed * journey) // duration if direction > 0 else target_x - (elapsed * journey) // duration

    y = UFO_STATE["y"] + UFO_BOB[(elapsed // 300) % len(UFO_BOB)]
    body, lights = UFO_COLOURS[UFO_STATE["colour"]]
    graphics.set_pen(cached_pen((90, 90, 105)))
    for dx, dy in UFO_DOMES[style]:
        draw_visible_pixel(x + dx, y + dy)
    graphics.set_pen(cached_pen(body))
    for row_start, row_end, dy in UFO_ROWS[style]:
        for dx in range(row_start, row_end + 1):
            draw_visible_pixel(x + dx, y + dy)
    light_y = UFO_LIGHT_Y[style]
    light_phase = (elapsed // 375) % 3
    graphics.set_pen(cached_pen(UFO_DIM_LIGHTS[UFO_STATE["colour"]]))
    for dx in UFO_LIGHTS[style]:
        draw_visible_pixel(x + dx, y + light_y)
    active_lights = UFO_DAY_LIGHTS[UFO_STATE["colour"]] if daylight else lights
    graphics.set_pen(cached_pen(active_lights))
    for lamp_index, dx in enumerate(UFO_LIGHTS[style]):
        if (lamp_index + light_phase) % 3 == 0:
            draw_visible_pixel(x + dx, y + light_y)
    if UFO_STATE["mode"] == 2 and 3000 <= elapsed < duration - 3000 and (elapsed // 700) % 2 == 0:
        graphics.set_pen(cached_pen((24, 38, 42)))
        centre_x = width // 2
        beam_y = UFO_BEAM_Y[style]
        draw_visible_pixel(x + centre_x, y + beam_y)
        draw_visible_pixel(x + centre_x, y + beam_y + 1)


def schedule_day_creature(now_ms):
    seed = star_seed((now_ms // 1000) + 911)
    DAY_CREATURE["next_ms"] = time.ticks_add(now_ms, 20000 + (seed % 20001))


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


def day_creature_motion(elapsed, duration, origin_right, turnaround):
    if not turnaround:
        return (elapsed * 82) // duration, origin_right, False
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
    return progress, origin_right if phase < 525 else not origin_right, 450 <= phase < 600


def draw_day_creature(data, now_ms, second, data_fault=False):
    if not is_daylight(data):
        DAY_CREATURE["active"] = False
        DAY_CREATURE["next_ms"] = 0
        return
    if DAY_CREATURE["next_ms"] == 0:
        schedule_day_creature(now_ms)
        return
    if not DAY_CREATURE["active"]:
        if time.ticks_diff(now_ms, DAY_CREATURE["next_ms"]) < 0:
            return
        seed = star_seed((now_ms // 1000) + 1237)
        perches = [16, 42, 63]
        if GROUND_STATE["level"]:
            surface = 64 - GROUND_STATE["level"]
            perches = [perch for perch in perches if perch < surface]
        duck_visit = (seed & 7) == 0
        DAY_CREATURE["active"] = True
        DAY_CREATURE["start_ms"] = now_ms
        DAY_CREATURE["kind"] = "duck" if duck_visit else "bird"
        DAY_CREATURE["species"] = (seed >> 4) % len(BIRD_COLOURS)
        DAY_CREATURE["perch"] = 16 if duck_visit else perches[(seed >> 7) % len(perches)]
        DAY_CREATURE["right"] = bool(seed & 1)
        DAY_CREATURE["duration_ms"] = (12000 + ((seed >> 11) % 4001)) if duck_visit else (7000 + ((seed >> 11) % 5001))
        interaction_roll = (seed >> 16) % 6
        DAY_CREATURE["interact"] = not duck_visit and interaction_roll < 2
        DAY_CREATURE["interaction_done"] = False
        DAY_CREATURE["interaction_start_ms"] = 0
        DAY_CREATURE["turnaround"] = False if duck_visit else ((seed >> 19) & 3) == 0

    raw_elapsed = time.ticks_diff(now_ms, DAY_CREATURE["start_ms"])
    hold_ms = 900
    interaction_age = time.ticks_diff(now_ms, DAY_CREATURE["interaction_start_ms"])
    held_ms = clamp(interaction_age, 0, hold_ms) if DAY_CREATURE["interaction_done"] else 0
    elapsed = raw_elapsed - held_ms
    duration = DAY_CREATURE["duration_ms"]
    if elapsed >= duration:
        DAY_CREATURE["active"] = False
        schedule_day_creature(now_ms)
        return

    # Ducks deliberately use the upper strip (y=8). That keeps them visible
    # when rainwater/snow occupies the bottom of the display.
    if DAY_CREATURE["kind"] == "duck":
        progress = (elapsed * (64 + DUCK_FAMILY_WIDTH)) // duration
        x = -DUCK_FAMILY_WIDTH + progress if DAY_CREATURE["right"] else 64 - progress
        draw_duck_family(x, 8, DAY_CREATURE["right"], elapsed)
        return

    progress, right, stopped = day_creature_motion(
        elapsed, duration, DAY_CREATURE["right"], DAY_CREATURE["turnaround"]
    )
    x = -18 + progress if DAY_CREATURE["right"] else 64 - progress
    perch = DAY_CREATURE["perch"]
    hop = 0 if stopped else (0, 0, -1, -2, -1, 0, 0, 0)[(elapsed // 150) % 8]
    front_x = x + 16 if right else x
    if (
        DAY_CREATURE["interact"]
        and not DAY_CREATURE["interaction_done"]
        and not data_fault
        and perch in (16, 42)
        and abs(front_x - (2 + second)) <= 2
    ):
        DAY_CREATURE["interaction_done"] = True
        DAY_CREATURE["interaction_start_ms"] = now_ms
        interaction_age = 0

    interacting = DAY_CREATURE["interaction_done"] and 0 <= interaction_age < hold_ms
    y = perch - 14 + hop
    body, breast, wing, beak = BIRD_COLOURS[DAY_CREATURE["species"]]
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
        x = -23 + (45 * elapsed // 1500)
    elif elapsed < 9000:
        x = 22
    else:
        x = 22 + (48 * (elapsed - 9000) // 1500)
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
                for bx in range(31 - half, 32 + half):
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

    for index in range(16):
        cadence = 23000 + index * 3700
        epoch = now_ms // cadence
        seed = star_seed(epoch + index * 101)
        x = 2 + (seed % 60)
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
    travel = (elapsed * 70) // 2000
    x = -3 + travel if SHOOTING_STAR["right"] else 66 - travel
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


def wind_dx_percent(direction):
    sector = int((safe_float(direction) + 11.25) // 22.5) % 16
    return WIND_DX_BY_SECTOR[sector]


def draw_weather_particles(data, now_ms):
    if not data.get("forecast_ok", False):
        return

    rain_mm = max(safe_float(data.get("rain_mm")), safe_float(data.get("showers_mm")))
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
        for index in range(count):
            phase_ms = (now_ms + index * 337) % cycle_ms
            y = (phase_ms * 72) // cycle_ms - 5
            seed_x = 3 + ((index * 19 + 7) % 58)
            drift_x = (phase_ms * drift_tenths) // (cycle_ms * 10)
            x = 2 + ((seed_x - 2 + drift_x) % 60)
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
        for index in range(count):
            phase_ms = (now_ms + index * 911) % cycle_ms
            y = (phase_ms * 70) // cycle_ms - 3
            seed_x = 3 + ((index * 23 + 11) % 58)
            drift_x = (phase_ms * drift_tenths) // (cycle_ms * 10)
            wave_index = ((phase_ms * 8) // cycle_ms + index) % 8
            x = 2 + ((seed_x - 2 + drift_x + SNOW_FLUTTER[wave_index]) % 60)
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

    if effective_wind >= 8:
        leaf_count = 1 if effective_wind < 20 else 2 if effective_wind < 40 else 4
        travel_ms = max(3600, 7600 - int(effective_wind * 65))
        interval_ms = travel_ms + 3000
        travels_right = wind_dx >= 0
        for index in range(leaf_count):
            phase_ms = (now_ms + index * 1900) % interval_ms
            if phase_ms >= travel_ms:
                continue
            if travels_right:
                x = -3 + (phase_ms * 70) // travel_ms
                tip_dx = 1
            else:
                x = 66 - (phase_ms * 70) // travel_ms
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
    rain_mm = max(safe_float(data.get("rain_mm")), safe_float(data.get("showers_mm")))
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
        for x in range(64):
            height = min(21, level + bank[(x // 4) % len(bank)])
            graphics.rectangle(x, 64 - height, 1, height)
        graphics.set_pen(cached_pen((112, 125, 134)))
        for x in range(64):
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
        graphics.rectangle(0, surface_y + band_start, 64, band_height)
    graphics.set_pen(cached_pen((0, 72, 102)))
    graphics.rectangle(0, surface_y, 64, 1)

    wind_dx = wind_dx_percent(data.get("wind_direction_deg"))
    for ripple in range(2):
        phase = (now_ms + ripple * 1900) % 4400
        if phase >= 2100:
            continue
        centre = (18, 45)[ripple] + (wind_dx * phase) // 21000
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
        for bubble in range(min(7, 2 + level // 5)):
            cycle = 2600 + bubble * 370
            phase = (now_ms + bubble * 641) % cycle
            rise = (phase * bubble_span) // cycle
            bx = 4 + ((bubble * 17 + 9) % 56) + UFO_BOB[(phase // 300 + bubble) % len(UFO_BOB)]
            by = 62 - rise
            graphics.set_pen(cached_pen((20, 88, 112) if bubble % 3 else (34, 112, 138)))
            draw_visible_pixel(bx, by)
            if bubble % 3 == 0 and level >= 14:
                draw_visible_pixel(bx + 1, by - 1)


def fish_seed(now_ms):
    seed = (now_ms // 1000) & 0x7FFFFFFF
    return (seed * 1103515245 + 12345) & 0x7FFFFFFF


def schedule_next_fish(now_ms):
    seed = fish_seed(now_ms)
    FISH_STATE["next_ms"] = time.ticks_add(now_ms, 20000 + (seed % 20001))


def draw_flood_fish(now_ms):
    if GROUND_STATE["kind"] != "rain" or GROUND_STATE["level"] < 8:
        FISH_STATE["active"] = False
        FISH_STATE["next_ms"] = 0
        return

    surface_y = 64 - GROUND_STATE["level"]
    min_y = surface_y + 1
    if FISH_STATE["active"] and FISH_STATE["y"] < min_y:
        FISH_STATE["y"] = min_y
    if FISH_STATE["next_ms"] == 0:
        schedule_next_fish(now_ms)
        return
    if not FISH_STATE["active"]:
        if time.ticks_diff(now_ms, FISH_STATE["next_ms"]) < 0:
            return
        seed = fish_seed(now_ms)
        species = (seed >> 7) % len(FISH_WIDTHS)
        fish_height = FISH_HEIGHTS[species]
        y_span = max(1, (64 - fish_height) - min_y + 1)
        FISH_STATE["active"] = True
        FISH_STATE["start_ms"] = now_ms
        FISH_STATE["right"] = bool(seed & 1)
        FISH_STATE["y"] = min_y + ((seed >> 3) % y_span)
        FISH_STATE["species"] = species
        FISH_STATE["colour"] = (seed >> 11) % len(FISH_COLOURS)
        FISH_STATE["travel_ms"] = (7600, 9800, 12400)[species] + ((seed >> 15) % 1800)

    travel_ms = FISH_STATE["travel_ms"]
    elapsed_ms = time.ticks_diff(now_ms, FISH_STATE["start_ms"])
    if elapsed_ms >= travel_ms:
        FISH_STATE["active"] = False
        schedule_next_fish(now_ms)
        return

    species = FISH_STATE["species"]
    width = FISH_WIDTHS[species]
    height = FISH_HEIGHTS[species]
    journey = 64 + width * 2
    if FISH_STATE["right"]:
        x = -width + (elapsed_ms * journey) // travel_ms
        direction = 1
    else:
        x = 63 + width - (elapsed_ms * journey) // travel_ms
        direction = -1

    y = FISH_STATE["y"]
    graphics.set_pen(cached_pen(FISH_COLOURS[FISH_STATE["colour"]]))
    middle = height // 2
    for dy in range(height):
        distance = abs(middle - dy)
        row_start = 2 + (distance // 2)
        row_end = width - 1 - distance
        for dx in range(row_start, row_end + 1):
            draw_visible_pixel(x + direction * dx, y + dy)

    tail_shift = FISH_TAIL_SHIFT[(elapsed_ms // 375) % len(FISH_TAIL_SHIFT)]
    graphics.set_pen(cached_pen(FISH_ACCENTS[FISH_STATE["colour"]]))
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
        graphics.rectangle(56, 0, 8, 2)
        graphics.rectangle(62, 0, 2, 8)
    if lightning_now:
        graphics.set_pen(make_pen(blend_rgb((28, 0, 0), (120, 0, 0), lightning_pulse_amount(now_ms))))
        graphics.rectangle(0, 0, 64, 2)
        graphics.rectangle(0, 62, 64, 2)
        graphics.rectangle(0, 0, 2, 64)
        graphics.rectangle(62, 0, 2, 64)
    if is_cold:
        graphics.set_pen(pen_blue())
        graphics.rectangle(0, 62, 8, 2)
        graphics.rectangle(0, 56, 2, 8)
        graphics.rectangle(56, 62, 8, 2)
        graphics.rectangle(62, 56, 2, 8)


def draw_weather(data, now_ms, pulses):
    clear_screen()
    update_abduction(data, now_ms)
    draw_night_sky(data, now_ms)
    draw_weather_particles(data, now_ms)
    draw_ground_accumulation(data, now_ms)

    temperature = data.get("temperature_c", "--")
    humidity = data.get("humidity", "--")
    min_temp = data.get("min_temperature_c", "--")
    max_temp = data.get("max_temperature_c", "--")
    clock_text, clock_second = get_clock_parts()
    humidity_text = format_humidity(humidity)
    temp_text = format_temperature(temperature)
    data_fault = not data.get("data_ok", True)
    min_whole, min_fraction = format_daily_temperature_parts(min_temp)
    max_whole, max_fraction = format_daily_temperature_parts(max_temp)
    trend = data.get("pressure_trend", "steady")
    pressure_state = "storm" if data.get("storm_warning", False) else trend

    pulses.update_display(
        clock_text, humidity_text, temp_text,
        min_whole + min_fraction, max_whole + max_fraction,
        pressure_state, now_ms,
    )

    draw_pixel_text(
        clock_text, 2, 3,
        animated_pen((85, 85, 85), pulses.amount("clock", now_ms)),
        scale=2,
    )
    humidity_x = 62 - pixel_text_width(humidity_text, scale=2)
    draw_pixel_text(
        humidity_text, humidity_x, 3,
        animated_pen((0, 95, 105), pulses.amount("humidity", now_ms)),
        scale=2,
    )
    draw_divider_line(16, clock_second, top=True, fault=data_fault)

    temp_scale = 3 if pixel_text_width(temp_text, scale=3) <= 40 else 2
    temp_width = pixel_text_width(temp_text, scale=temp_scale)
    temp_x = max(3, (49 - temp_width) // 2 + 3)
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
        outline_pixel_text("C", degree_x + 4, temp_y + 2, scale=1)
        unit_rgb = tuple(int(channel * beam_fade) for channel in (120, 120, 120))
        unit_pen = make_pen(unit_rgb)
        graphics.set_pen(unit_pen)
        graphics.rectangle(degree_x, temp_y, 2, 2)
        draw_pixel_text("C", degree_x + 4, temp_y + 2, unit_pen, scale=1)

    draw_divider_line(42, clock_second, top=False, fault=data_fault)

    # Standalone MIN/MAX are Open-Meteo's forecast minimum and maximum for the
    # complete local calendar day, not observations collected since midnight.
    outline_pixel_text("MIN", 4, 45, scale=1)
    outline_pixel_text("MAX", 26, 45, scale=1)
    draw_pixel_text("MIN", 4, 45, pen_secondary(), scale=1)
    draw_pixel_text("MAX", 26, 45, pen_secondary(), scale=1)
    draw_daily_temperature(
        min_temp, 4, 20,
        animated_pen(temperature_rgb(min_temp), pulses.amount("min", now_ms)),
    )
    draw_daily_temperature(
        max_temp, 25, 23,
        animated_pen(temperature_rgb(max_temp), pulses.amount("max", now_ms)),
    )

    # In this edition the triangle is driven by Open-Meteo's WMO thunderstorm
    # codes rather than the home station's local pressure/lightning heuristics.
    if data.get("storm_warning", False):
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            draw_storm_warning(52 + dx, 50 + dy, BLACK)
        draw_storm_warning(52, 50, animated_pen((120, 65, 0), storm_pulse_amount(now_ms)))
    else:
        arrow = ARROWS.get(trend, ARROWS["steady"])
        outline_bitmap(arrow, 52, 50, thickness=2)
        draw_bitmap(
            arrow, 52, 50,
            animated_pen(pressure_trend_rgb(trend), pulses.amount("pressure", now_ms)),
            thickness=2,
        )

    draw_flood_fish(now_ms)
    draw_day_creature(data, now_ms, clock_second, data_fault)
    after_sunset = is_after_sunset(data)
    daylight = is_daylight(data)
    if (after_sunset or daylight) and not ABDUCTION["active"]:
        draw_ufo(now_ms, daylight=daylight and not after_sunset)
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

while not connect_wifi():
    show_message("WiFi", "waiting")
    time.sleep(10)

sync_time()

latest_data = dict(EMPTY_WEATHER)
last_fetch = 0
pulses = PulseTracker()
next_frame_ms = time.ticks_ms()

while True:
    frame_started_ms = time.ticks_ms()
    now = time.time()
    now_ms = frame_started_ms
    update_local_time_cache(now)
    refresh_seconds = DEMO_REFRESH_SECONDS if DEMO_MODE else WEATHER_REFRESH_SECONDS
    fetch_elapsed_ms = 0

    if now - last_fetch >= refresh_seconds:
        fetch_started_ms = time.ticks_ms()
        if DEMO_MODE:
            latest_data = get_demo_weather()
            last_fetch = now
            print("Demo weather updated")
        else:
            try:
                new_data = fetch_weather()
                set_weather_timezone_offset(new_data)
                latest_data = new_data
                last_fetch = now
                print("Open-Meteo weather updated")
            except Exception as error:
                # A temporary Internet/API failure should not wipe a perfectly
                # usable display. Keep the last successful values and retry at
                # the next normal refresh. Before the first success the fault
                # placeholder remains visible.
                print("Weather fetch failed:")
                print(error)
                last_fetch = now
        fetch_elapsed_ms = time.ticks_diff(time.ticks_ms(), fetch_started_ms)
        # HTTP/JSON parsing allocates temporary objects. Reclaim them here so
        # garbage collection does not interrupt an arbitrary animation frame.
        gc.collect()

    update_elapsed_ms = draw_weather(latest_data, now_ms, pulses)

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
