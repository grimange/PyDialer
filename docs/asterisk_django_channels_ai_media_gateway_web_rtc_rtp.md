# Asterisk + Django Channels + AI Media Gateway (WebRTC & RTP)

An end‑to‑end Python reference that replaces Laravel/Vue with **Django Channels** (WebSockets) while keeping Asterisk PBX and an **AI Media Gateway** that handles **WebRTC** and **Raw RTP**. It includes an ARI controller, real‑audio ingest, Whisper transcription, and optional TTS playback.

---

## 0) High‑level Architecture
```
PSTN/ITSP → SBC → Asterisk (B2BUA)
                        │
                        ├─ ARI WS/HTTP  ⇆  ARI Controller (Python asyncio)
                        ├─ ExternalMedia RTP ⇆ AI Media Gateway (WebRTC/RTP)
                        │
                        └─ (optional) SIPREC fork  → AI Media Gateway

AI Media Gateway → (Whisper via OpenAI) → Django API (/ai/events)
                                     └→ (optional TTS → RTP back or file → ARI play)

Django (ASGI + Channels + Redis) → WebSocket groups per call → Agent desktop (HTML/JS)
```

- **Django**: Receives AI events and broadcasts to agents via WebSockets (Channels).
- **ARI Controller**: Manages Asterisk Stasis app and ExternalMedia channels.
- **AI Media Gateway**: Ingests real audio from Asterisk (WebRTC/RTP), calls **OpenAI Whisper** for STT, posts partial/final transcripts back to Django, and can synthesize speech for playback.

---

## 1) Project Layout
```
ai-stack/
├─ django_app/
│  ├─ manage.py
│  ├─ settings.py
│  ├─ asgi.py
│  ├─ urls.py
│  ├─ routing.py
│  ├─ app/
│  │  ├─ consumers.py
│  │  ├─ views.py
│  │  ├─ models.py
│  │  ├─ api.py        # /ai/events webhook
│  │  └─ auth.py
│  └─ requirements.txt
├─ ari_controller/
│  └─ run_ari.py
├─ ai_gateway/
│  ├─ webrtc_gateway.py
│  ├─ rtp_gateway.py
│  ├─ stt_openai.py
│  └─ tts_openai.py (optional)
└─ docker-compose.yml
```

---

## 2) Django (ASGI + Channels)

### 2.1 requirements.txt
```
Django==5.0.7
channels==4.1.0
channels-redis==4.2.0
daphne==4.1.2
redis==5.0.8
uvicorn==0.30.5
requests==2.32.3
```

### 2.2 settings.py (minimal)
```python
# settings.py
import os
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent
SECRET_KEY = 'dev-only'
DEBUG = True
ALLOWED_HOSTS = ['*']
INSTALLED_APPS = [
    'django.contrib.admin','django.contrib.auth','django.contrib.contenttypes',
    'django.contrib.sessions','django.contrib.messages','django.contrib.staticfiles',
    'channels','app',
]
ASGI_APPLICATION = 'asgi.application'
CHANNEL_LAYERS = { 'default': {
    'BACKEND': 'channels_redis.core.RedisChannelLayer',
    'CONFIG': { 'hosts': [os.getenv('REDIS_URL','redis://redis:6379')] }
}}
ROOT_URLCONF = 'urls'
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
]
STATIC_URL = '/static/'
```

### 2.3 asgi.py
```python
# asgi.py
import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
import routing

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')

django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter({
    'http': django_asgi_app,
    'websocket': URLRouter(routing.websocket_urlpatterns),
})
```

### 2.4 routing.py
```python
# routing.py
from django.urls import re_path
from app.consumers import CallConsumer

websocket_urlpatterns = [
    re_path(r'ws/call/(?P<call_id>[^/]+)/$', CallConsumer.as_asgi()),
]
```

### 2.5 consumers.py
```python
# app/consumers.py
from channels.generic.websocket import AsyncJsonWebsocketConsumer

class CallConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.call_id = self.scope['url_route']['kwargs']['call_id']
        self.group = f'call.{self.call_id}'
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group, self.channel_name)

    async def ai_event(self, event):
        # forward to browser
        await self.send_json(event['data'])
```

### 2.6 urls.py + views
```python
# urls.py
from django.urls import path
from app.api import ai_events

urlpatterns = [ path('ai/events', ai_events) ]
```

