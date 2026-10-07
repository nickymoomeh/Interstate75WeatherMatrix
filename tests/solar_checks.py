"""Dated sunset/sunrise, DST, drift and decorative-layer regressions."""
from ambient_motion import SolarCountdown


def exercise(env, clock):
    epoch = lambda y, m, d, h, mm=0: clock.mktime((y, m, d, h, mm, 0, 0, 0))
    convert = env['solar_event_epoch']
    data = dict(forecast_ok=True, sunrise_times=['2026-10-06T07:09', '2026-10-07T07:10'],
                sunset_times=['2026-10-06T18:26', '2026-10-07T18:24'])
    countdown = SolarCountdown()
    assert countdown.update(data, epoch(2026, 10, 6, 9), convert, env['solar_event_clock'])[:2] == ('SET', '18:26')
    previous = countdown.value
    assert countdown.update(data, epoch(2026, 10, 6, 9, 0) + 5, convert, env['solar_event_clock']) is previous
    assert countdown.update(data, epoch(2026, 10, 6, 18, 5), convert, env['solar_event_clock'])[:2] == ('RISE', '07:10')
    assert countdown.update(data, epoch(2026, 10, 7, 0), convert, env['solar_event_clock'])[:2] == ('RISE', '07:10')
    assert countdown.update(data, epoch(2026, 10, 7, 6, 9), convert, env['solar_event_clock'])[:2] == ('RISE', '07:10')
    assert countdown.value[2] == 1
    assert countdown.update(data, epoch(2026, 10, 7, 6, 10), convert, env['solar_event_clock'])[:2] == ('SET', '18:24')
    assert countdown.update(data, epoch(2026, 10, 8, 6), convert, env['solar_event_clock']) is None
    assert countdown.update(dict(data, forecast_ok=False), epoch(2026, 10, 6, 9), convert, env['solar_event_clock']) is None
    # Don't silently turn yesterday's single-day timestamps into tomorrow's.
    old = dict(forecast_ok=True, sunrise_time='2026-10-06T07:09', sunset_time='2026-10-06T18:26')
    assert countdown.update(old, epoch(2026, 10, 6, 18), convert, env['solar_event_clock']) is None
    assert convert('not-a-date', {}) is None and convert('2026-13-06T07:00', {}) is None
    assert convert('2026-10-06T07:00Z', {}) == epoch(2026, 10, 6, 7)
    assert countdown.update(dict(data, sunrise_times=9, sunset_times=8), epoch(2026, 10, 6, 9), convert, env['solar_event_clock']) is None
    # Actual elapsed hours through both UK clock changes, not wall-time subtraction.
    fall = dict(forecast_ok=True, sunrise_times=['2026-10-25T07:45'], sunset_times=['2026-10-24T18:00'])
    assert countdown.update(fall, epoch(2026, 10, 24, 17), convert, env['solar_event_clock'])[:2] == ('RISE', '07:45')
    spring = dict(forecast_ok=True, sunrise_times=['2026-03-29T06:45'], sunset_times=['2026-03-28T18:00'])
    assert countdown.update(spring, epoch(2026, 3, 28, 18), convert, env['solar_event_clock'])[:2] == ('RISE', '06:45')
    if 'TIMEZONE' in env:
        zone = env['TIMEZONE']
        try:
            env['TIMEZONE'] = 'America/New_York'
            assert convert('2026-10-06T07:00', {'utc_offset_seconds': -14400}) == epoch(2026, 10, 6, 11)
        finally:
            env['TIMEZONE'] = zone

    graphics = env['graphics']
    original_parts = env['LOCAL_TIME_CACHE']['parts']
    original_epoch = env['LOCAL_TIME_CACHE']['epoch_second']
    saved = {name: env[name] for name in ('draw_day_rainbow', 'draw_air_visitors', 'draw_weather_particles',
                 'draw_ground_accumulation', 'draw_surface_event', 'draw_solar_countdown',
                 'draw_flood_fish', 'draw_day_creature', 'draw_ufo', 'draw_air_sprite')}
    try:
        env['LOCAL_TIME_CACHE']['parts'] = (2026, 10, 6, 10, 0, 0, 1, 279)
        env['NETWORK_FAULTS'] = (False, False)
        for now in (epoch(2026, 10, 6, 9), epoch(2026, 10, 6, 17, 26), epoch(2026, 10, 7, 6, 9)):
            env['LOCAL_TIME_CACHE']['epoch_second'] = now
            for offset in (-min(3, env['SCREEN_COUNT']), 0, min(3, env['SCREEN_COUNT'])):
                graphics.clear()
                env['draw_solar_countdown'](data, offset)
                if env['SCREEN_COUNT'] == 1:
                    assert not graphics.rects and not graphics.pixels
                else:
                    assert graphics.rects
                    assert all(0 <= x and x + w <= env['WIDTH'] and 18 <= y < 41 for x, y, w, h in graphics.rects)
                    assert all(0 <= x < env['WIDTH'] and 25 <= y <= 32 for x, y in graphics.pixels)
        if env['SCREEN_COUNT'] > 1:
            now = epoch(2026, 10, 6, 17, 25)
            # Sinking sun is small near sunset; the shrinking moon stays inside its box.
            env['LOCAL_TIME_CACHE']['epoch_second'] = now
            graphics.clear();env['draw_solar_countdown'](data, 0)
            centre = (env['WIDTH'] + env['UI_SHIFT'] + 64) // 2
            assert any(y == 31 for x, y, w, h in graphics.rects if w < 11 and centre - 5 <= x <= centre + 5)
        enabled = env['SHOW_SOLAR_COUNTDOWN']
        env['SHOW_SOLAR_COUNTDOWN'] = False
        graphics.clear();env['draw_solar_countdown'](data, 0)
        assert not graphics.rects and not graphics.pixels
        env['SHOW_SOLAR_COUNTDOWN'] = enabled
        # No opaque rectangular backing, even where the live water reaches the icon.
        env['GROUND_STATE'].update(kind='rain', level=32)
        graphics.clear();env['draw_solar_countdown'](data, 0)
        assert not any(w == 13 and h == 9 for x, y, w, h in graphics.rects)
        env['AIR_VISITOR'].active = True
        # Verify the actual display call order: aircraft and rainbow under water/text/actors.
        order = []
        for name in saved:
            env[name] = lambda *args, n=name, **kwargs: order.append(n)
        env['draw_weather'](env['get_demo_weather'](), 3000, env['PulseTracker']())
        assert order.index('draw_day_rainbow') < order.index('draw_air_visitors') < order.index('draw_ground_accumulation')
        assert order.index('draw_ground_accumulation') < order.index('draw_solar_countdown') < order.index('draw_air_sprite') < order.index('draw_flood_fish')
        assert order.index('draw_solar_countdown') < order.index('draw_day_creature')
        assert all(max(colour) >= 120 for colour in env['RAINBOW_COLOURS'])
    finally:
        env.update(saved)
        env['LOCAL_TIME_CACHE']['parts'] = original_parts
        env['LOCAL_TIME_CACHE']['epoch_second'] = original_epoch
    print('Solar UTC/date/DST/countdown/drift and decorative layers OK')
