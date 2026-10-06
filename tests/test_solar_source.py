"""Run separately with CPython: python tests/test_solar_source.py."""
import ast
import json
import sys
import types
from pathlib import Path
from urllib.parse import urlencode, urlparse, parse_qs

root = Path(__file__).resolve().parents[1]
payload = {'current': {'time': '2026-10-07T10:15', 'temperature_2m': 18, 'pressure_msl': 1002, 'weather_code': 3},
           'daily': {'time': ['2026-10-06', '2026-10-07'],
                     'sunrise': ['2026-10-06T07:09', '2026-10-07T07:10'],
                     'sunset': ['2026-10-06T18:26', '2026-10-07T18:24'],
                     'temperature_2m_min': [13, 10], 'temperature_2m_max': [21, 18]},
           'hourly': {'time': ['2026-10-07T07:00', '2026-10-07T08:00', '2026-10-07T09:00', '2026-10-07T10:00'],
                      'pressure_msl': [1005, 1004, 1003, 1002], 'precipitation_probability': [0, 0, 0, 12]}}
requests = []
class Response:
    status_code = 200
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self): return json.dumps(payload).encode()
    def json(self): return payload
    def close(self): pass

def request(url, **kwargs):
    requests.append(parse_qs(urlparse(url).query))
    return Response()

if (root / 'weather_server.py').exists():
    # Execute the real parsing functions without binding the HTTP server or loading private config.
    tree = ast.parse((root / 'weather_server.py').read_text())
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ('fetch_open_meteo', 'empty_forecast')]
    env = dict(json=json, urlencode=urlencode, urlopen=request, FORECAST_LATITUDE=0, FORECAST_LONGITUDE=0,
               FORECAST_BASE_URL='https://api.open-meteo.com/v1/forecast', FORECAST_TIMEOUT_SECONDS=5)
    exec(compile(ast.Module(body=functions, type_ignores=[]), 'server-parsers', 'exec'), env)
    fetch = env['fetch_open_meteo']
    assert env['empty_forecast']()['sunrise_times'] == []
else:
    sys.path.insert(0, str(root))
    sys.modules['urequests'] = types.SimpleNamespace(get=request)
    import weather_source
    fetch = weather_source.fetch_weather

result = fetch()
assert result['sunrise_time'] == '2026-10-07T07:10'
assert result['sunset_time'] == '2026-10-07T18:24'
assert result['sunrise_times'] == payload['daily']['sunrise']
assert result['sunset_times'] == payload['daily']['sunset']
assert result['precipitation_probability'] == 12
assert requests[-1]['forecast_days'] == ['2'] and requests[-1]['forecast_hours'] == ['1']
if 'min_temperature_c' in result:
    assert result['min_temperature_c'] == 10 and result['max_temperature_c'] == 18
    assert result['pressure_change_3h'] == -3
    assert requests[-1]['past_hours'] == ['3']
payload['daily'] = {}
result = fetch()
assert result['sunrise_times'] == [] and result['sunset_times'] == []
assert result['sunrise_time'] is None
print('Two-day solar response, daily selection, compact hourly request and missing fields OK')
