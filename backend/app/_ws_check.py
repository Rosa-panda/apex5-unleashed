# 一次性：验证 /ws 的 motion 推送（30Hz 节流）。
import base64
import json
import os
import socket
import struct
import urllib.request

# 先开总闸（raw 流来数据才有 motion 帧）
req = urllib.request.Request('http://127.0.0.1:18765/api/motion/master',
                             data=b'{"enabled": true}',
                             headers={'Content-Type': 'application/json'}, method='POST')
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
print('master on:', opener.open(req, timeout=5).read().decode()[:60])

s = socket.create_connection(('127.0.0.1', 18765), timeout=5)
key = base64.b64encode(os.urandom(16)).decode()
s.sendall((f'GET /ws HTTP/1.1\r\nHost: 127.0.0.1:18765\r\nUpgrade: websocket\r\n'
           f'Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n').encode())
buf = b''
while b'\r\n\r\n' not in buf:
    buf += s.recv(4096)
print('handshake:', buf.split(b'\r\n')[0].decode())

mot = 0
other = 0
s.settimeout(3)
try:
    while mot < 5 and other < 50:
        hdr = s.recv(2)
        if len(hdr) < 2:
            break
        ln = hdr[1] & 0x7F
        if ln == 126:
            ln = struct.unpack('>H', s.recv(2))[0]
        payload = b''
        while len(payload) < ln:
            payload += s.recv(ln - len(payload))
        evt = json.loads(payload.decode('utf-8'))
        if evt.get('kind') == 'motion':
            mot += 1
            if mot <= 3:
                print('motion:', {k: evt[k] for k in ('tilt', 'source', 'frames')})
        else:
            other += 1
except socket.timeout:
    pass
s.close()
print(f'motion frames: {mot}, other events: {other}')
# 关回总闸（默认态）
req = urllib.request.Request('http://127.0.0.1:18765/api/motion/master',
                             data=b'{"enabled": false}',
                             headers={'Content-Type': 'application/json'}, method='POST')
print('master off:', opener.open(req, timeout=5).read().decode()[:60])
