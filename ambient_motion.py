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


def _air_sprite(rows, width):
    # Compile artwork once, grouped by colour to avoid per-frame bitmap scans.
    runs = bytearray()
    for colour in range(1, 6):
        for y, row in enumerate(rows):
            x = 0
            while x < len(row):
                if row[x] != str(colour):
                    x += 1
                    continue
                left = x
                while x < len(row) and row[x] == str(colour):
                    x += 1
                # MicroPython bytearray.extend requires a buffer, not a tuple.
                runs.append(colour - 1)
                runs.append(y)
                runs.append(left)
                runs.append(x - left)
    return width, len(rows), bytes(runs)


# Helicopters keep their pixel size on every panel count. Nose points right.
# 1 outline, 2 body, 3 highlight, 4 shade, 5 glass; empty pixels are transparent.
AIR_SPRITES = (
    _air_sprite((
        '',
        '                1',
        '              111111',
        '             133222211',
        '  11        13322255521',
        '  1211111111122222555521',
        '  1222222222222222255521',
        '   111111111144444444441',
        '             111111111',
        '               1    1',
        '',
        '            111111111111'), 29),
)
AIR_COLOURS = (
    ((18, 22, 30), (128, 42, 38), (185, 105, 85), (68, 24, 26), (55, 120, 145)),
    ((18, 22, 30), (40, 85, 145), (100, 155, 190), (22, 45, 82), (100, 170, 180)),
    ((18, 22, 30), (115, 58, 140), (170, 115, 185), (62, 30, 78), (65, 140, 160)),
    ((18, 22, 30), (42, 115, 74), (115, 170, 110), (22, 62, 40), (80, 145, 170)),
    ((18, 22, 30), (155, 98, 30), (195, 155, 75), (85, 48, 18), (60, 125, 155)),
)


def _towards(position, target, step):
    if position < target:
        return min(target, position + step)
    return max(target, position - step)


