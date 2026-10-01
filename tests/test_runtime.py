"""Run with CPython: python tests/test_runtime.py (no Pico required)."""
import ast, sys, types, re, time as real_time
from pathlib import Path
class Clock:
 now=0
 epoch=1790812800
 def ticks_ms(self): return self.now
 def ticks_add(self,a,b): return (a+b)%(1<<30)
 def ticks_diff(self,a,b): return ((a-b+(1<<29))%(1<<30))-(1<<29)
 def time(self): return self.epoch + self.now//1000
 def localtime(self,t=None): return real_time.gmtime(self.time() if t is None else t)
 def mktime(self,t): return __import__("calendar").timegm(tuple(t)+(0,) if len(t)==8 else t)
 def sleep(self,n): pass
 def sleep_ms(self,n): self.now+=n
clock=Clock()
class Graphics:
 def __init__(self,w): self.w=w;self.pixels=[];self.rects=[]
 def get_bounds(self):return self.w,64
 def create_pen(self,*rgb):return rgb
 def set_pen(self,p):pass
 def clear(self):self.pixels=[];self.rects=[]
 def pixel(self,x,y):self.pixels.append((x,y))
 def rectangle(self,*r):self.rects.append(r)
 def text(self,*a,**kw):pass
class I75:
 def __init__(self,display):self.display=Graphics(display)
 def update(self,*a):pass
 def switch_pressed(self,*a):return False
class WLAN:
 connected=True
 calls=0
 def active(self,*a):pass
 def isconnected(self):return self.connected
 def connect(self,*a):self.calls+=1
 def disconnect(self):pass
wlan=WLAN()
sys.modules['time']=clock
sys.modules['network']=types.SimpleNamespace(WLAN=lambda _:wlan,STA_IF=0)
sys.modules['ntptime']=types.SimpleNamespace(settime=lambda:None)
sys.modules['urequests']=types.SimpleNamespace()
sys.modules['ujson']=__import__('json')
sys.modules['secrets']=types.SimpleNamespace(WIFI_SSID='test',WIFI_PASSWORD='test')
sys.modules['interstate75']=types.SimpleNamespace(Interstate75=I75,SWITCH_A=0,**{'DISPLAY_INTERSTATE75_%dX64'%w:w for w in (64,128,192,256)})
roots = sys.argv[1:] or ['.']
for folder in roots:
 sys.path.insert(0,str(Path(folder).resolve()))
 for panels in (1,2,3,4):
  sys.modules.pop('config',None)
  cfg=types.ModuleType('config')
  cfg_path=Path(folder,'config.py')
  if cfg_path.exists():exec(cfg_path.read_text(),cfg.__dict__)
  cfg.SCREEN_COUNT=panels;sys.modules['config']=cfg
  s=Path(folder,'main.py').read_text()
  s=re.sub(r'^SCREEN_COUNT = [0-9]+', 'SCREEN_COUNT = %d'%panels, s, flags=re.M)
  prefix=s[:s.index('show_message("Starting", "weather")')]
  env={};exec(prefix,env)
  env['NETWORK_FAULTS']=(False,False)
  env['update_local_time_cache'](clock.time())
  for conditions in ({},{'rain_mm':2},{'snowfall_cm':1},{'wind_speed_kmh':50},{'storm_warning':True},{'lightning_strikes_last_5_min':3},{'rain_visual_level':30}):
   data=env['get_demo_weather']();data.update(conditions)
   pulses=env['PulseTracker']()
   for ms in range(0,16000,500):env['draw_weather'](data,ms,pulses)
  assert env['WIDTH']==64*panels
  assert env['day_creature_motion'](10000,10000,True,False)[0]==64*panels+18
  env['graphics'].clear();env['draw_visible_pixel'](64*panels-1,20);assert env['graphics'].pixels
  # No left-half-only clipping of stars/particles.
  env['graphics'].clear();env['is_after_sunset']=lambda _:True;env['draw_night_sky']({},1234)
  assert len(env['graphics'].pixels)>=16*panels
  if panels>1:assert max(x for x,y in env['graphics'].pixels)>=64
  print(folder,panels,'rendering and geometry OK')
  from ambient_checks import exercise
  exercise(env, clock)
  from rainbow_checks import exercise as exercise_rainbow
  exercise_rainbow(env, clock)
  # Optional controls keep the original restrained population and centred UI.
  cfg.AMBIENT_ACTIVITY=False;cfg.UI_DRIFT_MINUTES=0
  restrained={}
  restrained_prefix=prefix.replace('AMBIENT_ACTIVITY = True', 'AMBIENT_ACTIVITY = False')
  restrained_prefix=re.sub(r'^UI_DRIFT_MINUTES = [0-9]+', 'UI_DRIFT_MINUTES = 0', restrained_prefix, flags=re.M)
  exec(restrained_prefix,restrained)
  assert all(len(restrained[name])==1 for name in ('BIRD_STATES','UFO_STATES','FISH_STATES'))
  restrained['is_daylight']=lambda _:True
  restrained['CLOUD_STATE'].update(active=True,next_ms=1000,start_ms=0)
  restrained['draw_clouds'](dict(data,forecast_ok=True,weather_code=3),1000)
  assert not restrained['CLOUD_STATE']['active'] and restrained['UI_DRIFT_MINUTES']==0
  cfg.AMBIENT_ACTIVITY=True;cfg.UI_DRIFT_MINUTES=15
  # Exercise actual main-loop body once, including demo fetch scheduling.
  tree=ast.parse(s); loop=tree.body[-1];assert isinstance(loop,ast.While)
  setup=ast.Module(body=tree.body[tree.body.index(next(n for n in tree.body if isinstance(n,ast.Expr) and isinstance(n.value,ast.Call) and getattr(n.value.func,'id',None)=='show_message' and n.value.args[0].value=='Starting')):-1],type_ignores=[])
  exec(compile(setup,'setup','exec'),env);env['DEMO_MODE']=True
  exec(compile(ast.Module(body=loop.body,type_ignores=[]),'loop','exec'),env)
  body=compile(ast.Module(body=loop.body,type_ignores=[]),'loop','exec')
  env['DEMO_MODE']=False;env['recovery'].synced=True
  env['recovery'].poll=lambda now:(True,False)
  env['fetch_weather']=lambda:dict(data,weather_day=env['day'])
  env['next_fetch_ms']=clock.now
  exec(body,env)
  cached=env['latest_data']['temperature_c']
  def fail():raise OSError('temporary API failure')
  env['fetch_weather']=fail;env['next_fetch_ms']=clock.now
  exec(body,env)
  assert env['latest_data']['temperature_c']==cached
  assert env['NETWORK_FAULTS']==(False,True)
  deadline=env['next_fetch_ms'];exec(body,env);assert env['next_fetch_ms']==deadline
  # Cross midnight while offline; yesterday extrema disappear, temperature remains.
  env['recovery'].poll=lambda now:(False,False)
  clock.epoch+=86400
  exec(body,env)
  assert env['latest_data']['min_temperature_c']=='--'
  assert env['latest_data']['max_temperature_c']=='--'
  assert env['latest_data']['temperature_c']==cached
  env['recovery'].poll=lambda now:(True,True)
  env['fetch_weather']=lambda:dict(data,weather_day=env['day'])
  exec(body,env)
  assert not env['wrong_day'] and not env['api_failed']
  assert env['latest_data']['min_temperature_c']==data['min_temperature_c']

