# Interstate75WeatherMatrix

A standalone, configurable-width animated LED weather display for the **Pimoroni Interstate 75 W**.

This project grew out of a sensor-backed home weather matrix that used a Raspberry Pi, InfluxDB and local 433 MHz/BMP280 weather sensors. This edition needs none of that infrastructure: the Interstate 75 W connects directly to Wi-Fi and retrieves its weather data from **Open-Meteo**.

The aim is a project that someone can copy to an Interstate 75 W, enter Wi-Fi credentials and a location, and run.

## What it displays

The matrix shows:

- current temperature
- relative humidity
- today's forecast minimum and maximum temperature
- barometric pressure tendency
- frost/cold indication
- rain and snow animation
- wind-driven precipitation and leaves
- accumulated rain/snow effects
- sunrise/sunset-aware daytime and night-time scenes
- animated birds, ducks and ducklings
- a festive Santa-and-reindeer procession during December and January 1–14
- fish when the rain accumulation becomes deep enough
- stars and shooting stars after sunset
- assorted UFOs, including festive red, white and green craft
- a larger UFO that abducts the centre temperature every half hour after sunset
- festive divider lights during December and early January

The decorative animation runs locally at a target of eight frames per second. Weather is fetched much less frequently, so animation does not depend on Internet latency.

## Hardware

- Pimoroni Interstate 75 W
- one or more horizontally chained 64×64 HUB75 RGB LED matrices
- suitable 5 V power supply for the matrix

The code targets Pimoroni's MicroPython build for the Interstate 75 W.

## Files

- `main.py` — display loop, rendering, animation and runtime state
- `sprites.py` — static pixel artwork, colour palettes and animation-frame data
- `ambient_motion.py` — compact UI drift, fish movement and packed font helpers
- `network_recovery.py` — Wi-Fi recovery and periodic NTP scheduling
- `weather_source.py` — Open-Meteo request and translation into the fields used by the display
- `config.py` — normal user-editable settings such as location, timezone, temperature unit, clock format, refresh rate and brightness behaviour
- `secrets.example.py` — safe Wi-Fi credentials template
- `secrets.py` — your real Wi-Fi credentials; intentionally ignored by Git

Static sprite data is separated from the drawing logic so artwork can be changed without digging through network/weather code. The tuples are imported once at boot; the split does not add work to every animation frame.

## Installation

### 1. Install Pimoroni MicroPython

Install a current Pimoroni MicroPython build that supports the Interstate 75 W and the `interstate75` module.

### 2. Copy the project files

Copy these files to the root of the Interstate 75 W filesystem:

- `main.py`
- `sprites.py`
- `weather_source.py`
- `network_recovery.py`
- `ambient_motion.py`
- `config.py`

### 3. Create `secrets.py`

Copy `secrets.example.py` to `secrets.py` and enter your Wi-Fi details:

```python
WIFI_SSID = "YOUR_WIFI_NAME"
WIFI_PASSWORD = "YOUR_WIFI_PASSWORD"
```

**Do not commit your real `secrets.py`.** It is listed in `.gitignore` so Wi-Fi credentials are not accidentally published.

### 4. Set the location

Edit `config.py`:

```python
LATITUDE = 51.5074
LONGITUDE = -0.1278
TIMEZONE = "Europe/London"
```

The supplied coordinates are an example for central London, not the project author's location. Replace all three values with the location where the display will be used.

`TIMEZONE` should be an IANA timezone name such as:

```text
Europe/London
Europe/Paris
America/New_York
Australia/Sydney
```

Open-Meteo returns the correct UTC offset for the requested timezone and the display uses that to convert NTP's UTC clock to local time. For Europe/London, local GMT/BST transition rules also keep DST correct while offline. Other timezones use the most recently received API offset.

### 5. Choose temperature and clock units if required

The defaults are Celsius and a 24-hour clock:

```python
TEMPERATURE_UNIT = "C"
CLOCK_FORMAT = 24
```

For Fahrenheit and a 12-hour clock:

```python
TEMPERATURE_UNIT = "F"
CLOCK_FORMAT = 12
```

