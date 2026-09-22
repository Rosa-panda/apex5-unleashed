# 引擎层：锁存账本状态机 + HID worker(ADR-012) + panic + 启动卫生(ADR-010) + 代理权检测(ADR-006)
import math
import threading
import time
from collections import deque

import protocol
import screenota
import transport

ACK_TIMEOUT = 0.3
ACK_RETRY = 2
EXTERNAL_COOLDOWN = 60.0
PROXY_RELEASE_TIMEOUT = 15.0   # 总线无外部命令持续此时长 → 判定对方停手，自动接管回来
REPLY_GRACE = 5.0              # 孤儿 ACK 宽限窗：命令号 5s 内本方（含第二句柄）刚发过 → 算自己的回复

PROXY_NAMES = {
    "SpaceStationService.exe": "飞智空间站",
    "steam.exe": "Steam",
    "DSX.exe": "DualSenseX",
}

# 飞智空间站服务 init 指纹（2026-09-20 真机抓取，ADR-023）：设备接入瞬间服务
# 一轮突发——握手/读设置块/读灯表/SyncWithGrip/开体感流，随后自己停手。
# 命中指纹 = 熟客例行公事：代理权照旧置 external（15s 收回+账本重放不变，
# cmd82 是真写入必须重放夺回），仅横幅柔化为中性提示，不再弹「被接管」吓人。
SS_INIT_MARKERS = {2, 4, 7, 16, 17, 82, 161, 162, 163, 167}
SS_INIT_WINDOW = 10.0     # 指纹统计窗口（秒）
SS_INIT_MIN = 3           # 窗口内命中 ≥3 种标记 cmd 即判 init

# 0xEF 帧 32 键物理位图（官方 OperatorDataParser 同源，映射前状态，ADR-019）：
# body[11..14] = keyId 0-31 的实时按压；拓展键 id18-23 与固件映射无关，天然区别于老按键
EXTKEY_BITNAMES = {18: "m1", 19: "m2", 20: "m3", 21: "m4", 22: "lm", 23: "rm"}


def now():
    return time.strftime("%H:%M:%S")


