# 任务#8 第一步：只读探测映射配置（cmd 161 状态 / 163 读 / 162 恢复）
# 键表布局来自 openflydigi (MIT, 实机验证) + 官方 SDK 反编译交叉确认：
#   blob[13 + keyid*3] 起 = {目标键id, turbo模式, 频率}，键id: 18=m1 19=m2 20=m3 21=m4 22=m5 23=m6
# 注意：读配置会把该槽位变成活动配置，读完必须把原槽位应用回去。
import os
import struct
import sys
import time

import hid

VID, PID = 0x37D7, 0x2501
USAGE_VENDOR_PAGE, USAGE_VENDOR = 0xFFA0, 0xA0  # usage_page 0xFFA0
PKG = 20

CMD_STATUS, CMD_APPLY, CMD_READ = 161, 162, 163
KEY_NAMES = {0: "up", 1: "right", 2: "down", 3: "left", 4: "a", 5: "b",
             6: "select", 7: "x", 8: "y", 9: "start", 10: "lb", 11: "rb",
             12: "lt", 13: "rt", 14: "thl", 15: "thr", 16: "c", 17: "z",
             18: "m1", 19: "m2", 20: "m3", 21: "m4", 22: "m5", 23: "m6",
             24: "menu/fn", 25: "turbo", 27: "home", 28: "back"}
TARGET_SENTINELS = {255: "identity", 32: "macro", 254: "keyboard"}


def checksum(buf, start, end):
    return sum(buf[start:end]) & 0xFF


def build(cmd, payload=b""):
    """校验和版帧：len = payload+2（含 cmd+len 两字节），校验和在 3+len。"""
    buf = bytearray(32)
    buf[0], buf[1], buf[2], buf[3] = 0x03, 0x5A, 0xA5, cmd
    buf[4] = len(payload) + 2
    buf[5:5 + len(payload)] = payload
    buf[3 + buf[4]] = checksum(buf, 3, 3 + buf[4])
    return bytes(buf)


def open_vendor():
    for d in hid.enumerate(VID, PID):
        if d.get("usage_page") == USAGE_VENDOR_PAGE:
            dev = hid.device()
            dev.open_path(d["path"])
            dev.set_nonblocking(False)
            return dev
    raise RuntimeError("vendor 接口未找到")


class Pad:
    def __init__(self):
        self.dev = open_vendor()

    def exchange(self, frame, wait=0.8):
        """发送并收集 wait 秒内的 5A A5 命令应答（已剥 report id）。
        注意：hid.device.read 返回单条报告（int 列表），不是报告列表。"""
        self.dev.write(frame)
        end = time.time() + wait
        out = []
        while time.time() < end:
            r = bytes(self.dev.read(64, timeout_ms=30))
            if len(r) > 7 and r[0] == 0x04 and r[1] == 0x5A and r[2] == 0xA5:
                if r[3] == 0xEF:
                    continue                    # 体感流，忽略
                out.append(r[1:])               # 剥 report id
                end = max(end, time.time() + 0.15)   # 有应答就顺延，收尾包
        return out

    def read_status(self):
        for body in self.exchange(build(CMD_STATUS)):
            if body[2] == CMD_STATUS:
                raw = body[5]
                active = raw - 4 if 3 < raw <= 7 else (raw if raw <= 7 else 0)
                versions = [(body[7 + 2 * i] << 8) | body[6 + 2 * i] for i in range(4)]
                return {"active": active, "versions": versions}
        return None

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
            raise RuntimeError(f"读配置不完整: {len(chunks)}/{total}")
        blob = bytearray(total * PKG)
        for i, c in chunks.items():
            blob[i * PKG:(i + 1) * PKG] = c
        return bytes(blob)

    def apply(self, cfg_id):
        return any(b[2] == CMD_APPLY for b in self.exchange(build(CMD_APPLY, bytes([cfg_id]))))


def decode_target(v):
    return TARGET_SENTINELS.get(v, KEY_NAMES.get(v, f"raw{v}"))


def main():
    pad = Pad()
    st = pad.read_status()
    if not st:
        print("状态命令无应答")
        return 1
    active = st["active"]
    print(f"活动槽位: {active}  版本号: {st['versions']}")
    blob = pad.read_config(active)
    proto = struct.unpack_from("<H", blob, 0)[0]
    pkgs = blob[2]
    dver = struct.unpack_from("<H", blob, 225)[0]
    print(f"proto={proto >> 8}.{proto & 0xF}  pkg_count={pkgs}  blob={len(blob)}B  data_version={dver}")
    print("--- 键表 (13..109, 每键 [目标, turbo, 频率]) ---")
    for kid in range(32):
        off = 13 + kid * 3
        tgt, turbo, freq = blob[off:off + 3]
        name = KEY_NAMES.get(kid, f"key{kid}")
        interesting = kid in (18, 19, 20, 21, 22, 23) or tgt != 255
        if interesting:
            print(f"  [{kid:2d}] {name:8s} -> {decode_target(tgt):10s} turbo={turbo} freq={freq}"
                  + ("   <<<< 拓展键" if kid in (18, 19, 20, 21, 22, 23) else ""))
    print("其余键全部 identity(255)" if all(blob[13 + k * 3] == 255 for k in range(32)
          if k not in (18, 19, 20, 21, 22, 23)) else "")
    pad.apply(active)          # 读已把 active 切成现役，重新应用确保状态不变
    print(f"已重新应用槽位 {active}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