Open-Meteo returns temperature values directly in the selected unit. Fahrenheit therefore does not require repeated conversion in the animation loop. The display's cold-warning threshold and colour bands retain the same physical meanings in either unit.

Twelve-hour mode omits AM/PM to preserve space on the 64×64 display. For example, `18:47` becomes `6:47`; midnight is `12:00`. Twelve-hour mode also omits the leading zero, so `09:00` becomes `9:00`.

The bottom `MIN`/`MAX` readings normally keep one decimal place. In Fahrenheit mode, values of 100°F or above are shown as whole degrees so three-digit temperatures remain legible in the narrow bottom-row areas.

### 6. Reboot

The animation loop starts even if Wi-Fi or NTP is unavailable. Wi-Fi retries automatically; NTP retries every five minutes after failures and approximately daily after success. Until the first successful NTP sync, the clock reads `--:--` while weather can still update.

Set `SCREEN_COUNT = 1` in `config.py` for 64×64, or `SCREEN_COUNT = 2` for 128×64. Counts 1–4 select the matching Pimoroni display mode; unsupported firmware fails with a clear message. The driver configures the HUB75 output width as well as the framebuffer. Both panels must have compatible scan/driver requirements. Connect first-panel OUT to second-panel IN and power both appropriately. See [Pimoroni's Interstate75 implementation](https://github.com/pimoroni/pimoroni-pico/blob/main/micropython/modules_py/interstate75.py).

Sprites and font sizes stay unchanged. Clock and humidity occupy opposite edges; the temperature and lower readings remain a centred cluster. Wider screens show more scenery. Each existing divider/platform grows from 60 to 108 pixels at two panels, centred with continuous rendering across the physical join. Wildlife can cross the physical join. Stars, precipitation, leaves and bubbles maintain density; the main bird and fish waits stay unchanged, while wider displays gain sparse additional actors and modestly more UFO opportunities. Shooting-star schedules stay unchanged.

The upper bar turns red for lost Wi-Fi; the lower bar turns red for request failure, stale/no weather, or previous-day extrema. Normal seconds motion continues in both states. A failed request retains cached readings and retries after one minute; normal Open-Meteo refresh remains ten minutes. After thirty minutes without an update, cached readings are explicitly marked stale. Previous-day extrema become `--` after local midnight and refresh automatically after recovery.

### Hardware checks

1. Confirm the original layout with `SCREEN_COUNT = 1`.
2. With `SCREEN_COUNT = 2`, confirm panel order, colours, scan alignment and brightness, and watch actors cross x=64.
3. Check both platform bars, decimal min/max, rain/snow, ground coverage, night stars and warning edges.
4. Disable Wi-Fi for at least ten minutes, then restore it: expect red upper bar, retained temperature, and recovery without reset.
5. Block Internet/API access with Wi-Fi still connected: expect red lower bar and one-minute retries. Try booting with NTP unavailable, then restoring it.
6. Cross midnight while offline: yesterday extrema must disappear and return with the new day's data after recovery. Check GMT/BST transitions.

Network requests remain synchronous and may briefly pause frames. HTTP socket timeout is eight seconds and NTP timeout is two seconds; firmware DNS resolution may have its own timeout. Desktop tests cannot verify actual scan timing, Pico memory headroom, colour mapping or radio/DNS behaviour. Enable performance logging temporarily when testing two panels.

Run off-device regression checks with `python tests/test_runtime.py`, and syntax-check with `python -m compileall -q .`. The browser emulator remains its existing single-panel demonstration.

## Configuration

`config.py` contains the settings most users might reasonably want to change:

```python
LATITUDE = 51.5074
LONGITUDE = -0.1278
TIMEZONE = "Europe/London"
TEMPERATURE_UNIT = "C"
CLOCK_FORMAT = 24
WEATHER_REFRESH_SECONDS = 600
TARGET_FRAME_MS = 125
NIGHT_DIM_FACTOR = 0.35
PERFORMANCE_LOGGING = False
SCREEN_COUNT = 1
```

The default weather refresh is **10 minutes**. Open-Meteo's weather values do not need to be queried at animation-frame speed.

### Festive mode button

The rear **button A** toggles between normal and festive presentation for the current boot. After a restart, the display returns to automatic mode: festive presentation runs from 1 December through 14 January. The temporary override is intentionally kept in RAM so pressing the button does not cause repeated writes to the Pico's flash storage.

During festive mode, the divider lights become coloured bulbs, some UFOs use Christmas palettes, and Santa with two trotting reindeer can cross the upper line during either daytime or nighttime.

`TARGET_FRAME_MS = 125` gives a target of eight frames per second. The loop treats this as a complete frame budget: rendering time is subtracted before sleeping rather than adding a fixed delay after every rendered frame.

## Weather data

The standalone edition uses Open-Meteo for:

- current temperature
- relative humidity
- mean-sea-level pressure
- three-hour pressure tendency
- rain, showers and snowfall
- precipitation probability
- wind speed, direction and gusts
- today's forecast minimum and maximum temperature
- sunrise and sunset
- WMO weather code / thunderstorm indication
- local UTC offset for the configured timezone

### Daily minimum and maximum

The `MIN` and `MAX` readings are **forecast/model values for the whole local day**.

That differs from the original home version, where the minimum and maximum were calculated from physical thermometer readings actually observed since midnight. No local cache is required for the standalone edition because Open-Meteo supplies the daily values directly.

## Lightning limitation

The original sensor-backed matrix has a physical Fine Offset lightning detector and can react to local strikes almost immediately.

Open-Meteo does not provide equivalent immediate individual strike detections, so the standalone edition cannot reproduce the five-minute/hour lightning edge warnings from real local hardware. Those display paths remain in the code for compatibility, but their strike counts are normally zero.

Instead, WMO thunderstorm weather codes (95, 96 and 99) activate the storm-warning triangle. This is model/weather-condition information, not a real-time local lightning detector.

## Rain and snow accumulation

The home version can persist a shared precipitation reservoir on its Raspberry Pi server. The standalone version has no server, so it maintains its visual rain/snow depth in RAM on the Interstate 75 W and lets it build and drain gradually.

A reboot therefore resets the decorative accumulated water/snow. This does not affect the actual weather readings.

## Network failures

A temporary Open-Meteo or Internet failure does **not** wipe a successfully running display. `main.py` retains the last successful weather response and tries again at the next refresh interval.

Before the first successful fetch, the display shows its fault/placeholder readings rather than inventing weather values.

## Open-Meteo attribution and API use

Weather data is provided by **Open-Meteo.com**. Open-Meteo states that its API weather data is supplied under the **Creative Commons Attribution 4.0 International (CC BY 4.0)** licence, so projects using the data must provide appropriate attribution.

The normal Open-Meteo free/open-access API is intended for **non-commercial use** and is subject to Open-Meteo's published usage limits and terms. If you intend to use this project commercially, check Open-Meteo's current terms and API plans rather than assuming the free endpoint is suitable.

This project's source code is MIT licensed; that is separate from the licence/terms governing weather data obtained from Open-Meteo and its underlying data providers.

## Code comments and contributions

The comments focus on the parts that are not obvious from the code itself: frame timing, MicroPython allocation considerations, weather-provider translation, coordinate-based sprites, animation state and differences from the sensor-backed original.

If you alter artwork, `sprites.py` is the first place to look. If you want to use another weather provider, `weather_source.py` is the intended boundary; ideally it should continue returning the same field names so `main.py` does not need to know where the data came from.

Bug reports, questions and improvements are welcome through **GitHub Issues**. Please do not include Wi-Fi passwords, precise private locations or other credentials in issues, logs or screenshots.

## Status

The standalone build has been tested on a physical Interstate 75 W and 64×64 HUB75 panel and successfully fetched and displayed live Open-Meteo data. It is usable, but remains an evolving hobby project and additional hardware/configuration combinations may reveal edge cases.

## Licence

MIT License.



## Quiet-weather ambient improvements

`AMBIENT_ACTIVITY = True` enables the optional activity; set it to False to keep one actor per family and disable fish surprises, clouds and surface visitors. Width chooses fixed small state pools automatically: one panel allows one bird/day creature, one UFO and one fish; wider displays allow up to three birds/day creatures, two UFOs and two fish. Artwork and palettes stay shared. Extra bird slots only spawn birds, so ducks and festive processions are not duplicated.

The primary bird/day-creature gap remains 20–40 seconds after a visit. Extra bird slots wait 90–210 seconds and 180–420 seconds respectively, with distinct seeds. The primary fish gap remains 20–40 seconds; its second slot waits 110–240 seconds. Two-panel primary UFO waits are 24–48 seconds by day and 16–32 seconds at night, plus a sparse secondary slot (110–220 seconds by day, 70–140 seconds at night). These are independent gaps after visits, not guarantees of a fixed simultaneous population. More than one actor may overlap, but maximum populations should be rare. Existing crossing speeds/durations are retained apart from subtle fish movement changes.

Most fish swim normally. Roughly a quarter of journeys may briefly slow, pause, accelerate or turn; turns mirror the sprite about its centre. A bounded lifetime prevents a repeatedly indecisive fish remaining indefinitely. Fish remain fully below the live waterline; they can pass another fish without sharing state. No collision/pathfinding system is added.

One small shark fin or periscope may traverse the live water surface once water is at least eight pixels deep. Visits are scheduled 12–25 minutes apart while water remains eligible; approximately one in ten is a periscope. Both are dim background sprites rendered before the readings. Dry/shallow conditions cancel the event. No full shark or submarine sprite is allocated.

Dry overcast/mostly cloudy daytime weather (WMO codes 2, 3, 45 or 48) can show one dim six-row cloud crossing slowly: a 2.5–5.5 minute wait on wider displays, 5–8 minutes on one panel. Clouds stop during rain, snow, storm warnings or nighttime and require available forecast conditions. Existing nighttime shooting stars already supply the rare night event, so no duplicate system was added.

`WIND_LEAF_THRESHOLD_KMH = 5` allows occasional leaves in a light breeze. Effective wind remains max(speed, 0.65 × gust). For example, 5.4 km/h with 9.4 km/h gusts yields 6.1 km/h: this was below the old 8 km/h threshold. Winds between 5 and 8 now use a long idle gap; rain/snow still take precedence over leaves.

### Static UI drift

`UI_DRIFT_MINUTES = 15` moves by one pixel every fifteen minutes, starting at the normal centred position. Set 0 to disable. The clock and humidity form a header group moving within ±1 pixel because their edge margins are small. The temperature/unit, daily min/max labels/readings and pressure/storm icon form a central group moving within ±1 pixel at 64×64 and ±2 at 128×64 (capped at ±3 for larger configurations). Each group reverses smoothly; no centre reset or per-frame scrolling occurs. Platforms, warning borders, precipitation, wildlife, clouds and the abduction craft/beam stay in world coordinates. The abduction still operates over the small temperature region; its fixed beam easily covers the drift range.

The former two-pixel seconds-bar gap was caused by explicit black rectangles drawn over x = WIDTH/2 − 1. Removing those cut-outs fixes the underlying cause; the original bar geometry and seconds-position calculation now render continuously.

### Efficiency and validation

Font rows are packed into horizontal runs once at boot (under 400 bytes of run payload per edition). Identical glyph pixels need about 36% fewer rectangle calls across the font inventory, and per-frame glyph-bit scanning is removed. This is a drawing-call saving, not a measured RP2350 frame-rate improvement. Actor pools are allocated once; no sprites/framebuffers are duplicated, and new movement uses small scalar state with fixed-point fish positions. Existing pen caches, frame pacing and network recovery remain.

Desktop regression tests exercise 64/128/192/256 widths, concurrent actor state isolation, join crossing, fish pause/turn/exit, both surface events, cloud suppression, light-breeze leaves, drift extremes and timer wrap, continuous bars, and maximum-cast rain/water/stars scenes. Packed glyphs are pixel-equivalent to the old renderer. Actual RP2350 heap use, HUB75 transfer timing and sustained FPS still require hardware measurement: temporarily enable PERFORMANCE_LOGGING and watch free heap during a busy scene. Test single-panel layout, both drift extremes, quiet-weather clouds/leaves, simultaneous journeys, fish turns and rare surface visitors. The existing browser/desktop emulators remain single-panel demonstrations of the earlier behaviour.
