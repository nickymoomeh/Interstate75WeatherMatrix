"""Allocation-light movement helpers shared by both weather display editions."""
import time


def seed(value):
    return (value * 1103515245 + 12345) & 0x7fffffff


class UIDrift:
    """Move one pixel per interval, starting at centre and reversing smoothly."""
    def __init__(self, interval_ms):
        self.interval_ms = max(60000, int(interval_ms))
        self.offset = 0
        self.direction = 1
        self.last_ms = None

    def update(self, now_ms, limit=1):
        if self.last_ms is None:
            self.last_ms = now_ms
        elif time.ticks_diff(now_ms, self.last_ms) >= self.interval_ms:
            self.last_ms = now_ms
            if self.offset >= limit:
                self.direction = -1
            elif self.offset <= -limit:
                self.direction = 1
            self.offset += self.direction
        return self.offset


def start_fish_motion(state, now_ms, width, sprite_width):
    state["centre_q"] = (-sprite_width if state["right"] else width + sprite_width) * 1000
    state["speed_q"] = (width + 2 * sprite_width) * 1000000 // state["travel_ms"]
    state["last_motion_ms"] = now_ms
    state["behaviour_ms"] = time.ticks_add(now_ms, 2500)
    state["mode_until_ms"] = now_ms
    state["speed_percent"] = 100
    state["turns"] = 0
    state["quirky"] = seed(now_ms // 100 + state["slot"] * 97) % 4 == 0


def move_fish(state, now_ms, width, sprite_width):
    """Integrate centre position; direction flips preserve the sprite centre."""
    elapsed = time.ticks_diff(now_ms, state["start_ms"])
    # Cap network-induced frame gaps; actors don't teleport after a slow request.
    dt = max(0, min(250, time.ticks_diff(now_ms, state["last_motion_ms"])))
    state["last_motion_ms"] = now_ms
    if time.ticks_diff(now_ms, state["mode_until_ms"]) >= 0:
        state["speed_percent"] = 100
    if state["quirky"] and time.ticks_diff(now_ms, state["behaviour_ms"]) >= 0:
        roll = seed(now_ms // 17 + state["slot"] * 139)
        action = (roll >> 5) % 5
        state["behaviour_ms"] = time.ticks_add(now_ms, 4500 + (roll % 3501))
        state["mode_until_ms"] = time.ticks_add(now_ms, 650 + ((roll >> 8) % 1201))
        if action == 0:
            state["speed_percent"] = 45
        elif action == 1:
            state["speed_percent"] = 0
        elif action == 2:
            state["speed_percent"] = 145
        elif action == 3 and state["turns"] < 2:
            state["right"] = not state["right"]
            state["turns"] += 1
    direction = 1 if state["right"] else -1
    state["centre_q"] += direction * (dt * state["speed_q"] // 1000) * state["speed_percent"] // 100
    centre = state["centre_q"] // 1000
    finished = elapsed > 1000 and (centre < -sprite_width or centre > width + sprite_width)
    # Safety lifetime for a fish that turns/pauses repeatedly.
    finished = finished or elapsed >= state["travel_ms"] * 4
    return centre, direction, finished


# One shared, lobed cartoon cloud; no duplicated sprite buffers.
CLOUD_WIDTH = 33
CLOUD_ROWS = (((10, 13),), ((8, 15),), ((7, 16), (22, 25)),
              ((6, 18), (20, 27)), ((4, 29),), ((2, 30),),
              ((1, 31),), ((0, 32),), ((0, 32),), ((1, 31),),
              ((3, 29),), ((5, 27),))
FIN_ROWS = ((6, 6), (5, 6), (4, 6), (3, 7), (2, 8))


def compile_glyph_runs(font):
    """Pack each horizontal glyph run into three bytes: row, column, length."""
    result = {}
    for character, glyph in font.items():
        runs = bytearray()
        for y, row in enumerate(glyph):
            x = 0
            while x < len(row):
                if row[x] != "1":
                    x += 1
                    continue
                start = x
                while x < len(row) and row[x] == "1":
                    x += 1
                runs.append(y)
                runs.append(start)
                runs.append(x - start)
        result[character] = bytes(runs)
    return result


def rainbow_profile(width, height):
    """Outer elliptical arc, calculated once; one byte per display column."""
    span = width - 1
    denominator = span * span
    rows = bytearray(width)
    for x in range(width):
        distance = 2 * x - span
        rise = (max(0, denominator - distance * distance) / denominator) ** 0.5
        rows[x] = height - 1 - int((height - 2) * rise + 0.5)
    return rows


class SolarCountdown:
    """Keep only four dated events; parse on refresh and format once a minute."""
    def __init__(self):
        self.raw = None
        self.events = ()
        self.minute = None
        self.value = None

    def update(self, data, now_seconds, event_epoch):
        if not data.get("forecast_ok", False):
            self.minute = None
            self.value = None
            return None
        rises = data.get("sunrise_times") or (data.get("sunrise_time"),)
        sets = data.get("sunset_times") or (data.get("sunset_time"),)
        if not isinstance(rises, (list, tuple)):
            rises = (data.get("sunrise_time"),)
        if not isinstance(sets, (list, tuple)):
            sets = (data.get("sunset_time"),)
        raw = (rises, sets, data.get("utc_offset_seconds", 0))
        if raw != self.raw:
            events = []
            for kind, values in (("RISE", rises), ("SET", sets)):
                for value in values[:2]:
                    epoch = event_epoch(value, data)
                    if epoch is not None:
                        events.append((epoch, kind))
            events.sort()
            self.events = tuple(events)
            self.raw = raw
            self.minute = None
        minute = int(now_seconds) // 60
        if minute != self.minute:
            self.minute = minute
            self.value = None
            for epoch, kind in self.events:
                if now_seconds < epoch <= now_seconds + 172800:
                    remaining = max(1, (epoch - int(now_seconds) + 59) // 60)
                    text = "{}:{:02d}".format(remaining // 60, remaining % 60)
                    # Cosmetic depletion over the last three hours, not moon phase.
                    level = min(7, max(1, (remaining * 7 + 179) // 180))
                    self.value = (kind, text, level)
                    break
        return self.value
