"""Half-hour event, clipping and shared label-pen regression checks."""
def exercise(env, clock):
    graphics = env['graphics']
    width = env['WIDTH']
    rows = env['RAINBOW_ROWS']
    assert len(rows) == width and rows[0] == rows[-1] == 63
    assert list(rows) == list(reversed(rows)) and min(rows) == 1
    saved = {name: env[name] for name in ('local_time_parts', 'is_daylight', 'is_after_sunset', 'draw_pixel_text')}
    old_night = env['LOCAL_TIME_CACHE']['night']
    parts = [2026, 10, 1, 12, 0, 0, 3, 274]
    env['local_time_parts'] = lambda: tuple(parts)
    env['is_daylight'] = lambda _: True
    env['is_after_sunset'] = lambda _: False
    data = env['get_demo_weather']()
    event = env['RAINBOW']
    try:
        event.update(start_ms=None, last_key=None)
        graphics.clear()
        env['draw_day_rainbow'](data, 1000)
        assert event['start_ms'] == 1000 and not graphics.rects
        cache_sizes = tuple(len(cache) for cache in env['PEN_CACHE'])
        env['draw_day_rainbow'](data, 1375)
        assert tuple(len(cache) for cache in env['PEN_CACHE']) == cache_sizes
        graphics.clear()
        parts[5] = 1
        env['draw_day_rainbow'](data, 1750)
        assert graphics.rects
        assert all(0 <= x and x + w <= width and 0 <= y < 64 and h == 1
                   for x, y, w, h in graphics.rects)
        assert (0, 63, 1, 1) in graphics.rects and (width - 1, 63, 1, 1) in graphics.rects
        assert any(x <= width // 2 < x + w and y == 1 for x, y, w, h in graphics.rects)
        if width > 64:
            assert any(x <= 64 < x + w for x, y, w, h in graphics.rects)
        env['draw_day_rainbow'](data, 7000)
        assert event['start_ms'] is None
        env['draw_day_rainbow'](data, 7100)
        assert event['start_ms'] is None  # Same slot never replays.
        parts[4:6] = [30, 15]
        env['draw_day_rainbow'](data, 8000)
        assert event['start_ms'] is None
        parts[5] = 6  # Slow fetch near the half-hour may still trigger once.
        env['draw_day_rainbow'](data, 9000)
        assert event['start_ms'] == 9000
        graphics.clear()
        event['start_ms'] = (1 << 30) - 1000
        env['draw_day_rainbow'](data, 500)
        assert graphics.rects  # Monotonic wrap remains safe.
        env['is_daylight'] = lambda _: False
        graphics.clear()
        env['draw_day_rainbow'](data, 600)
        assert event['start_ms'] is None and not graphics.rects
        env['is_after_sunset'] = lambda _: True
        parts[3:6] = [0, 0, 0]
        env['ABDUCTION'].update(active=False, last_key=None)
        env['update_abduction'](data, 1000)
        assert env['ABDUCTION']['active']  # Original nighttime event retained.

        # Compare actual pens, including night dimming and clock-change pulses.
        env['ABDUCTION']['active'] = False
        records = []
        original = saved['draw_pixel_text']
        def record(*args, **kwargs):
            records.append((args[0], args[3]))
            return original(*args, **kwargs)
        env['draw_pixel_text'] = record
        for night in (False, True):
            env['LOCAL_TIME_CACHE']['night'] = night
            records.clear()
            env['draw_weather'](data, 3000, env['PulseTracker']())
            pens = {text: pen for text, pen in records}
            clock_text = env['get_clock_parts']()[0]
            assert pens['MIN'] == pens['MAX'] == pens[clock_text]
    finally:
        env.update(saved)
        env['LOCAL_TIME_CACHE']['night'] = old_night
        event.update(start_ms=None, last_key=None)
        env['ABDUCTION']['active'] = False
    print('Day rainbow timing/geometry and MIN/MAX clock pens OK')
