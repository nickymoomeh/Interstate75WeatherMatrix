# Interstate75WeatherMatrix

A standalone 64×64 animated LED weather display for the **Pimoroni Interstate 75 W**.

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
- fish when the rain accumulation becomes deep enough
- stars and shooting stars after sunset
- assorted UFOs
- a larger UFO that abducts the centre temperature every half hour after sunset
- festive divider lights during December and early January

The decorative animation runs locally at a target of eight frames per second. Weather is fetched much less frequently, so animation does not depend on Internet latency.

## Hardware

- Pimoroni Interstate 75 W
- 64×64 HUB75 RGB LED matrix
- suitable 5 V power supply for the matrix

The code targets Pimoroni's MicroPython build for the Interstate 75 W.

## Files

- `main.py` — display loop, rendering, animation and runtime state
- `sprites.py` — static pixel artwork, colour palettes and animation-frame data
- `weather_source.py` — Open-Meteo request and translation into the fields used by the display
- `config.py` — normal user-editable settings such as location, timezone, refresh rate and brightness behaviour
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

Open-Meteo returns the correct UTC offset for the requested timezone and the display uses that to convert NTP's UTC clock to local time. This means daylight-saving changes are not hard-coded to the UK.

### 5. Reboot

On boot the display will:

1. initialise the matrix;
2. connect to Wi-Fi;
3. synchronise its clock using NTP;
4. request weather from Open-Meteo;
5. begin the normal animated display.

## Configuration

`config.py` contains the settings most users might reasonably want to change:

```python
LATITUDE = 51.5074
LONGITUDE = -0.1278
TIMEZONE = "Europe/London"
WEATHER_REFRESH_SECONDS = 600
TARGET_FRAME_MS = 125
NIGHT_DIM_FACTOR = 0.35
PERFORMANCE_LOGGING = False
```

The default weather refresh is **10 minutes**. Open-Meteo's weather values do not need to be queried at animation-frame speed.

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

The standalone software structure is complete and ready for testing on physical Interstate 75 W hardware. It was derived from a working sensor-backed display, but the direct Open-Meteo edition should be treated as **pre-release until it has been exercised on the real controller and matrix**.

## Licence

MIT License.