class AirVisitor:
    """One sparse background aircraft; bounded state and fixed-point movement."""
    def __init__(self):
        self.active = False
        self.next_ms = None
        self.scheduled_day = None
        self.last_ms = 0
        self.kind = 0
        self.style = 0
        self.x_q = self.y_q = 0
        self.right = True
        self.phase = 'enter'
        self.phase_ms = 0
        self.start_ms = 0
        self.decision_ms = 0
        self.pause_until = 0
        self.target_y = 6
        self.target_x = 0
        self.perch = 16
        self.landing_used = False
        self.turns = 0
        self.roam_ms = 16000
        self.manoeuvres = 0

    def update(self, now_ms, width, daylight, enabled, surface, perches, bar_left, bar_width):
        if not enabled:
            self.active = False
            self.next_ms = None
            return
        if not self.active:
            if self.scheduled_day != daylight:
                self.next_ms = None
                self.scheduled_day = daylight
            if self.next_ms is None:
                roll = seed(now_ms // 1000 + 1999)
                # Wider scenery gets more opportunity, not a doubled population.
                wait = ((180000 + roll % 180001) if width > 64 else
                        (300000 + roll % 240001)) if daylight else 1080000 + roll % 720001
                self.next_ms = time.ticks_add(now_ms, wait)
                return
            if time.ticks_diff(now_ms, self.next_ms) < 0:
                return
            roll = seed(now_ms // 100 + 2137)
            self.active = True
            self.start_ms = self.last_ms = self.phase_ms = now_ms
            self.phase = 'enter'
            self.kind = 0
            self.style = (roll >> 7) % len(AIR_COLOURS)
            self.right = bool(roll & 1)
            sprite_width, height, _ = AIR_SPRITES[self.kind]
            self.x_q = (-sprite_width if self.right else width) * 1000
            self.target_y = min(6 + ((roll >> 12) % 22), max(2, surface - height - 3))
            self.y_q = self.target_y * 1000
            self.decision_ms = time.ticks_add(now_ms, 9000)
            self.pause_until = now_ms
            # Only about one quarter of helicopter visits may try a landing.
            self.landing_used = not daylight or ((roll >> 19) & 3) != 0
            self.turns = 0
            self.roam_ms = (6000 if width == 64 else 10000) + ((roll >> 9) % (6001 if width == 64 else 8001))
            self.manoeuvres = 0
        dt = max(0, min(250, time.ticks_diff(now_ms, self.last_ms)))
        self.last_ms = now_ms
        sprite_width, height, _ = AIR_SPRITES[self.kind]
        max_y = max(2, min(30, surface - height - 3))
        if time.ticks_diff(now_ms, self.start_ms) >= 120000 and self.phase != 'exit':
            self.phase = 'exit'
            self.target_y = min(self.target_y, max_y)
        if self.phase in ('land', 'park') and (not (perches & (1 if self.perch == 16 else 2))):
            # A rising surface or a new bird takes priority over parking.
            self.phase = 'lift'
            self.target_y = max(2, min(max_y, self.perch - height - 7))
        if self.phase == 'park':
            if time.ticks_diff(now_ms, self.phase_ms) >= 3000 + (self.style // 2) * 1000:
                self.phase = 'lift'
                self.target_y = max(2, min(max_y, self.perch - height - 7))
            return
        if self.phase == 'land':
            self.x_q = _towards(self.x_q, self.target_x * 1000, dt * 4)
            self.y_q = _towards(self.y_q, (self.perch - height) * 1000, dt * 2)
            if self.x_q == self.target_x * 1000 and self.y_q == (self.perch - height) * 1000:
                self.phase = 'park'
                self.phase_ms = now_ms
            return
        self.target_y = min(self.target_y, max_y)
        self.y_q = _towards(self.y_q, self.target_y * 1000, dt * (2 if self.phase == 'lift' else 1))
        if self.phase == 'lift':
            if self.y_q == self.target_y * 1000:
                self.phase = 'exit'
            return
        if self.phase == 'roam':
            if time.ticks_diff(now_ms, self.phase_ms) >= self.roam_ms:
                self.phase = 'exit'
            elif self.manoeuvres == 0 and time.ticks_diff(now_ms, self.decision_ms) >= 0:
                self.manoeuvres = 1
                roll = seed(now_ms // 100 + self.style * 137)
                self.decision_ms = time.ticks_add(now_ms, 5000 + roll % 4001)
                if not self.landing_used and perches:
                    self.landing_used = True
                    self.perch = 42 if perches & 2 and roll & 1 else 16
                    if not (perches & 1):
                        self.perch = 42
                    self.target_x = min(bar_left + bar_width - sprite_width - 2,
                                        max(bar_left + 2, self.x_q // 1000 + ((roll >> 8) % 13) - 6))
                    self.phase = 'land'
                    return
                action = (roll >> 6) % 5
                if action == 0:
                    self.pause_until = time.ticks_add(now_ms, 1500 + roll % 1501)
                elif action == 1 and self.turns < 1:
                    self.right = not self.right
                    self.turns += 1
                self.target_y = max(2, min(max_y, self.y_q // 1000 + ((roll >> 10) % 7) - 3))
            if self.phase == 'roam':
                if self.x_q <= 1000:
                    self.right = True
                elif self.x_q >= (width - sprite_width - 1) * 1000:
                    self.right = False
        if self.phase != 'roam' or time.ticks_diff(now_ms, self.pause_until) >= 0:
            self.x_q += (1 if self.right else -1) * dt * 4
        if self.phase == 'enter' and 0 <= self.x_q <= (width - sprite_width) * 1000:
            self.phase = 'roam'
            self.phase_ms = now_ms
        if self.phase == 'exit' and (self.x_q < -sprite_width * 1000 or self.x_q > width * 1000):
            self.active = False
            self.next_ms = None


def draw_air_sprite(visitor, now_ms, graphics, pen, surface=64):
    width, height, runs = AIR_SPRITES[visitor.kind]
    bob = 0 if visitor.phase in ('land', 'park', 'lift') else (0, 1, 0, -1)[(now_ms // 1000) % 4]
    x, y = visitor.x_q // 1000, visitor.y_q // 1000 + bob
    colours = AIR_COLOURS[visitor.style]
    previous = -1
    for i in range(0, len(runs), 4):
        colour, dy, left, length = runs[i], runs[i + 1], runs[i + 2], runs[i + 3]
        if colour != previous:
            graphics.set_pen(pen(colours[colour]))
            previous = colour
        dx = left if visitor.right else width - left - length
        if y + dy < surface:
            graphics.rectangle(x + dx, y + dy, length, 1)
    if y < surface:
        # Keep a steady rotor silhouette; a tiny glint suggests rotation without
        # the old large span changes that looked like blinking/shrinking blades.
        graphics.set_pen(pen((90, 95, 105)))
        left = 4
        dx = left if visitor.right else width - left - 25
        graphics.rectangle(x + dx, y, 25, 1)
        if visitor.phase != 'park':
            graphics.set_pen(pen((135, 140, 150)))
            left = (4, 10, 16, 10)[(now_ms // 250) % 4]
            dx = left if visitor.right else width - left - 4
            graphics.rectangle(x + dx, y, 4, 1)


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
    """Cache four dated events; select local HH:MM and icon progress once a minute."""
    def __init__(self):
        self.raw = None
        self.events = ()
        self.minute = None
        self.value = None

    def update(self, data, now_seconds, event_epoch, event_clock):
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
                    text = event_clock(epoch, data)
                    # Cosmetic depletion over the last three hours, not moon phase.
                    level = min(7, max(1, (remaining * 7 + 179) // 180))
                    self.value = (kind, text, level)
                    break
        return self.value