# UK clock transition tests on the retained rules.
for date,expected in [((2026,3,29,0,59,0,0,0),0),((2026,3,29,1,0,0,0,0),1),((2026,10,25,0,59,0,0,0),1),((2026,10,25,1,0,0,0,0),0)]:assert env['uk_utc_offset_hours'](date)==expected
from network_recovery import Recovery
clock.now=0;r=Recovery('test','test');assert r.poll(0)==(True,True);assert r.synced
wlan.connected=False;r.poll(1000);assert wlan.calls
r.poll(26000);assert r.connect_started is None
calls=wlan.calls;r.poll(30000);assert wlan.calls==calls
wlan.connected=True;assert r.poll(40000)==(True,True)
# Daily failure must back off, not retry on every frame.
clock.now=86400000
sys.modules['ntptime'].settime=lambda:(_ for _ in ()).throw(OSError('offline'))
r.poll(clock.now);assert r.next_ntp==86700000
r.poll(clock.now+1);assert r.next_ntp==86700000
print('DST and network recovery/backoff OK')

# The daily response can contain multiple dates: never assume index zero.
import weather_source
class Response:
 status_code=200
 closed=False
 def json(self):return payload
 def close(self):self.closed=True
response=Response()
sys.modules['urequests'].get=lambda *a,**kw:response
payload={"current":{"time":"2026-10-01T12:00","temperature_2m":18},
         "daily":{"time":["2026-09-30","2026-10-01"],
                  "temperature_2m_min":[9,10],"temperature_2m_max":[19,20]}}
result=weather_source.fetch_weather()
assert result['min_temperature_c']==10 and result['max_temperature_c']==20
assert result['weather_day']=='2026-10-01' and response.closed
payload['daily']['time']=[]
assert weather_source.fetch_weather()['min_temperature_c'] is None
print('Open-Meteo daily date selection and response cleanup OK')
