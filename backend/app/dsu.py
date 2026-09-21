# DSU/Cemuhook UDP 体感桥（体验区 #18）：监听 127.0.0.1:26760，把 0xEF 运动流
# 翻译成 DSU 协议喂给 Yuzu/Cemu/Dolphin/PCSX2——DS4Windows/BetterJoy 喂体感的
# 同一条标准通路。手柄留在 XInput 模式（工具照常工作），模拟器的 Motion 映射即可绑定。
#
# 协议事实（https://v1993.github.io/cemuhook-protocol/，v1001）：
#   二进制包，小端。头 16B：magic("DSUC"=客户端 / "DSUS"=服务端) + ver u16(1001) +
#   len u16(不含头) + crc32 u32(整包、本字段置零参与计算) + server_id u32。
#   之后 4B 消息类型：0x100000 版本 / 0x100001 控制器信息 / 0x100002 数据流 /
#   0x110001 马达数 / 0x110002 震动（非官方）。数据包总长 100B。
#   accel 单位 g、gyro 单位 deg/s、时间戳 µs。
#
# 轴向默认映射（推导自迷宫实测符号：平放 az=+1g、前倾 ay 增、右倾 ax 减；
# DSU 期望 DS4 姿态系：x 右 / y 上 / z 朝用户）：
#   accel = (-ax, az, ay) / 4096；gyro pitch/yaw/roll = (g0, g2, g1) * 0.05
# 符号若有反手感，面板三轴 invert 开关现场翻——真机验收钩子（同 #1 的 gain）。
import socket
import struct
import threading
import time
import zlib

from maze import GYRO_DPS_PER_LSB

DEFAULT_PORT = 26760
ACCEL_PER_G = 4096.0         # 实测（maze 同款）
PROTO_VER = 1001
CLIENT_TIMEOUT = 5.0         # 客户端消失后停止发包
RUMBLE_TIMEOUT = 5.0         # 规范建议：收不到震动包就归零，防卡震
STREAM_HZ = 100              # 数据包发送频率（0xEF ~300Hz 足够喂）
MAGIC_C = b"DSUC"
MAGIC_S = b"DSUS"
T_VERSION = 0x100000
T_INFO = 0x100001
T_DATA = 0x100002
T_MOTORS = 0x110001
T_RUMBLE = 0x110002
# 假 MAC：固定即可（用途=客户端跨启动识别同一设备，稳定比真实重要）
FAKE_MAC = bytes([0x37, 0xD7, 0x00, 0x00, 0x00, 0x01])
ALLOW_HOSTS = {"127.0.0.1", "::1"}


def _packet(msg_type, payload, server_id):
    """拼一个 DSUS 包：头 16B + 类型 4B + payload，CRC32 按 8..12 置零计算。"""
    body = struct.pack("<I", msg_type) + payload
    total = 16 + len(body)
    pkt = bytearray(MAGIC_S + struct.pack("<HHI", PROTO_VER, total - 16, 0)
                    + struct.pack("<I", server_id) + body)
    crc = zlib.crc32(bytes(pkt)) & 0xFFFFFFFF
    struct.pack_into("<I", pkt, 8, crc)
    return bytes(pkt)


