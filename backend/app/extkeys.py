# 拓展键映射（ADR-019）：cmd 161-166 配置区读写 + 测试模式
# 写通路真机已验证（2026-09-19）：42 包写→读回一致→应用→保存，即刻生效。
# 键 id↔物理键采信官方 device_config_k5.json：18=M1(背右上) 19=M2(背左上) 20=M3(背右下)
# 21=M4(背左下) 22=M5(头左=LM) 23=M6(头右=RM)。255=透传 32=宏 254=键盘。
import os
import struct
import threading
import time

EXT_KEYS = [("m1", 18), ("m2", 19), ("m3", 20), ("m4", 21), ("lm", 22), ("rm", 23)]
TARGET_NAMES = {0: "up", 1: "right", 2: "down", 3: "left", 4: "a", 5: "b", 6: "select",
                7: "x", 8: "y", 9: "start", 10: "lb", 11: "rb", 12: "lt", 13: "rt",
                14: "thl", 15: "thr", 16: "c", 17: "z", 24: "fn", 25: "turbo",
                27: "home", 255: "透传", 254: "键盘", 32: "宏"}
TEST_TARGETS = {"m1": 6, "m2": 9, "m3": 10, "m4": 11, "lm": 14, "rm": 15}  # 视图/菜单/LB/RB/L3/R3
PKG = 20
CMD_STATUS, CMD_APPLY, CMD_READ, CMD_WRITE_START, CMD_WRITE_PACK, CMD_SAVE = \
    161, 162, 163, 164, 165, 166


def _appdata():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "Apex5Unleashed")
    os.makedirs(d, exist_ok=True)
    return d


def backup_path():
    return os.path.join(_appdata(), "mapping_backup_slot0.bin")


def build(cmd, payload=b""):
    """校验和版 32B 帧：len=payload+2，CRC=sum(frame[3:3+len])。"""
    buf = bytearray(32)
    buf[0], buf[1], buf[2], buf[3] = 0x03, 0x5A, 0xA5, cmd
    buf[4] = len(payload) + 2
    buf[5:5 + len(payload)] = payload
    buf[3 + buf[4]] = sum(buf[3:3 + buf[4]]) & 0xFF
    return bytes(buf)


def enable_raw_stream(pad):
    """重开「私有原始数据」开关（cmd17，255=其余保持）——0xEF 位图流（拓展键检测/宏录制
    的唯一信号源）靠它。实测该开关会被手柄休眠/重启等冲回关闭（RAM 态，非配置项），
    所以连接时与配置写入后都补一刀。真机验证：关→开 0xEF 立即恢复 ~300Hz。"""
    return any(b[2] == 17 for b in pad.exchange(build(17, bytes([255, 1, 255, 255, 255]))))


# 本进程第二句柄（Pad 独占会话）的总线活动登记：Windows 多句柄复制输入，这里发出的
# 命令的 ACK 也会落进引擎读线程的 _pending 之外——引擎的孤儿 ACK 宽限窗靠它把
# 「自己人另一句柄的回复」和真·外部进程区分开（engine._classify，ADR-006 补丁）。
_TX_SEEN = {}


def last_tx(cmd: int) -> float:
    """cmd 最近一次由本进程第二句柄发送的时刻（monotonic；没发过返回 0.0）。"""
    return _TX_SEEN.get(cmd & 0xFF, 0.0)


class Pad:
    """vendor 接口独占会话（161-166 命令族）。与引擎读线程并存（Windows 多句柄复制输入）。"""

    def __init__(self):
        import hid
        for d in hid.enumerate(0x37D7, 0x2501):
            if d.get("usage_page") == 0xFFA0:
                self.dev = hid.device()
                self.dev.open_path(d["path"])
                self.dev.set_nonblocking(False)
                break
        else:
            raise RuntimeError("vendor 接口未找到")

    def exchange(self, frame, wait=0.8):
        """发送并收集 wait 秒内的命令应答（已剥 report id，跳过体感流）。"""
        self.dev.write(frame)
        _TX_SEEN[frame[3] & 0xFF] = time.monotonic()   # 引擎孤儿 ACK 宽限窗要查（见模块头注释）
        end = time.time() + wait
        out = []
        while time.time() < end:
            r = bytes(self.dev.read(64, timeout_ms=30))
            if len(r) > 7 and r[0] == 0x04 and r[1] == 0x5A and r[2] == 0xA5:
                if r[3] == 0xEF:
                    continue
                out.append(r[1:])
                end = max(end, time.time() + 0.15)
        return out

    def read_status(self):
        for body in self.exchange(build(CMD_STATUS)):
            if body[2] == CMD_STATUS:
                raw = body[5]
                active = raw - 4 if 3 < raw <= 7 else (raw if raw <= 7 else 0)
                return {"active": active,
                        "versions": [(body[7 + 2 * i] << 8) | body[6 + 2 * i] for i in range(4)]}
        raise RuntimeError("161 状态无应答")

    def read_config(self, cfg_id):
        chunks, total = {}, None
        for body in self.exchange(build(CMD_READ, bytes([cfg_id, PKG])), wait=2.0):
            if body[2] != CMD_READ:
                continue
            total, index = body[3], body[4]
            chunks[index] = bytes(body[6:6 + PKG])
            if len(chunks) >= total:
                break
        if not total or len(chunks) < total:
            raise RuntimeError(f"163 读配置不完整: {len(chunks)}/{total}")
        blob = bytearray(total * PKG)
        for i, c in chunks.items():
            blob[i * PKG:(i + 1) * PKG] = c
        return blob

    def apply(self, cfg_id):
        return any(b[2] == CMD_APPLY for b in self.exchange(build(CMD_APPLY, bytes([cfg_id]))))