class Engine:
    def __init__(self, force_mock=False):
        self.force_mock = force_mock
        self.dev = None
        self.dev_kind = None            # "real" / "mock" / None
        self.online = False

        # 锁存账本（UI 看的就是这份，先记账再发送）
        self.state = {
            "triggers": {"left": None, "right": None},   # {mode,params,source,applied_at}
            "rumble": {"l": 0, "r": 0, "updated_at": None},
            "gripBind": {"left": None, "right": None},
        }
        self.proxy = {"holder": "self", "detail": "", "since": None}
        self._ext_cmds = {}                   # 外部命令计数 {cmd: n}（诊断：谁在轮询）
        self._ext_frames = {}                 # 外部命令最近一帧原文 {cmd: hex}（归因实锤用）
        self._ext_window = deque()            # 外部命令滑动窗口 [(t, cmd)]（init 指纹统计）
        self._orphan_replies = {}             # 本方孤儿回复计数 {cmd: n}（多包/迟到/第二句柄）
        self._last_tx = {}                    # {cmd: 本方最近一次发送时刻}（孤儿回复宽限判定）
        self.events = deque(maxlen=500)                    # 事件日志（含外部命令）

        self._wq = deque()                                  # (frame, meta)
        self._wq_lock = threading.Lock()
        self._pending = {}                                  # cmd -> deque[[deadline, retries, meta]]（FIFO：同 cmd 连发不互相覆盖）
        self._bus_lock = threading.Lock()
        self._bus = []                                      # 订阅者回调
        self._stop = threading.Event()
        self._last_external = 0.0
        self._bg_process_hint = None
        self._last_raw = {}
        self._rumble_timer = None
        self._worker = None
        self.last_screen_event = {"stage": "idle"}
        self._status_rx = None               # cmd3 设置块捕获（None=不在读取态）
        self._led_rx = None                  # 0xA7 多包接收缓冲（None=不在接收态）
        self._led_rx_done = False
        self._led_bean = None                # 最近一次读回的灯表（dict）
        self._led_blob_raw = b""             # 最近一次读回的原始 blob（备份用）
        self._extkey_bits = 0                # 0xEF 键位图上一次状态（变化才发事件）
        self.battery = None                  # {"level":0..5,"charging":bool}（cmd1 心跳回复 body[11]）
        self.versions = None                 # cmd1 七模块固件版本（body[15..29)，ADR-027）
        self.owner = None                    # cmd16 占用方读数（ADR-027 仲裁升级）
        self.motion_subs = []                # 0xEF 运动数据订阅（体感/摇杆映射，高频不走事件日志）
        self.raw_motion = False              # 0xEF 位图流实际状态（RAM 态，休眠/重启作废）
        self._raw_wanted = False             # 流需求位（service 需求登记表决策，attach 按此恢复）
        self._motion_count = 0
        self._rx_cmd = None                  # request() 阻塞问答的捕获槽
        self._rx_buf = []

    # ---------- 事件总线 / 状态推送 ----------
    def subscribe(self, cb):
        with self._bus_lock:
            self._bus.append(cb)

    def _emit(self, kind, **kw):
        evt = {"ts": now(), "kind": kind, **kw}
        self.events.append(evt)
        with self._bus_lock:
            subs = list(self._bus)
        for cb in subs:
            try:
                cb(evt)
            except Exception:
                pass

    def snapshot(self):
        return {"device": {"kind": self.dev_kind, "online": self.online,
                           "battery": self.battery, "versions": self.versions},
                "state": self.state, "proxy": self.proxy,
                "owner": self.owner,
                "ext_cmds": dict(self._ext_cmds),
                "ext_frames": dict(self._ext_frames),
                "orphan_replies": dict(self._orphan_replies),
                "events": list(self.events)[-80:]}

    # ---------- 0xEF 运动数据订阅（ADR-027：体感瞄准/摇杆映射/诊断采样的信号源） ----------
    def subscribe_motion(self, cb):
        self.motion_subs.append(cb)

    def set_raw_motion(self, on, source="ui"):
        """cmd17 raw 位开关（语义实锤：openflydigi gyro-probe enable_raw(raw=1/0)，
        0xFF=不动）。用户实测：流常开时固件把上报当活动，手柄永不断电休眠——
        关掉即恢复自动休眠。代价：迷宫/体感桥/陀螺瞄准没数据，拓展键监测与
        宏录制同流也停。RAM 态：手柄休眠/重启后本开关态作废，attach 按
        _raw_wanted 恢复（ADR-028 修订 2：按需开流，默认关）。"""
        import extkeys
        self._send(extkeys.build(17, bytes([255, 1 if on else 0, 255, 255, 255])),
                   source=source)
        self.raw_motion = bool(on)
        self._raw_wanted = bool(on)
        self._emit("raw_motion", enabled=bool(on))
        return {"ok": True, "enabled": bool(on)}

    def _dispatch_motion(self, body):
        """0xEF 帧运动段（ADR-027 D2：body 索引 = openflydigi raw-1）：
        摇杆 LX/LY/RX/RY @3/5/7/9、陀螺 @17/19/21、加速度 @23/25/27，i16 LE。"""
        import struct as _s
        if len(body) < 29:
            return
        lx, ly, rx, ry = _s.unpack_from("<4h", body, 3)
        gx, gy, gz = _s.unpack_from("<3h", body, 17)
        ax, ay, az = _s.unpack_from("<3h", body, 23)
        self._motion_count += 1
        m = {"t": time.monotonic(), "lx": lx, "ly": ly, "rx": rx, "ry": ry,
             "gyro": [gx, gy, gz], "accel": [ax, ay, az]}
        for cb in list(self.motion_subs):
            try:
                cb(m)
            except Exception:
                pass

    # ---------- 阻塞问答（体验区配置读：cmd3/cmd16/cmd2 等，ADR-027） ----------
    def request(self, frame, cmd_id, timeout=1.0, source="req"):
        """发一帧并等同命令号回复（body 列表）。超时返回已收到的（可能为空）。"""
        self._rx_cmd = cmd_id
        self._rx_buf = []
        try:
            self._send(frame, source)
            t0 = time.monotonic()
            while not self._rx_buf and time.monotonic() - t0 < timeout:
                time.sleep(0.02)
            return list(self._rx_buf)
        finally:
            self._rx_cmd = None

    def send_checked(self, frame, cmd_id, source="req", timeout=1.0):
        """发一帧并等 ACK；无回复/超时抛错（体验区写操作统一走这里，防静默失败）。"""
        bodies = self.request(frame, cmd_id, timeout=timeout, source=source)
        if not any(b[2] == cmd_id for b in bodies):
            raise RuntimeError(f"cmd{cmd_id} 无 ACK（手柄可能休眠或被占用）")
        return bodies

    def read_owner(self):
        """cmd16：占用方五开关 + control_by 标签（ADR-027 #5）。存快照。"""
        import extkeys
        bodies = self.request(extkeys.build(16), 16, timeout=1.0, source="owner")
        for body in bodies:
            if body[2] == 16:
                import devcfg
                self.owner = devcfg.parse_owner(body)
                self._emit("owner", **{"owner": self.owner})
                return self.owner
        return None

    def acquire_control(self, tag=b"Apex5Unleashed"):
        """cmd28 申请仲裁（ADR-027 #5）：[23, 1, 20B 标签]。ACK 不改固件态语义待真机验。"""
        import protocol as _p
        tag = (tag or b"Apex5Unleashed")[:20].ljust(20, b"\x00")
        self.send_checked(_p.build_crc(28, bytes([23, 1]) + tag), 28, source="acquire")
        self.read_owner()
        return {"ok": True, "owner": self.owner}

    # ---------- 设备生命周期 ----------
    def attach(self, dev):
        self.dev = dev
        self.dev_kind = dev.kind
        self.online = True
        # 新枚举的设备上不存在「上一个接管者还活着」——代理权复位（mock 路径没有
        # panic 兜底，real 路径 panic 也会再复位一次，双保险）
        self.proxy = {"holder": "self", "detail": "", "since": now()}
        self._pending.clear()
        self._worker = threading.Thread(target=self._worker_loop, daemon=True, name="hid-worker")
        self._worker.start()
        self._emit("device", online=True, dev_kind=dev.kind, detail="已连接")
        if dev.kind == "real":
            self.panic(source="hygiene")          # ADR-010 启动卫生检查
            # 0xEF 位图流按需恢复（开关 RAM 态，休眠/重启会丢）。需求位由 service
            # 需求登记表决策（拓展键监听心跳/宏录制/体感总闸/手动），无人消费不开——
            # 流常开会让固件把上报当活动，手柄永不休眠（2026-09-22 用户实锤）。
            if self._raw_wanted:
                import extkeys
                self._send(extkeys.build(17, bytes([255, 1, 255, 255, 255])), source="attach")
                self.raw_motion = True
        self.refresh_battery()                    # 心跳一发，电量随回复异步进账（_capture_battery）
        if dev.kind == "real":
            threading.Thread(target=self._post_attach, daemon=True, name="post-attach").start()

    def _post_attach(self):
        """接入后 1s：读一次占用方标签（ADR-027 #5——谁在管手柄，UI 有据可查）。"""
        time.sleep(1.0)
        if self.online:
            try:
                self.read_owner()
            except Exception:
                pass

    def detach(self, reason=""):
        if self._rumble_timer:
            self._rumble_timer.cancel()
        was = self.dev_kind
        self.dev = None
        self.dev_kind = None
        self.online = False
        # 设备离线 → 总线上不存在外部接管者，代理权必须复位（否则横幅永久卡「被接管」，
        # 且 maybe_release_proxy 只在在线时跑，离线期间永远没机会自动恢复）
        if self.proxy["holder"] != "self":
            self.proxy = {"holder": "self", "detail": "", "since": now()}
            self._emit("proxy", holder="self", detail="设备离线，代理权复位")
        if was:
            self._emit("device", online=False, dev_kind=was, detail=reason or "已断开")
        self.state["triggers"] = {"left": None, "right": None}
        self.state["gripBind"] = {"left": None, "right": None}
        self.state["rumble"] = {"l": 0, "r": 0, "updated_at": None}
        self._notify_state()

    def _notify_state(self):
        self._emit("state", **{"state": self.state, "proxy": self.proxy})

    # ---------- 电量（cmd1 心跳回复，openflydigi 同源布局） ----------
    def refresh_battery(self, source="battery"):
        """发一发 cmd1 心跳；回复异步走 _classify 抓取。离线静默跳过。"""
        if not self.online:
            return
        try:
            import extkeys
            self._send(extkeys.build(protocol.CMD_INFO), source=source)
        except Exception:
            pass

    def _capture_battery(self, body):
        """body[11]：低半字节=电量 0..5，高半字节 1=充电中。真机实证（2026-09-19，
        满电读数 0x05）。变化才发事件，快照/WS 均可见。"""
        if len(body) <= 11:
            return
        b = body[11]
        new = {"level": min(b & 0xF, 5), "charging": (b >> 4) == 1}
        old = self.battery
        self.battery = {**new, "updated_at": now()}
        if old is None or old["level"] != new["level"] or old["charging"] != new["charging"]:
            self._emit("battery", **new)

    def _capture_versions(self, body):
        """cmd1 心跳回复 body[15..29)：七模块固件版本 2B BCD（openflydigi motion.py
        VERSION_OFFSET 布局，ADR-027）。随心跳刷新，P4 探针的问题就地消解。"""
        import devcfg
        v = devcfg.parse_versions(body)
        if v and v != self.versions:
            self.versions = v
            self._emit("versions", **{"versions": v})

    # ---------- HID worker：唯一读写线程（ADR-012） ----------
    def _worker_loop(self):
        while not self._stop.is_set() and self.dev:
            frame = None
            with self._wq_lock:
                if self._wq:
                    frame, meta = self._wq.popleft()
            try:
                if frame is not None:
                    self.dev.write(frame)
                    cmd = frame[3]
                    self._note_tx(cmd)
                    self._pending.setdefault(cmd, deque()).append(
                        [time.monotonic() + ACK_TIMEOUT, ACK_RETRY, meta])
                data = self.dev.read(10)     # 读 10ms 超时，永不长期阻塞
                if data:
                    self._classify(data)
            except Exception as e:            # HID 异常 → 断开重连（TECH-SPEC §9）
                self._emit("error", detail=f"HID: {e}")
                try:
                    self.dev.close()
                except Exception:
                    pass
                self.detach("HID 异常")
                return
            # ACK 超时检查（超时只记录失败，不盲目重发——重发错误状态更危险）
            t = time.monotonic()
            for cmd, q in list(self._pending.items()):
                for rec in list(q):
                    if t > rec[0]:
                        q.remove(rec)
                        self._emit("command", source=rec[2].get("source", "?"),
                                   hex=rec[2].get("hex", ""), result="timeout")
                if not q:
                    self._pending.pop(cmd, None)

    def _classify(self, data):
        body = bytes(data[1:]) if data and data[0] == protocol.REPORT_ID_IN else bytes(data or [])
        if len(body) < 4 or body[:2] != b"\x5a\xa5":
            self._raw_frame(bytes(data or b""))    # 非协议帧：特殊键候选 → 原始事件
            return
        cmd = body[2]
        if cmd == 0xEF:
            # 设备→主机数据流（~370Hz，PROTOCOL.md）：不是控制命令，不算外部代理证据。
            # 附带解码 32 键物理位图（拓展键唯一实时信号源，官方按键区分同款通道）
            if len(body) >= 15:
                cur = body[11] | (body[12] << 8) | (body[13] << 16) | (body[14] << 24)
                if cur != self._extkey_bits:
                    self._extkey_bits = cur
                    keys = [n for i, n in EXTKEY_BITNAMES.items() if cur >> i & 1]
                    names = [protocol.KEY32_NAMES.get(i, f"k{i}") for i in range(32) if cur >> i & 1]
                    self._emit("extkey", keys=keys, names=names, bits=f"{cur:08x}")
            if self.motion_subs:
                self._dispatch_motion(body)
            return
        if self._rx_cmd == cmd:
            self._rx_buf.append(body)          # request() 问答捕获（不拦 ACK 走账）
        if cmd == protocol.CMD_INFO and len(body) > 11 and body[5] == 0x80:
            # 心跳回复（设备类型 0x80 守门，防误吃其他 cmd1 帧）：抓电量后照常走 ACK 逻辑
            self._capture_battery(body)
            self._capture_versions(body)
        if cmd == protocol.CMD_LED_READ and self._led_rx is not None:
            # 0xA7 多包 ACK（ADR-018）：[3]=总包数 [4]=包序号 [6..26]=数据段；末包 data[3]==data[4]+1
            self._led_rx.append(body)
            q = self._pending.get(cmd)
            if q:
                q.popleft()
                if not q:
                    self._pending.pop(cmd, None)
            if len(body) > 4 and body[3] == body[4] + 1:
                self._led_rx_done = True
            return
        if cmd == protocol.CMD_STATUS and self._status_rx is not None:
            # cmd3 设置块回复（单帧）：捕获 body 后照常走 ACK 逻辑
            self._status_rx.append(body)
        q = self._pending.get(cmd)
        rec = q.popleft() if q else None
        if q is not None and not q:
            self._pending.pop(cmd, None)
        if rec is not None:
            self._emit("command", source=rec[2].get("source", "?"),
                       hex=rec[2].get("hex", ""),
                       result="ack" if protocol.ack_ok(body, cmd) else "nack")
        else:
            # 孤儿 ACK：多包读的第 2..N 包、超时后的迟到 ACK、第二句柄（Pad 独占会话，
            # Windows 多句柄复制输入）的回复都落这里——宏的 42 包读把这些噪声放大了
            # 几十倍，曾全被当成「外部接管铁证」（ext_cmds 163:252 = 6 次读 × 42 包）。
            # 宽限窗内本方任意句柄刚发过同命令号 → 只记诊断计数；从没发过的命令号
            # 才算别的进程在写手柄（铁证，ADR-006）。
            tx = self._last_tx.get(cmd, 0.0)
            try:
                import extkeys
                tx = max(tx, extkeys.last_tx(cmd))
            except Exception:
                pass
            if tx and time.monotonic() - tx <= REPLY_GRACE:
                self._orphan_replies[cmd] = self._orphan_replies.get(cmd, 0) + 1
            else:
                self._external_hit(cmd, body)

    def _raw_frame(self, frame):
        """vendor 接口上的非协议输入帧（去抖：同内容 200ms 内只报一次）。"""
        key = frame.hex()
        t = time.monotonic()
        if t - self._last_raw.get(key, 0.0) < 0.2:
            self._last_raw[key] = t
            return
        self._last_raw[key] = t
        if len(self._last_raw) > 64:
            self._last_raw.clear()
        self._emit("rawhid", hex=key)

    def _external_hit(self, cmd, body=b""):
        # 时间戳无条件刷新（空闲恢复判定依赖它）；冷却只抑制事件刷屏
        self._ext_cmds[cmd] = self._ext_cmds.get(cmd, 0) + 1
        if body:
            self._ext_frames[cmd] = body.hex(" ")   # 帧原文：归因到具体进程/固件行为的实锤
        try:    # 罕见事件必须落盘：内存事件列表重启即失，归因线索不能只活在会话里
            import json as _json, os as _os
            _d = _os.path.join(_os.environ.get("APPDATA") or _os.path.expanduser("~"),
                               "Apex5Unleashed")
            _os.makedirs(_d, exist_ok=True)
            with open(_os.path.join(_d, "proxy_hits.log"), "a", encoding="utf-8") as _f:
                _f.write(_json.dumps({"ts": now(), "cmd": cmd,
                                      "hex": self._ext_frames.get(cmd, ""),
                                      "detail": self.proxy.get("detail")},
                                     ensure_ascii=False) + "\n")
        except Exception:
            pass
        t = time.monotonic()
        self._ext_window.append((t, cmd))
        while self._ext_window and t - self._ext_window[0][0] > SS_INIT_WINDOW:
            self._ext_window.popleft()
        recent = {c for _, c in self._ext_window}
        mild = len(recent & SS_INIT_MARKERS) >= SS_INIT_MIN   # ADR-023
        self._last_external = t
        active = t - self._last_external < EXTERNAL_COOLDOWN
        if active and self.proxy["holder"] == "external":
            # 已在外部状态：指纹结论变了只刷新状态，不重复发事件（防刷屏）
            if mild != self.proxy.get("mild", False):
                self.proxy = {**self.proxy, "mild": mild}
                self._notify_state()
            return
        if mild:
            detail = "飞智空间站（服务初始化）"
            msg = "飞智空间站服务初始化手柄，稍后自动收回"
        else:
            detail = self.proxy.get("detail") or "未知进程"
            msg = f"总线上出现外部命令 cmd={cmd}"
        self.proxy = {"holder": "external", "detail": detail,
                      "since": now(), "mild": mild}
        self._emit("proxy", holder="external", cmd=cmd,
                   hex=self._ext_frames.get(cmd, ""), mild=mild, detail=msg)
        self._notify_state()

    # ---------- 对外 API ----------
    def _send(self, cmd_frame, source):
        meta = {"source": source, "hex": cmd_frame[:12].hex(" ")}
        with self._wq_lock:
            self._wq.append((cmd_frame, meta))
        self._emit("command", source=source, hex=meta["hex"], result="sent")

    def _note_tx(self, cmd):
        """本方发送登记（孤儿 ACK 宽限窗的数据源）。三条写路径都必须走这里：
        worker 队列 / _stream 流式直写 / 第二句柄 extkeys._TX_SEEN——漏任何一条，
        那条路的固件 ACK 就会被误判成「外部接管铁证」（震动测试曾中招）。"""
        self._last_tx[cmd] = time.monotonic()

    def _stream(self, cmd_frame):
        """流式直写（cmd18 高频），与队列共用写锁防帧交错。"""
        with self._wq_lock:
            if self.dev and self.online:
                try:
                    self.dev.write(cmd_frame)
                    self._note_tx(cmd_frame[3])
                except Exception:
                    pass

    def set_trigger(self, side, mode, params, preview=False, source="ui"):
        if side not in ("left", "right"):
            raise ValueError("side")
        payload = protocol.trigger_payload(apply=not preview, side=protocol.SIDE[side],
                                           mode=mode, params=params or {})
        if payload is None:
            raise ValueError("mode/params")
        self._send(protocol.build(protocol.CMD_TRIGGER, payload), source)
        if not preview:
            self.state["triggers"][side] = {"mode": mode, "params": params or {},
                                            "source": source, "applied_at": now()}
            self._notify_state()

    def clear_trigger(self, side, source="ui"):
        self.set_trigger(side, "normal", {}, preview=False, source=source)

    def set_rumble(self, l, r, duration=None, source="ui"):
        l, r = protocol.clamp(l, 0, 255), protocol.clamp(r, 0, 255)
        self._send(protocol.build(protocol.CMD_RUMBLE, bytes([l, r])), source)
        self.state["rumble"] = {"l": l, "r": r, "updated_at": now()}
        if self._rumble_timer:
            self._rumble_timer.cancel()
        if duration:                        # 自动归零（TECH-SPEC §3）
            self._rumble_timer = threading.Timer(duration, lambda: self.set_rumble(0, 0, source=source + ":auto0"))
            self._rumble_timer.daemon = True
            self._rumble_timer.start()
        self._notify_state()

    def bind_grip(self, side, params, source="ui"):
        payload = protocol.grip_payload(protocol.SIDE[side], params or {})
        self._send(protocol.build(protocol.CMD_GRIP, payload), source)
        self.state["gripBind"][side] = {**(params or {}), "source": source, "applied_at": now()}
        self._notify_state()

    def unbind_grip(self, side, source="ui"):
        self.set_trigger(side, "normal", {}, source=source + ":unbind")
        self.state["gripBind"][side] = None
        self._notify_state()

    # ---------- 灯光（ADR-018：写表驻留，同扳机一样锁存） ----------
    def led_test(self, r, g, b, source="ui"):
        """0xF5 测试灯：直点色，最安全的探针。"""
        self._send(protocol.led_test_frame(r, g, b), source)

    def led_read_config(self, source="ui", timeout=3.0):
        """0xA7 读灯表（多包 ACK），阻塞至收齐或超时。返回 bean dict 或 None。原始 blob 存 _led_blob_raw。"""
        if not self.online:
            return None
        self._led_rx = []
        self._led_rx_done = False
        try:
            self._send(protocol.led_read_frame(0), source)
            t0 = time.monotonic()
            while not self._led_rx_done and time.monotonic() - t0 < timeout:
                time.sleep(0.02)
            if not self._led_rx:
                return None
            self._led_blob_raw = b"".join(
                bytes(p[6:26]) for p in sorted(self._led_rx, key=lambda p: p[4] if len(p) > 4 else 0))
            self._led_bean = protocol.parse_led_bean(self._led_blob_raw)
            return self._led_bean
        finally:
            self._led_rx = None
            self._led_rx_done = False

    def led_backup(self, path=None):
        """当前灯表原始 blob 存盘（恢复出厂灯效的保险，ADR-018 R1）。"""
        import os
        if not self._led_blob_raw:
            self.led_read_config()
        if not self._led_blob_raw:
            raise RuntimeError("读不到灯表")
        path = path or os.path.join(
            os.environ.get("APPDATA", os.path.expanduser("~")), "Apex5Unleashed", "led_backup.bin")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(self._led_blob_raw)
        return path

    def led_restore(self, path=None):
        """把备份的灯表原样写回。"""
        import os
        path = path or os.path.join(
            os.environ.get("APPDATA", os.path.expanduser("~")), "Apex5Unleashed", "led_backup.bin")
        if not os.path.isfile(path):
            raise FileNotFoundError("没有灯表备份")
        with open(path, "rb") as f:
            blob = f.read()
        bean = protocol.parse_led_bean(blob)
        if not bean:
            raise ValueError("备份文件损坏")
        self.led_write(bean, blob[20:], source="restore")

    def led_write(self, bean, frames_b, source="ui", timeout=5.0, verify=True):
        """组装 blob → 0xA8 start + N×0xA9 写入。写后读回自校验（实测有丢包），不符自动重试一次。"""
        if not self.online:
            raise RuntimeError("设备不在线")
        blob = protocol.led_bean_header(bean, frames_b)

        def _send_all():
            packs = [blob[i:i + protocol.LED_PACK_SIZE]
                     for i in range(0, len(blob), protocol.LED_PACK_SIZE)]
            self._send(protocol.led_write_start_frame(0, len(packs)), source)
            for i, p in enumerate(packs):
                self._send(protocol.led_write_pack_frame(i, p), source)
            t0 = time.monotonic()
            while (protocol.CMD_LED_WRITE_START in self._pending or
                   protocol.CMD_LED_WRITE_PACK in self._pending):
                if time.monotonic() - t0 > timeout:
                    break                       # 超时交给读回校验兜底
                time.sleep(0.02)

        _send_all()
        if verify:
            for _ in range(2):                  # 首发丢过包，最多重试一次
                time.sleep(0.3)                 # 固件落表有延迟，立即读回会读到旧值（实测 0.3s 后 0 差异）
                self.led_read_config(source=source + ":verify")
                # 只比对重叠区：固件槽位可能比写入长（尾部残留旧帧）或短（帧数截断）
                n = min(len(blob), len(self._led_blob_raw))
                if n > 0 and self._led_blob_raw[:n] == blob[:n]:
                    return
                _send_all()
            raise TimeoutError("灯光写入校验不符（已重试）")

    def led_apply_effect(self, mode, colors, brightness=None, period=None, source="ui"):
        """效果展开 → 写灯表。基于真机读回的 bean 参数（版本/灯珠数/保留区），不硬编码。"""
        bean = self._led_bean or self.led_read_config(source=source)
        if not bean:
            raise RuntimeError("读不到灯表（设备不支持或未连接）")
        rgb_num = bean.get("rgb_num") or 10
        if isinstance(colors, tuple):
            colors = [colors]
        colors = [tuple(max(0, min(255, int(c))) for c in rgb) for rgb in colors] or [(255, 255, 255)]
        frames = {"on": lambda: protocol.led_frames_solid(colors[0], rgb_num),
                  "off": lambda: protocol.led_frames_solid((0, 0, 0), rgb_num),
                  "breath": lambda: protocol.led_frames_breath(colors[0], rgb_num),
                  "gradient": lambda: protocol.led_frames_gradient(colors, rgb_num),
                  "flow": lambda: protocol.led_frames_flow(colors, rgb_num),
                  "blink": lambda: protocol.led_frames_blink(colors[0], rgb_num),
                  "heartbeat": lambda: protocol.led_frames_heartbeat(colors[0], rgb_num),
                  "wipe": lambda: protocol.led_frames_wipe(colors, rgb_num),
                  "comet": lambda: protocol.led_frames_comet(colors, rgb_num),
                  "duosweep": lambda: protocol.led_frames_duosweep(colors, rgb_num),
                  "rain": lambda: protocol.led_frames_rain(colors, rgb_num),
                  "chase": lambda: protocol.led_frames_chase(colors, rgb_num),
                  "pulse": lambda: protocol.led_frames_pulse(colors, rgb_num),
                  "fire": lambda: protocol.led_frames_fire(colors, rgb_num),
                  "auroraflow": lambda: protocol.led_frames_auroraflow(colors, rgb_num),
                  "typewriter": lambda: protocol.led_frames_typewriter(colors, rgb_num),
                  "rainbow": lambda: protocol.led_frames_rainbow(rgb_num),
                  "aurora": lambda: protocol.led_frames_aurora(colors, rgb_num),
                  "default": lambda: protocol.led_frames_solid(colors[0], rgb_num)}.get(mode)
        if frames is None:
            raise ValueError("mode")
        frames_b = frames()
        n_frames = len(frames_b) // (rgb_num * 3)
        bean = dict(bean)
        bean["led_mode"] = 0 if mode == "off" else 1
        if brightness is not None:
            bean["brightness"] = max(0, min(255, int(brightness)))
        bean["loop_start"], bean["loop_end"] = 0, max(0, n_frames - 1)
        if period is not None:
            bean["loop_time"] = max(1, min(255, int(period)))
        self.led_write(bean, frames_b, source=source)
        self._emit("led", effect=mode, frames=n_frames, brightness=bean["brightness"])

    # ---------- 屏幕上传（ADR-018 R4 二期：串口 OTA，离线自检已过，真机待用户确认） ----------
    def screen_flash(self, frames, interval_ms=100, restore_default=False, source="ui"):
        """屏幕图片写入（串口 OTA 路径，ADR-018）。设备随后自重启，HID 短暂掉线。

        红线：调用前必须离线自检全绿 + 用户明确确认（ADR-018 R4）。
        在后台线程跑，进度经 _emit("screen", ...) 推给 UI。
        """
        # 升级模式下 HID 可能不可见（online=False），但串口在 = 设备在
        if not self.online and not screenota.find_port():
            raise RuntimeError("设备未连接（HID 与升级串口均未找到）")

        def run():
            try:
                def progress(done, total, stage):
                    self.last_screen_event = {"stage": "flash", "op": stage, "done": done, "total": total}
                    self._emit("screen", **self.last_screen_event)

                # 芯片若已挂在升级模式（上次尝试中断），直接复用串口，跳过 cmd 0x1F
                port = screenota.find_port()
                if port:
                    self.last_screen_event = {"stage": "reuse", "port": port}
                    self._emit("screen", **self.last_screen_event)
                base = screenota.upload_picture(
                    lambda cmd, payload: self._send(protocol.build_crc(cmd, payload), source),
                    frames, interval_ms=interval_ms,
                    restore_default=restore_default, progress=progress, port=port,
                    on_stage=lambda stage: self._emit("screen", stage=stage))
                self.last_screen_event = {"stage": "done", "base": hex(base)}
                self._emit("screen", **self.last_screen_event)
            except Exception as exc:                     # noqa: BLE001 —— 错误必须进事件流
                self.last_screen_event = {"stage": "error", "error": f"{type(exc).__name__}: {exc}"}
                self._emit("screen", **self.last_screen_event)

        threading.Thread(target=run, daemon=True, name="screen-flash").start()

    # ---------- 屏显开关（ADR-018 附带：cmd 19/8 状态栏、19/9 动画常亮） ----------
    def screen_get_flags(self):
        """cmd3 设置块 → 屏显两开关。bit 布局见 openflydigi settings.py：
        sub9 动画常亮（SDK 叫 OffScreen，实测语义反转）：usable=body[7]&1, enabled=body[8]&1
        sub8 状态栏常亮：usable=body[5]&0x80, enabled=body[6]&0x80"""
        self._status_rx = []
        try:
            self._send(protocol.build(protocol.CMD_STATUS), source="screen")
            t0 = time.monotonic()
            while not self._status_rx and time.monotonic() - t0 < 1.0:
                time.sleep(0.02)
            if not self._status_rx:
                raise RuntimeError("cmd3 无回复（手柄可能休眠）")
            body = self._status_rx[-1]
            if len(body) < 9:
                raise RuntimeError("cmd3 回复过短")
            return {"animation_on": bool(body[8] & 1), "status_bar": bool(body[6] & 0x80)}
        finally:
            self._status_rx = None

    def screen_set_flag(self, sub_id: int, on: bool, source="ui"):
        """写单个子设置位。注意 ACK 不证明【这个】设置生效（官方已知怪癖），
        调用方可跟一次 screen_get_flags 复核。"""
        self._send(protocol.build(protocol.CMD_SETTING, bytes([sub_id, 1 if on else 0])), source=source)

    def panic(self, source="panic"):
        """终极复位：马达归零 + 双侧 Normal + 账本清零。"""
        self.set_rumble(0, 0, source=source)
        for side in ("left", "right"):
            payload = protocol.trigger_payload(True, protocol.SIDE[side], "normal", {})
            self._send(protocol.build(protocol.CMD_TRIGGER, payload), source)
        self.state["triggers"] = {"left": None, "right": None}
        self.state["gripBind"] = {"left": None, "right": None}
        if self.proxy["holder"] != "self":
            self.proxy = {"holder": "self", "detail": "", "since": now()}
        self._emit("panic", source=source)
        self._notify_state()

    # ---------- 测试台 ----------
    def test_pulse(self, side=None):
        self.set_rumble(220, 220, duration=0.15, source="test")

    def test_sine(self, seconds=3.0, freq=3.0, amp=220):
        for s in ("left", "right"):          # rumble→扳机路由后体感
            self.bind_grip(s, {"filter": 10, "scale": 60, "stroke": 50,
                               "press": 50, "strength": 50, "freq": 20}, source="test")
        threading.Thread(target=self._sine_stream, args=(seconds, freq, amp), daemon=True).start()

    def _sine_stream(self, seconds, freq, amp):
        rate = 100.0
        n = int(seconds * rate)
        t0 = time.perf_counter()
        for i in range(n):
            v = int(amp * (0.5 + 0.5 * math.sin(2 * math.pi * freq * i / rate)))
            self._stream(protocol.build(protocol.CMD_RUMBLE, bytes([v, v // 2])))
            nxt = t0 + (i + 1) / rate
            d = nxt - time.perf_counter()
            if d > 0:
                time.sleep(d)
        self._stream(protocol.build(protocol.CMD_RUMBLE, b"\x00\x00"))
        for s in ("left", "right"):
            self.unbind_grip(s, source="test")

    # ---------- 代理权-进程归因 + 自动接管回来（线程D调用） ----------
    def scan_proxy_processes(self):
        """进程扫描只做【归因命名】，不单独判定接管（进程在场≠在写总线）。
        接管唯一铁证 = _external_hit 的总线外部命令。"""
        import subprocess
        try:
            out = subprocess.run(
                ["tasklist", "/FO", "CSV", "/NH"],
                capture_output=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW
            ).stdout.decode("gbk", "ignore").lower()   # tasklist=GBK，PYTHONUTF8 下 text=True 必炸
        except Exception:
            return
        found = next((cn for en, cn in PROXY_NAMES.items() if en.lower() in out), None)

        if found:
            if self.proxy["holder"] == "external" and self.proxy["detail"] in ("", "未知进程"):
                # 已有总线铁证，进程扫描补上名字
                self.proxy["detail"] = found
                self._emit("proxy", holder="external", detail=f"归因到进程：{found}")
                self._notify_state()
            elif self.proxy["holder"] == "self" and self._bg_process_hint != found:
                # 仅仅是后台服务在跑：弱提示，不改代理权状态
                self._bg_process_hint = found
                self._emit("info", detail=f"检测到 {found} 在后台运行（未接管手柄）")

    def maybe_release_proxy(self):
        """外部命令空闲超时 → 对方已停手 → 自动接管回来并重放账本。"""
        if self.proxy["holder"] != "external":
            return
        if time.monotonic() - self._last_external < PROXY_RELEASE_TIMEOUT:
            return
        why = ("飞智空间站初始化结束，已自动接管回来" if self.proxy.get("mild")
               else f"外部已停止（{PROXY_RELEASE_TIMEOUT:.0f}s 无活动），自动接管回来")
        self._reclaim(why)

    def reclaim(self):
        """用户手动夺回。立即生效。"""
        self._reclaim("手动夺回控制权")

    def _reclaim(self, why):
        self.proxy = {"holder": "self", "detail": "", "since": now()}
        self._emit("proxy", holder="self", detail=why)
        self.reassert(source="reclaim")
        self._notify_state()

    def reassert(self, source="reassert"):
        """把账本效果原样重发——夺回的是实际控制权，不只是状态标签。"""
        if not self.online:
            return
        for side in ("left", "right"):
            t = self.state["triggers"].get(side)
            if t:
                self.set_trigger(side, t["mode"], t.get("params", {}), preview=False, source=source)
            else:
                self.clear_trigger(side, source=source)
        for side in ("left", "right"):
            g = self.state["gripBind"].get(side)
            if g:
                self.bind_grip(side, {k: g[k] for k in ("filter", "scale", "stroke", "press", "strength", "freq")
                                      if k in g}, source=source)
        r = self.state["rumble"]
        if r["l"] or r["r"]:
            self.set_rumble(r["l"], r["r"], source=source)

    def stop(self):
        self._stop.set()
