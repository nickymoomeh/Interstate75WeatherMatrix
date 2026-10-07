"""Desktop assertions for layout and independent ambient actor state."""
import sys
from ambient_motion import UIDrift, start_fish_motion, move_fish


def exercise(env, clock):
    width = env['WIDTH']
    panels = env['SCREEN_COUNT']
    noop = lambda *args, **kwargs: None
    graphics = env['graphics']
    data = env['get_demo_weather']()
    data.update(forecast_ok=True, weather_code=3, rain_mm=0, showers_mm=0,
                snowfall_cm=0, wind_speed_kmh=0, wind_gust_kmh=0)
    env['is_daylight'] = lambda _: True
    env['is_after_sunset'] = lambda _: False
    env['is_festive_period'] = lambda: False
    assert len(env['BIRD_STATES']) == (3 if panels > 1 else 1)
    assert len(env['UFO_STATES']) == (2 if panels > 1 else 1)
    assert len(env['FISH_STATES']) == (2 if panels > 1 else 1)
    for name in ('BIRD_STATES', 'UFO_STATES', 'FISH_STATES'):
        assert len({id(state) for state in env[name]}) == len(env[name])

    # Start every bird independently, prove no cross-state mutation, then render the join.
    env['GROUND_STATE'].update(kind=None, level=0)
    birds = env['BIRD_STATES']
    for i, bird in enumerate(birds):
        for other in birds:
            other['active'] = False
            other['next_ms'] = 1000
        snapshots = [dict(state) for state in birds]
        env['draw_day_creature'](data, 1000 + i * 125, 20, state=bird)
        assert bird['active']
        for j, other in enumerate(birds):
            if i != j:
                assert other == snapshots[j]
    graphics.clear()
    for i, bird in enumerate(birds):
        bird.update(active=True, kind='bird', start_ms=1000 + i * 125,
                    duration_ms=10000, right=bool(i & 1), turnaround=False)
        env['draw_day_creature'](data, 6500, 20, state=bird)
    assert len(graphics.pixels) > 0
    if panels > 1:
        assert any(x >= 64 for x, y in graphics.pixels)

    ufos = env['UFO_STATES']
    for i, ufo in enumerate(ufos):
        for other in ufos:
            other.update(active=False, next_ms=1000, daylight=True)
        snapshots = [dict(state) for state in ufos]
        env['draw_ufo'](1000 + i * 125, True, ufo)
        assert ufo['active']
        for j, other in enumerate(ufos):
            if i != j:
                assert other == snapshots[j]
    if panels > 1:
        assert ufos[0]['start_ms'] != ufos[1]['start_ms']

    # A normal fish must traverse the world and leave; pause and turn preserve its centre.
    fish = dict(slot=0, right=True, start_ms=0, travel_ms=10000)
    start_fish_motion(fish, 0, width, 11)
    fish['quirky'] = False
    centres = []
    for ms in range(0, 12000, 125):
        centre, direction, finished = move_fish(fish, ms, width, 11)
        centres.append(centre)
        if finished:
            break
    assert finished and centres[-1] > width
    assert all(a <= b for a, b in zip(centres, centres[1:]))
    fish.update(centre_q=40000, last_motion_ms=0, mode_until_ms=2000,
                speed_percent=0, start_ms=0, right=True)
    assert move_fish(fish, 125, width, 11)[0] == 40
    fish.update(speed_percent=100, right=False)
    centre, direction, _ = move_fish(fish, 250, width, 11)
    assert direction == -1 and centre < 40
    # Force each surprise via deterministic roll, including an actual sprite direction flip.
    module = sys.modules['ambient_motion']
    original_seed = module.seed
    try:
        for action, percent in ((0, 45), (1, 0), (2, 145), (3, 100)):
            module.seed = lambda _, a=action: a << 5
            fish = dict(slot=0, right=True, start_ms=0, travel_ms=10000)
            start_fish_motion(fish, 0, width, 11)
            fish.update(quirky=True, centre_q=40000, behaviour_ms=125)
            centre, direction, _ = move_fish(fish, 125, width, 11)
            assert fish['speed_percent'] == percent
            assert direction == (-1 if action == 3 else 1)
    finally:
        module.seed = original_seed

    env['GROUND_STATE'].update(kind='rain', level=20)
    for i, state in enumerate(env['FISH_STATES']):
        state.update(active=False, next_ms=1000)
        env['draw_flood_fish'](1000 + i * 125, state)
        assert state['active']
    snapshots = [dict(state) for state in env['FISH_STATES']]
    env['draw_flood_fish'](1500, env['FISH_STATES'][0])
    for j in range(1, len(snapshots)):
        assert env['FISH_STATES'][j] == snapshots[j]

    # Fin and periscope sit at the live surface; draining disables the visitor.
    event = env['SURFACE_EVENT']
    for kind in ('fin', 'periscope'):
        event.update(active=True, next_ms=1000, start_ms=0, kind=kind, right=True)
        graphics.clear()
        env['draw_surface_event']((width + 24) * 75)
        assert graphics.pixels
        assert all(40 <= y <= 44 for x, y in graphics.pixels)
    env['GROUND_STATE']['level'] = 7
    env['draw_surface_event'](5000)
    assert not event['active']

    # The reported light-breeze sample draws leaves; calm weather does not.
    graphics.clear()
    env['draw_weather_particles'](dict(data, wind_speed_kmh=5.4,
                                    wind_gust_kmh=9.4, wind_direction_deg=197), 3000)
    assert graphics.pixels
    graphics.clear()
    env['draw_weather_particles'](data, 3000)
    assert not graphics.pixels

    # Drift starts at centre, takes single-pixel steps and reverses without jumps/wrap errors.
    drift = UIDrift(900000)
    assert drift.update(0, 2) == 0
    offsets = [drift.update(ms, 2) for ms in range(900000, 9900001, 900000)]
    assert offsets[:8] == [1, 2, 1, 0, -1, -2, -1, 0]
    drift.last_ms = (1 << 30) - 400000
    drift.offset = 0
    drift.direction = 1
    assert drift.update(500000, 2) == 1

    # Render only static content at every drift extreme and both warning alternatives.
    function_names = ('update_abduction', 'draw_night_sky', 'draw_weather_particles',
                      'draw_ground_accumulation', 'draw_air_visitors', 'draw_surface_event',
                      'draw_flood_fish', 'draw_day_creature', 'draw_ufo', 'draw_abduction',
                      'draw_warning_edges')
    functions = {name: env[name] for name in function_names}
    for name in function_names:
        env[name] = noop
    try:
        env['ABDUCTION']['active'] = False
        env['NETWORK_FAULTS'] = (False, False)
        pulses = env['PulseTracker']()
        for drift_offset in (-min(3, panels), 0, min(3, panels)):
            env['UI_DRIFT'].offset = drift_offset
            env['UI_DRIFT'].last_ms = 0
            for storm in (False, True):
                static = dict(data, humidity=100, temperature_c=-40.1,
                              min_temperature_c=-40.1, max_temperature_c=38.5,
                              storm_warning=storm)
                env['draw_weather'](static, 0, pulses)
                assert all(x >= 0 and x + w <= width for x, y, w, h in graphics.rects)
                assert all(0 <= x < width for x, y in graphics.pixels)
                # Both base bars really cover the former physical-seam pixels.
                for y in (16, 42):
                    assert (env['BAR_LEFT'], y, env['BAR_WIDTH'], 1) in graphics.rects
                    assert not any(x == width // 2 - 1 and yy == y and w == 2 and h == 1
                                   for x, yy, w, h in graphics.rects)
    finally:
        env.update(functions)

    # Packed glyphs reproduce exactly the old bitmaps at all font scales.
    run_calls = old_calls = 0
    for character, glyph in env['FONT'].items():
        old_calls += sum(row.count('1') for row in glyph)
        run_calls += len(env['GLYPH_RUNS'][character]) // 3
        for scale in (1, 2, 3):
            graphics.clear()
            env['draw_pixel_text'](character, 4, 2, env['BLACK'], scale)
            actual = {(x + dx, y + dy) for x, y, w, h in graphics.rects
                      for dx in range(w) for dy in range(h)}
            expected = {(4 + x * scale + dx, 2 + y * scale + dy)
                        for y, row in enumerate(glyph) for x, bit in enumerate(row)
                        if bit == '1' for dx in range(scale) for dy in range(scale)}
            assert actual == expected
    assert run_calls < old_calls
    print('Ambient/drift/state checks OK; glyph calls', old_calls, '->', run_calls,
          'packed bytes', sum(len(r) for r in env['GLYPH_RUNS'].values()))

    # Force the maximum daytime cast, rain and deep water; then repeat at night with stars.
    storm_data = dict(data, rain_mm=3, storm_warning=True,
                      lightning_strikes_last_5_min=3, rain_visual_level=32)
    env['GROUND_STATE'].update(kind='rain', level=32)
    env['ABDUCTION']['active'] = False
    env['is_daylight'] = lambda _: True
    env['is_after_sunset'] = lambda _: True
    for i, bird in enumerate(env['BIRD_STATES']):
        bird.update(active=True, kind='bird', start_ms=0, duration_ms=10000,
                    perch=16, right=bool(i & 1), turnaround=False)
    for i, ufo in enumerate(env['UFO_STATES']):
        ufo.update(active=True, start_ms=0, duration_ms=10000, mode=0,
                   y=6 + i * 13, right=bool(i & 1), style=i, colour=i, festive=False)
    for i, fish_state in enumerate(env['FISH_STATES']):
        fish_state.update(active=True, start_ms=0, travel_ms=14000, right=bool(i & 1),
                          species=i, colour=i, y=40 + i * 9)
        start_fish_motion(fish_state, 0, width, env['FISH_WIDTHS'][i])
        fish_state.update(centre_q=(width // 2 + i * 10) * 1000,
                          last_motion_ms=3000, quirky=False)
    event.update(active=True, start_ms=0, next_ms=1000, kind='fin', right=True)
    env['UI_DRIFT'].offset = 0
    aircraft = env['AIR_VISITOR']
    aircraft.active = True
    aircraft.kind = 1
    aircraft.phase = 'roam'
    aircraft.x_q = (width // 2 - 14) * 1000
    aircraft.y_q = 6000
    aircraft.target_y = 6
    aircraft.start_ms = aircraft.last_ms = aircraft.phase_ms = 3000
    aircraft.decision_ms = 9000
    aircraft.pause_until = 3000
    aircraft.landing_used = True
    env['draw_weather'](storm_data, 3000, env['PulseTracker']())
    assert aircraft.active
    assert all(0 <= x < width and 0 <= y < 64 for x, y in graphics.pixels)
    assert all(s['active'] for s in env['BIRD_STATES'])
    assert all(s['active'] for s in env['UFO_STATES'])
    assert all(s['active'] for s in env['FISH_STATES'])
    print('Maximum cast scene calls:', len(graphics.pixels), 'pixels,', len(graphics.rects), 'rectangles')