class ExtKeyMapper:
    """独立 HID 句柄的映射配置读写（与引擎读线程并存，Windows 输入报告多句柄复制）。"""

    def __init__(self):
        self._lock = threading.Lock()

    def _pad(self):
        return Pad()

    def read_mapping(self):
        """返回六拓展键当前映射 [{name, target, turbo, freq}]（只读，不动备份）。"""
        with self._lock:
            pad = self._pad()
            st = pad.read_status()
            blob = bytearray(pad.read_config(st["active"]))
            pad.apply(st["active"])
        out = []
        for name, kid in EXT_KEYS:
            tgt, turbo, freq = blob[13 + kid * 3:13 + kid * 3 + 3]
            out.append({"name": name, "target": tgt, "target_name": TARGET_NAMES.get(tgt, str(tgt)),
                        "turbo": turbo, "freq": freq})
        return out

    def _save_backup(self, blob):
        try:
            with open(backup_path(), "wb") as f:
                f.write(bytes(blob))
        except OSError:
            pass

    def _commit(self, pad, blob):
        """写→读回校验→应用→保存。失败抛异常（调用方决定是否还原）。"""
        st = pad.read_status()
        cfg = st["active"]
        ver = ((blob[226] << 8) | blob[225]) + 1
        blob[225:227] = struct.pack("<H", ver)
        packs = [blob[i:i + PKG] for i in range(0, len(blob), PKG)]
        if not any(b[2] == CMD_WRITE_START for b in
                   pad.exchange(build(CMD_WRITE_START, bytes([cfg, 0, len(packs), PKG])))):
            raise RuntimeError("164 写-开始无 ACK")
        for i, p in enumerate(packs):
            if not any(b[2] == CMD_WRITE_PACK for b in pad.exchange(build(CMD_WRITE_PACK, bytes([i]) + p))):
                raise RuntimeError(f"165 包 {i} 无 ACK")
        back = pad.read_config(cfg)
        if bytes(back) != bytes(blob):
            raise RuntimeError("写后读回不一致")
        if not pad.apply(cfg):
            raise RuntimeError("162 应用无 ACK")
        time.sleep(0.4)
        if not any(b[2] == CMD_SAVE for b in
                   pad.exchange(build(CMD_SAVE, struct.pack("<H", ver)), wait=1.5)):
            raise RuntimeError("166 保存无 ACK")
        enable_raw_stream(pad)   # 0xEF 位图流保险（同 macro._commit_checked）
        return ver

    def set_targets(self, mapping):
        """按 {name: target} 改六键映射（其余键字节不动），写+应用+保存。
        仅当当前不是测试态时才快照备份（防把测试映射存成"用户原始配置"）。"""
        with self._lock:
            pad = self._pad()
            st = pad.read_status()
            blob = bytearray(pad.read_config(st["active"]))
            kid_of = dict(EXT_KEYS)
            cur = {n: blob[13 + k * 3] for n, k in kid_of.items()}
            if cur != TEST_TARGETS:
                self._save_backup(blob)
            for name, tgt in mapping.items():
                kid = kid_of[name]
                blob[13 + kid * 3:13 + kid * 3 + 3] = bytes([tgt, 0, 0])
            ver = self._commit(pad, blob)
        return {"ok": True, "version": ver,
                "mapping": [{"name": n, "target_name": TARGET_NAMES.get(t, str(t))}
                            for n, t in mapping.items()]}

    def restore(self):
        """关闭测试模式：六键全部写透传（255，中性出厂态）。
        当前本就不是测试态时空操作（防误清用户在官方软件设置的键位）。
        注：不读备份——早期备份可能已被归因实验污染；用户键位可在官方软件重设。"""
        with self._lock:
            pad = self._pad()
            st = pad.read_status()
            blob = bytearray(pad.read_config(st["active"]))
            kid_of = dict(EXT_KEYS)
            cur = {n: blob[13 + k * 3] for n, k in kid_of.items()}
            if cur != TEST_TARGETS:
                return {"ok": True, "already": True, "version": (blob[226] << 8) | blob[225]}
            for _, kid in EXT_KEYS:
                blob[13 + kid * 3:13 + kid * 3 + 3] = bytes([255, 0, 0])
            ver = self._commit(pad, blob)
        return {"ok": True, "version": ver}


MAPPER = ExtKeyMapper()