```python
# app/api.py
import hmac, hashlib, time
from django.http import JsonResponse, HttpResponseForbidden
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.views.decorators.csrf import csrf_exempt
import json, os

SHARED_SECRET = os.getenv('AI_WEBHOOK_SECRET','dev')

@csrf_exempt
def ai_events(request):
    # Optional: verify HMAC signature
    sig = request.headers.get('X-Signature','')
    body = request.body
    check = hmac.new(SHARED_SECRET.encode(), body, hashlib.sha256).hexdigest()
    if sig and sig != check:
        return HttpResponseForbidden('bad signature')

    data = json.loads(body.decode())
    call_id = data.get('call_id','unknown')
    payload = { 'type': data.get('type'), 'payload': data.get('payload',{}) }

    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f'call.{call_id}',
        { 'type': 'ai_event', 'data': payload }
    )
    return JsonResponse({'ok': True})
```

### 2.7 Minimal Browser Client (HTML)
```html
<!doctype html>
<html><body>
<div id="log"></div>
<script>
 const callId = new URLSearchParams(location.search).get('call') || 'TEST1';
 const ws = new WebSocket(`ws://${location.host}/ws/call/${callId}/`);
 ws.onmessage = (e)=>{
   const d = JSON.parse(e.data);
   const el = document.getElementById('log');
   el.innerHTML += `<div>${d.type}: ${JSON.stringify(d.payload)}</div>`;
 };
</script>
</body></html>
```

---

## 3) Asterisk ARI Controller (Python asyncio)
A small daemon that connects to ARI, places inbound calls into a bridge, and attaches **ExternalMedia** to the AI Gateway.

```python
# ari_controller/run_ari.py
import asyncio, json, os, aiohttp, time

ARI_BASE = os.getenv('ARI_BASE','http://asterisk:8088/ari')
ARI_USER = os.getenv('ARI_USER','django')
ARI_PASS = os.getenv('ARI_PASS','secret')
APP_NAME = os.getenv('ARI_APP','ai-app')
AI_HOST = os.getenv('AI_GW_HOST','ai-gateway')
AI_PORT = int(os.getenv('AI_GW_PORT','40000'))  # RTP port
FORMAT  = os.getenv('AI_GW_FORMAT','pcmu')      # pcmu|pcma|slin16

async def post(session, path, **params):
    async with session.post(f"{ARI_BASE}{path}", data=params, auth=aiohttp.BasicAuth(ARI_USER, ARI_PASS)) as r:
        return await r.json()

async def events():
    url = f"{ARI_BASE}/events?app={APP_NAME}&subscribeAll=true"
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(url, auth=aiohttp.BasicAuth(ARI_USER, ARI_PASS)) as ws:
            print('ARI connected')
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    e = json.loads(msg.data)
                    t = e.get('type')
                    if t == 'StasisStart':
                        await on_start(session, e)

async def on_start(session, e):
    ch = e['channel']['id']
    bridge = await post(session, '/bridges', type='mixing')
    bid = bridge['id']
    await post(session, f"/bridges/{bid}/addChannel", channel=ch)

    # Create ExternalMedia: send RTP to AI gateway
    ext = await post(session, '/channels/externalMedia', app=APP_NAME,
                     external_host=f"{AI_HOST}:{AI_PORT}", transport='udp', format=FORMAT)
    ext_id = ext['id']
    await post(session, f"/bridges/{bid}/addChannel", channel=ext_id)
    print('Bridge + externalMedia attached')

if __name__ == '__main__':
    asyncio.run(events())
```

> Dialplan example to enter Stasis:
```asterisk
[from-pstn]
exten => _X.,1,Answer()
 same => n,Stasis(ai-app)
 same => n,Hangup()
```

---

## 4) AI Media Gateway — Real Audio Handling
You can enable **either** WebRTC or RTP (or both).

### 4.1 WebRTC Ingress (`aiortc`)
```python
# ai_gateway/webrtc_gateway.py
import asyncio, os, time, json, requests, numpy as np, soundfile as sf, webrtcvad
from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription, MediaStreamTrack

DJANGO_EVENTS = os.getenv('DJANGO_EVENTS','http://django:8000/ai/events')
VAD = webrtcvad.Vad(2)

