# Interstate 75 Weather Matrix - user configuration
#
# This file contains normal, non-secret settings for the display. It is safe to
# keep in Git. Change the location and timezone to match where the matrix will
# be used.

# Example location: London, UK. Replace these with your own coordinates.
LATITUDE = 51.5074
LONGITUDE = -0.1278
TIMEZONE = "Europe/London"

# Temperature display unit. Open-Meteo will return temperatures directly in
# the selected unit, so no per-frame conversion is needed on the Pico.
# Supported values: "C" or "F".
TEMPERATURE_UNIT = "C"

# Clock display format. Use 24 for e.g. 18:47, or 12 for e.g. 6:47.
# Twelve-hour mode deliberately omits AM/PM to keep the 64x64 layout compact.
CLOCK_FORMAT = 24

# Open-Meteo data does not need to be requested every few seconds. The weather
# model updates much more slowly than the display animation loop.
WEATHER_REFRESH_SECONDS = 600

# The matrix animation target is eight frames per second.
TARGET_FRAME_MS = 125

# Overall night-time dimming. 0.35 means approximately 35% of daytime output.
NIGHT_DIM_FACTOR = 0.35

# Optional performance diagnostics. Leave False for normal use.
PERFORMANCE_LOGGING = False


# Horizontal 64x64 HUB75 panels (1 through 4, subject to firmware/memory).
SCREEN_COUNT = 1

# Sparse extra wildlife/clouds and rare surface visitors; width determines caps.
AMBIENT_ACTIVITY = True
# One-pixel drift step interval. 0 disables; headers move +/-1 pixel, the
# central reading group moves +/-SCREEN_COUNT pixels (capped at 3).
UI_DRIFT_MINUTES = 15

# Dry-weather leaves start at a light breeze; below 8 km/h visits are sparse.
WIND_LEAF_THRESHOLD_KMH = 5

# Spare side space only: countdown to sunset by day / sunrise at night.
SHOW_SOLAR_COUNTDOWN = True