class DsuServer:
    def __init__(self, engine, port=DEFAULT_PORT):
        self.engine = engine
        self.port = port
        self.enabled = False
        self.server_id = int(time.time()) & 0xFFFFFFFF
        self.invert = [False, False, False]    # gyro pitch/yaw/roll 反符号（真机手感钩子）
        self._sock = None
        self._rx_thread = None
        self._tx_thread = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._motion = None                    # 最新一帧 (t, ax, ay, az, g0, g1, g2)
        self._clients = {}                     # addr -> {flags, slot, mac, last_seen, pkt_num}
        self._rumble = [0, 0]                  # motor0/1 强度 0..255
        self._last_rumble_seen = 0.0
        self._last_rumble_sent = None
        self.stats = {"packets": 0, "info_reqs": 0, "data_reqs": 0, "bad": 0,
                      "motion_sent": 0, "clients": 0, "last_error": None, "note": None}

    # ---------- engine.subscribe_motion 回调（0xEF 运动流 → 最新帧缓存） ----------
    def on_motion(self, m):
        ax, ay, az = m["accel"]
        g0, g1, g2 = m["gyro"]
        with self._lock:
            self._motion = (m["t"], ax, ay, az, g0, g1, g2)

    # ---------- 生命周期 ----------
    def start(self, port=None):
        if self.enabled:
            return self.status()
        requested = int(port or self.port)
        self._stop.clear()
        # Yuzu 默认就找 26760，端口顺延只作兜底；真被占了必须在 note 里大声说
        self._sock = None
        last_err = None
        for p in range(requested, requested + 10):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.bind(("127.0.0.1", p))
            except OSError as e:
                last_err = e
                continue
            self._sock = s
            self.port = p
            break
        if self._sock is None:
            raise OSError(f"UDP {requested}..{requested + 9} 全被占用，最后错误：{last_err}")
        self._sock.settimeout(0.5)
        self._rx_thread = threading.Thread(target=self._rx_loop, daemon=True, name="dsu-rx")
        self._tx_thread = threading.Thread(target=self._tx_loop, daemon=True, name="dsu-tx")
        self._rx_thread.start()
        self._tx_thread.start()
        self.enabled = True
        self.stats["note"] = (f"端口 {requested} 被占用，实际监听 {self.port}"
                              if self.port != requested else None)
        return self.status()

    def stop(self):
        self._stop.set()
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
        self._sock = None
        self.enabled = False
        self._clients.clear()
        self._rumble = [0, 0]
        self._apply_rumble(force=True)     # 停桥把震动归零（防卡震）
        return self.status()

    # ---------- 接收：解析 DSUC 请求 ----------
    def _rx_loop(self):
        while not self._stop.is_set():
            try:
                data, addr = self._sock.recvfrom(256)
            except socket.timeout:
                continue
            except OSError:
                break
            if addr[0] not in ALLOW_HOSTS:
                continue
            self.stats["packets"] += 1
            try:
                self._handle(data, addr)
            except Exception as e:
                self.stats["bad"] += 1
                self.stats["last_error"] = f"{type(e).__name__}: {e}"

    def _handle(self, data, addr):
        if len(data) < 20 or data[:4] != MAGIC_C:
            self.stats["bad"] += 1
            return
        ver, length = struct.unpack_from("<HH", data, 4)
        crc = struct.unpack_from("<I", data, 8)[0]
        if ver != PROTO_VER or 16 + length > len(data):
            self.stats["bad"] += 1
            return
        chk = bytearray(data[:16 + length])
        struct.pack_into("<I", chk, 8, 0)
        if (zlib.crc32(bytes(chk)) & 0xFFFFFFFF) != crc:
            self.stats["bad"] += 1
            return
        msg_type = struct.unpack_from("<I", data, 16)[0]
        if msg_type == T_VERSION:
            self._send(_packet(T_VERSION, struct.pack("<H", PROTO_VER), self.server_id), addr)
        elif msg_type == T_INFO:
            self.stats["info_reqs"] += 1
            n = struct.unpack_from("<i", data, 20)[0]
            for i in range(min(n, 4)):
                slot = data[24 + i] if 24 + i < len(data) else 0
                self._send(self._info_packet(slot), addr)
        elif msg_type == T_DATA:
            self.stats["data_reqs"] += 1
            flags = data[20]
            slot = data[21]
            mac = bytes(data[22:28])
            with self._lock:
                c = self._clients.get(addr) or {"pkt_num": 0}
                c.update({"flags": flags, "slot": slot, "mac": mac,
                          "last_seen": time.monotonic()})
                self._clients[addr] = c
                self.stats["clients"] = len(self._clients)
        elif msg_type == T_MOTORS:
            self._send(_packet(T_MOTORS, self._ident(data[21]) + bytes([2]), self.server_id), addr)
        elif msg_type == T_RUMBLE:
            motor = data[28]
            intensity = data[29]
            if motor in (0, 1):
                self._rumble[motor] = intensity
                self._last_rumble_seen = time.monotonic()

    def _ident(self, slot):
        """11B 控制器头：槽位/已连接/全陀螺/USB + MAC + 电量。"""
        bat = self.engine.battery or {}
        if bat.get("charging"):
            b = 0xEE
        else:
            b = max(1, min(5, int(bat.get("level") or 0))) or 0x01
        return bytes([slot, 2, 2, 1]) + FAKE_MAC + bytes([b])

    def _info_packet(self, slot):
        return _packet(T_INFO, self._ident(slot) + b"\x00", self.server_id)

    def _send(self, pkt, addr):
        try:
            self._sock.sendto(pkt, addr)
        except OSError as e:
            self.stats["last_error"] = f"{type(e).__name__}: {e}"

    # ---------- 发送：100Hz 数据流 + 震动超时归零 ----------
    def _tx_loop(self):
        interval = 1.0 / STREAM_HZ
        next_t = time.monotonic()
        while not self._stop.is_set():
            now = time.monotonic()
            next_t += interval
            with self._lock:
                expired = [a for a, c in self._clients.items()
                           if now - c["last_seen"] > CLIENT_TIMEOUT]
                for a in expired:
                    del self._clients[a]
                self.stats["clients"] = len(self._clients)
                clients = list(self._clients.items())
            if now - self._last_rumble_seen > RUMBLE_TIMEOUT and any(self._rumble):
                self._rumble = [0, 0]
            self._apply_rumble()
            for addr, c in clients:
                with self._lock:
                    motion = self._motion
                pkt = self._data_packet(motion, c["pkt_num"])
                c["pkt_num"] += 1
                self._send(pkt, addr)
                self.stats["motion_sent"] += 1
            delay = next_t - time.monotonic()
            if delay > 0:
                if self._stop.wait(delay):
                    break
            else:
                next_t = time.monotonic()

    def _data_packet(self, motion, pkt_num=0):
        """100B 数据包。按钮/摇杆/触摸全零——Yuzu 的按键走 XInput 直连，
        本桥只管体感（也可顺带喂 Cemu 的震动回路）。"""
        if motion is not None:
            t, ax, ay, az, g0, g1, g2 = motion
            acc = (-ax / ACCEL_PER_G, az / ACCEL_PER_G, ay / ACCEL_PER_G)
            raw = (g0, g2, g1)                     # pitch / yaw / roll
            gyro = tuple((-v if self.invert[i] else v) * GYRO_DPS_PER_LSB
                         for i, v in enumerate(raw))
            ts = int(t * 1_000_000) & 0xFFFFFFFFFFFFFFFF
        else:
            acc = (0.0, 0.0, 0.0)
            gyro = (0.0, 0.0, 0.0)
            ts = int(time.monotonic() * 1_000_000)
        payload = (self._ident(0) + b"\x01"                      # ident + connected
                   + struct.pack("<IBBBBBBBB", pkt_num & 0xFFFFFFFF,
                                 0, 0, 0, 0,                     # 键位两个 bitmask/home/touch
                                 128, 128, 128, 128)             # 双摇杆中立位
                   + bytes(12)                                    # 12 个模拟按键
                   + bytes(12)                                    # 两指触摸（无触摸）
                   + struct.pack("<Q6f", ts, *acc, *gyro))
        return _packet(T_DATA, payload, self.server_id)

    def _apply_rumble(self, force=False):
        l, r = self._rumble[0] / 255.0, self._rumble[1] / 255.0
        cur = (round(l, 3), round(r, 3))
        if not force and cur == self._last_rumble_sent:
            return
        self._last_rumble_sent = cur
        try:
            self.engine.set_rumble(l, r, source="dsu")
        except Exception as e:
            self.stats["last_error"] = f"{type(e).__name__}: {e}"

    # ---------- 运维 ----------
    def set_invert(self, pitch=None, yaw=None, roll=None):
        if pitch is not None:
            self.invert[0] = bool(pitch)
        if yaw is not None:
            self.invert[1] = bool(yaw)
        if roll is not None:
            self.invert[2] = bool(roll)

    def status(self):
        with self._lock:
            motion = self._motion
        if motion is not None:
            pkt = self._data_packet(motion)
            ts, ax, ay, az, p, y, r = struct.unpack_from("<Q6f", pkt, 68)
            preview = {"accel": [round(v, 3) for v in (ax, ay, az)],
                       "gyro": [round(v, 2) for v in (p, y, r)]}
        else:
            preview = None
        return {"enabled": self.enabled, "port": self.port,
                "invert": list(self.invert), "preview": preview,
                "has_imu": motion is not None, "stats": dict(self.stats)}