class PCMTrack(MediaStreamTrack):
    kind = 'audio'
    def __init__(self, track, call_id):
        super().__init__(); self.track=track; self.call_id=call_id; self.buf=bytearray()
    async def recv(self):
        frame = await self.track.recv()
        samples = frame.to_ndarray()
        if samples.ndim>1: samples = samples.mean(axis=1)
        # naive 48k→16k
        if frame.sample_rate==48000: samples = samples.reshape(-1,3).mean(axis=1)
        pcm16 = (samples*32767).astype('int16').tobytes()
        self.buf.extend(pcm16)
        if len(self.buf) >= 16000*2*0.5:
            chunk = bytes(self.buf); self.buf.clear()
            asyncio.create_task(send_to_stt(self.call_id, chunk))
        return frame

def post_event(call_id, typ, text):
    try:
        requests.post(DJANGO_EVENTS, json={
            'call_id': call_id,
            'type': typ,
            'payload': {'text': text},
            'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        }, timeout=3)
    except Exception as e:
        print('event error', e)

async def send_to_stt(call_id, pcm):
    import io
    import openai
    openai.api_key = os.getenv('OPENAI_API_KEY')
    # write in-memory WAV 16k mono
    import numpy as np, soundfile as sf
    buf = io.BytesIO()
    sf.write(buf, np.frombuffer(pcm, dtype='int16'), 16000, subtype='PCM_16', format='WAV')
    buf.seek(0)
    try:
        from openai import OpenAI
        client = OpenAI(api_key=openai.api_key)
        resp = client.audio.transcriptions.create(model='gpt-4o-mini-transcribe', file=buf)
        post_event(call_id, 'asr.partial', resp.text)
    except Exception as e:
        print('STT error', e)

routes = web.RouteTableDef()

@routes.post('/offer')
async def offer(request):
    p = await request.json(); call_id = p.get('call_id','CALL-'+str(int(time.time()*1000)))
    pc = RTCPeerConnection()
    @pc.on('track')
    def on_track(track):
        if track.kind=='audio':
            pc.addTrack(PCMTrack(track, call_id))
    await pc.setRemoteDescription(RTCSessionDescription(sdp=p['sdp'], type=p['type']))
    answer = await pc.createAnswer(); await pc.setLocalDescription(answer)
    return web.json_response({'sdp': pc.localDescription.sdp, 'type': pc.localDescription.type})

app = web.Application(); app.add_routes(routes)
if __name__=='__main__': web.run_app(app, host='0.0.0.0', port=9001)
```

### 4.2 Raw RTP Ingress (G.711 μ/A‑law)
```python
# ai_gateway/rtp_gateway.py
import asyncio, socket, struct, audioop, time, os, io, requests
import numpy as np, soundfile as sf
from openai import OpenAI

DJANGO_EVENTS = os.getenv('DJANGO_EVENTS','http://django:8000/ai/events')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
RTP_PORT = int(os.getenv('RTP_PORT','40000'))

client = OpenAI(api_key=OPENAI_API_KEY)

def post_event(call_id, typ, text):
    try:
        requests.post(DJANGO_EVENTS, json={
            'call_id': call_id, 'type': typ, 'payload': {'text': text},
            'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        }, timeout=2)
    except Exception as e:
        print('event error', e)

def parse_rtp(pkt):
    if len(pkt)<12: return None
    vpxcc, mpt, seq, ts, ssrc = struct.unpack('!BBHII', pkt[:12])
    pt = mpt & 0x7F
    return {'pt': pt, 'seq': seq, 'ts': ts, 'ssrc': ssrc, 'payload': pkt[12:]}

async def main():
    loop = asyncio.get_running_loop()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('0.0.0.0', RTP_PORT)); sock.setblocking(False)
    buf = bytearray(); call_id='RTP-'+str(int(time.time()))
    print('RTP listening on', RTP_PORT)
    while True:
        data, addr = await loop.sock_recvfrom(sock, 4096)
        r = parse_rtp(data);  
        if not r: continue
        payload = r['payload']
        try:
            pcm = audioop.ulaw2lin(payload, 2)
        except Exception:
            pcm = audioop.alaw2lin(payload, 2)
        buf.extend(pcm)
        if len(buf) >= 8000:  # ~0.5s at 8kHz
            chunk = bytes(buf); buf.clear()
            # resample 8k→16k by simple duplication (demo), replace with proper resampler
            pcm16 = audioop.ratecv(chunk, 2, 1, 8000, 16000, None)[0]
            bio = io.BytesIO()
            sf.write(bio, np.frombuffer(pcm16, dtype='int16'), 16000, format='WAV', subtype='PCM_16')
            bio.seek(0)
            try:
                resp = client.audio.transcriptions.create(model='gpt-4o-mini-transcribe', file=bio)
                post_event(call_id, 'asr.partial', resp.text)
            except Exception as e:
                print('whisper error', e)

if __name__=='__main__': asyncio.run(main())
```

> For quality, replace the simple `ratecv` with a higher‑fidelity resampler (e.g., `samplerate`/`soxr`).

---

## 5) Optional: TTS back into the call
Two paths:
1) **Reverse RTP**: stream synthesized PCM/G711 back to Asterisk `externalMedia` peer.
2) **ARI play**: write TTS WAV to Django `/static/tts/<call_id>.wav`, then `POST /channels/{id}/play?media=http://django:8000/static/tts/...`.

Skeleton using OpenAI TTS producing WAV:
```python
# ai_gateway/tts_openai.py
from openai import OpenAI
import numpy as np, soundfile as sf, io, os
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

def synth_to_wav_bytes(text, voice='verse'):  # voice name depends on provider
    # If using OpenAI TTS: use chat.completions with audio output or a TTS endpoint if available
    # Placeholder: return silent 240ms wav to demonstrate plumbing
    buf = io.BytesIO(); sf.write(buf, np.zeros(16000//4, dtype='int16'), 16000, format='WAV', subtype='PCM_16'); buf.seek(0)
    return buf.read()
```

---

## 6) Docker Compose (dev lab)
```yaml
version: '3.8'
services:
  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]

  django:
    build: ./django_app
    command: daphne -b 0.0.0.0 -p 8000 asgi:application
    environment:
      - REDIS_URL=redis://redis:6379
      - AI_WEBHOOK_SECRET=dev
    ports: ["8000:8000"]
    depends_on: [redis]

  ari:
    build: ./ari_controller
    environment:
      - ARI_BASE=http://asterisk:8088/ari
      - ARI_USER=django
      - ARI_PASS=secret
      - ARI_APP=ai-app
      - AI_GW_HOST=ai-gateway
      - AI_GW_PORT=40000
      - AI_GW_FORMAT=pcmu
    depends_on: [asterisk, django, ai-gateway]

  ai-gateway:
    build: ./ai_gateway
    environment:
      - DJANGO_EVENTS=http://django:8000/ai/events
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - RTP_PORT=40000
    ports: ["9001:9001", "40000:40000/udp"]

  asterisk:
    image: asterisk:18
    network_mode: host  # simplify RTP for lab; tighten in prod
    volumes:
      - ./asterisk/etc:/etc/asterisk
```

---

## 7) Asterisk snippets
`http.conf`
```ini
[general]
enable=yes
bindaddr=0.0.0.0
bindport=8088
```
`ari.conf`
```ini
[general]
enabled = yes
pretty = yes

[django]
type = user
read_only = no
password = secret
```
`extensions.conf`
```asterisk
[from-pstn]
exten => _X.,1,NoOp(Inbound → Stasis ai-app)
 same => n,Answer()
 same => n,Stasis(ai-app)
 same => n,Hangup()
```

---

## 8) Testing
1) **Bring up stack** with valid `OPENAI_API_KEY`.
2) **Call the DID** that lands in `from-pstn`. ARI will create a bridge + externalMedia to the AI Gateway RTP port.
3) **Watch Django WS** at `http://localhost:8000/?call=TEST1` (or the real `call_id`) to see `asr.partial` messages streaming.
4) Flip AI Gateway to WebRTC mode by offering a PeerConnection (`POST /offer`) if you want to test with a WebRTC sender.

---

## 9) Hardening Checklist
- Use **TLS** for ARI and Django endpoints; restrict RTP source IPs.
- Replace naive resampling with **soxr**; add **jitter buffer** & **reorder** on RTP.
- Implement **VAD** gating and **0.3–0.8s** chunking for latency/cost balance.
- Add **HMAC** on `/ai/events` and rotate secrets; log with `call_id` correlation.
- Store transcripts with **redaction** (PAN/CVV); enforce data retention policies.

---

### What next?
- I can add a minimal **agent web UI** page (pure HTML/JS) subscribing to a call group with controls (mute, disposition, notes).
- Or instrument the AI Gateway to also **inject TTS via reverse RTP** for a full virtual‑agent loop.

