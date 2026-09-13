# Interstate 75 Weather Matrix - user configuration
#
# This file contains normal, non-secret settings for the display. It is safe to
# keep in Git. Change the location and timezone to match where the matrix will
# be used.

# Example location: London, UK. Replace these with your own coordinates.
LATITUDE = 51.5074
LONGITUDE = -0.1278
TIMEZONE = "Europe/London"

# Open-Meteo data does not need to be requested every few seconds. The weather
# model updates much more slowly than the display animation loop.
WEATHER_REFRESH_SECONDS = 600

# The matrix animation target is eight frames per second.
TARGET_FRAME_MS = 125

# Overall night-time dimming. 0.35 means approximately 35% of daytime output.
NIGHT_DIM_FACTOR = 0.35

# Optional performance diagnostics. Leave False for normal use.
PERFORMANCE_LOGGING = False
