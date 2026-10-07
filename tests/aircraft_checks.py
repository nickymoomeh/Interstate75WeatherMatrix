"""Aircraft geometry, restrained scheduling and water-safe landing regressions."""
import sys
from ambient_motion import AirVisitor, AIR_SPRITES, draw_air_sprite


def exercise(env, clock):
    module = sys.modules['ambient_motion']
    original_seed = module.seed
    width = env['WIDTH']
    left, bar = env['BAR_LEFT'], env['BAR_WIDTH']
    graphics = env['graphics']

    def update(visitor, now, day=True, surface=64, perches=3, enabled=True):
        visitor.update(clock.ticks_add(0, now), width, day, enabled, surface, perches, left, bar)

    def airborne(kind=0, phase='roam'):
        visitor = AirVisitor()
        visitor.active = True
        visitor.kind = kind
        visitor.phase = phase
        visitor.start_ms = visitor.last_ms = visitor.phase_ms = 0
        visitor.x_q = (width // 2 - 14) * 1000
        visitor.y_q = 10000
        visitor.target_y = 10
        visitor.decision_ms = 999999
        visitor.pause_until = 0
        visitor.landing_used = True
        return visitor

    try:
        # Native-sized shared run sprites, all pixels inside their declared bounds.
        assert [s[:2] for s in AIR_SPRITES] == [(29, 12)]
        assert sum(len(s[2]) for s in AIR_SPRITES) < 700
        for sw, height, runs in AIR_SPRITES:
            assert all(runs[i + 1] < height and runs[i + 2] + runs[i + 3] <= sw
                       for i in range(0, len(runs), 4))
        # Five palettes and both directions; mirroring preserves exact sprite pixels.
        for kind in (0,):
            visitor = airborne(kind)
            visitor.x_q = ((64 if width > 64 else 32) - 16) * 1000
            for style in range(5):
                visitor.style = style
                pixels = []
                for right in (True, False):
                    visitor.right = right
                    graphics.clear()
                    draw_air_sprite(visitor, 0, graphics, env['cached_pen'])
                    assert all(0 <= x and x + w <= width and 0 <= y and y + h <= 64
                               for x, y, w, h in graphics.rects)
                    pixels.append({(x - visitor.x_q // 1000, y) for x, y, w, h in graphics.rects
                                   for x in range(x, x + w) for y in range(y, y + h)})
                assert pixels[1] == {(AIR_SPRITES[kind][0] - 1 - x, y) for x, y in pixels[0]}
                if width > 64:
                    assert any(x < 64 for x, y in pixels[0]) # Local sprite coordinates.
                    assert any(x < 64 < x + w for x, y, w, h in graphics.rects)
        # A helicopter is foreground over the solar icon, but never paints below water.
        visitor = airborne();visitor.y_q = 28000
        graphics.clear();draw_air_sprite(visitor, 0, graphics, env['cached_pen'], surface=32)
        assert graphics.rects and all(y < 32 for x,y,w,h in graphics.rects)
        # Scheduled gaps begin after visits; night gets much rarer opportunities.
        for day in (True, False):
            visitor = AirVisitor()
            update(visitor, 0, day=day)
            wait = visitor.next_ms
            minimum, maximum = ((180000, 360000) if width > 64 else (300000, 540000)) if day else (1080000, 1800000)
            assert minimum <= wait <= maximum
            update(visitor, wait - 1, day=day)
            assert not visitor.active
            update(visitor, wait, day=day)
            assert visitor.active
        # Dawn/dusk changes reset a pending schedule, not multiply opportunities.
        visitor = AirVisitor();update(visitor, 0);day_due = visitor.next_ms
        update(visitor, day_due - 1, day=False)
        assert clock.ticks_diff(visitor.next_ms, day_due) > 600000
        # Fixed-point speed stays 4 px/s at all widths and caps frame gaps.
        visitor = airborne()
        origin = visitor.x_q
        update(visitor, 125)
        assert visitor.x_q - origin == 500
        origin = visitor.x_q
        update(visitor, 8000)
        assert visitor.x_q - origin == 1000
        # Force pause and reversal, preserving position and independent visitor state.
        for action in (0, 1):
            module.seed = lambda _, a=action: a << 6
            visitor = airborne();visitor.decision_ms = 125
            other = airborne();before = dict(other.__dict__)
            origin = visitor.x_q;update(visitor, 125)
            assert other.__dict__ == before
            if action == 0:
                assert visitor.x_q == origin
            else:
                assert not visitor.right and visitor.x_q < origin
        # Some visits never try landing; others park with skids directly above either bar.
        module.seed = lambda _: 0
        for perch, mask in ((16, 1), (42, 2)):
            visitor = airborne();visitor.landing_used = False;visitor.decision_ms = 125
            update(visitor, 125, perches=mask)
            assert visitor.phase == 'land' and visitor.perch == perch
            assert left + 2 <= visitor.target_x <= left + bar - AIR_SPRITES[0][0] - 2
            for now in range(250, 120000, 125):
                update(visitor, now, perches=mask)
                if visitor.phase == 'park':
                    break
            assert visitor.phase == 'park'
            assert visitor.y_q == (perch - 12) * 1000
            graphics.clear();draw_air_sprite(visitor, now, graphics, env['cached_pen'])
            assert max(y + h - 1 for x, y, w, h in graphics.rects) == perch - 1
            # Normal takeoff is gradual, then exits; no second landing on this visit.
            park_end = now + 3000
            update(visitor, park_end, perches=mask)
            assert visitor.phase == 'lift'
            for t in range(park_end + 125, park_end + 240000, 125):
                update(visitor, t, perches=mask)
                if not visitor.active:
                    break
            assert not visitor.active and visitor.next_ms is None
        # A submerged/occupied bar causes immediate takeoff, even mid-descent.
        for phase in ('land', 'park'):
            visitor = airborne(phase=phase);visitor.perch = 42;visitor.y_q = 30000
            update(visitor, 125, surface=41, perches=1)
            assert visitor.phase == 'lift' and visitor.y_q < 30000
        visitor = airborne();visitor.landing_used = False;visitor.decision_ms = 125
        update(visitor, 125, perches=0)
        assert visitor.phase != 'land'
        # Ordinary visits now finish promptly; no repeated hovering/turning loop.
        durations = []
        for roll in (0, 64, 128, 192, 256, 1, 65, 129):
            module.seed = lambda _, value=roll: value | (3 << 19)
            visitor = AirVisitor();visitor.scheduled_day = True;visitor.next_ms = 0
            for now in range(0, 100000, 125):
                update(visitor, now)
                if now > 0 and not visitor.active:
                    break
            assert not visitor.active
            durations.append(now)
            assert visitor.manoeuvres <= 1
        assert max(durations) <= ((width + 29) * 250 + 20000), durations
        print('Ordinary helicopter visits:', min(durations)//1000, '-', max(durations)//1000, 'seconds')
        module.seed = original_seed
        # Real wrapper allows aircraft during rain/snow/storm and blocks unsafe perches.
        saved = env['AIR_VISITOR']
        try:
            for bird in env['BIRD_STATES']:
                bird['active'] = False
            for conditions in ({'rain_mm': 4}, {'snowfall_cm': 2}, {'storm_warning': True}):
                visitor = AirVisitor();visitor.scheduled_day = True;visitor.next_ms = 1000
                env['AIR_VISITOR'] = visitor
                env['GROUND_STATE'].update(kind='rain', level=24)
                env['draw_air_visitors'](dict(env['get_demo_weather'](), **conditions), 1000)
                assert visitor.active
            visitor = airborne(phase='park');visitor.perch = 42;visitor.y_q = 30000
            env['AIR_VISITOR'] = visitor
            env['draw_air_visitors'](env['get_demo_weather'](), 125)
            assert visitor.phase == 'lift'  # Lower bar below the current surface.
            env['GROUND_STATE'].update(kind=None, level=0)
            visitor = airborne(phase='park');visitor.perch = 16;visitor.y_q = 4000
            env['AIR_VISITOR'] = visitor
            env['BIRD_STATES'][0].update(active=True, kind='bird', perch=16)
            env['draw_air_visitors'](env['get_demo_weather'](), 125)
            assert visitor.phase in ('lift', 'exit')
        finally:
            env['AIR_VISITOR'] = saved
            for bird in env['BIRD_STATES']:
                bird['active'] = False
        # A server level jump is applied before this frame's landing decision.
        # This also tests the private edition's immediate persisted-level updates.
        saved = env['AIR_VISITOR']
        try:
            visitor = airborne(phase='park');visitor.perch = 42;visitor.y_q = 30000
            env['AIR_VISITOR'] = visitor
            env['GROUND_STATE'].update(kind=None, level=0)
            data = dict(env['get_demo_weather'](), forecast_ok=True, rain_visual_level=32)
            env['draw_weather'](data, 125, env['PulseTracker']())
            if env['GROUND_STATE']['level'] >= 22:
                assert visitor.phase == 'lift'
        finally:
            env['AIR_VISITOR'] = saved
        # Wrap-safe scheduling/motion and lifetime. No repeated immediate restart.
        visitor = AirVisitor();update(visitor, (1 << 30) - 1000)
        deadline = visitor.next_ms
        update(visitor, deadline)
        assert visitor.active
        visitor = airborne();update(visitor, 211000)
        assert visitor.phase == 'exit'
        update(visitor, 211125, enabled=False)
        assert not visitor.active and visitor.next_ms is None
        print('Aircraft schedules, sprites, motion, weather and landing OK', width)
    finally:
        module.seed = original_seed
