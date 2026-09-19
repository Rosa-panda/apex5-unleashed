# 任务#8 六拓展键归因：全量映射到 6 个互不相同目标 → 用户按键 → 时间序列归因
# 用法：
#   python extkey_attribution.py set      # 写入归因映射（kid18..23 -> select/start/lb/rb/c/z）
#   python extkey_attribution.py revert   # 还原备份 blob（mapping_backup_slot0.bin）
#   python extkey_attribution.py capture  # 监听游戏盘接口 40s 打印按钮字节变化
# 键表：blob[13 + kid*3] = [目标, turbo, 频率]；kid 18..23 = 六拓展键（物理对应待本轮归因）
import struct
import sys
import time

from mapping_probe import CMD_APPLY, Pad, build

CMD_SAVE = 166
BACKUP = "mapping_backup_slot0.bin"
ATTR_TARGETS = {18: 6, 19: 9, 20: 10, 21: 11, 22: 16, 23: 17}   # select/start/lb/rb/c/z
TARGET_NAMES = {6: "select", 9: "start", 10: "lb", 11: "rb", 16: "c", 17: "z"}


def save_version(pad, version):
    return any(b[2] == CMD_SAVE for b in pad.exchange(build(CMD_SAVE, struct.pack("<H", version)), wait=1.5))


def write_blob(pad, cfg_id, blob, pkg=20):
    packs = [blob[i:i + pkg] for i in range(0, len(blob), pkg)]
    if not any(b[2] == 164 for b in pad.exchange(build(164, bytes([cfg_id, 0, len(packs), pkg])))):
        raise RuntimeError("164 写-开始无 ACK")
    for i, p in enumerate(packs):
        if not any(b[2] == 165 for b in pad.exchange(build(165, bytes([i]) + p))):
            raise RuntimeError(f"165 包 {i} 无 ACK")
    return len(packs)


def commit(pad, blob):
    st = pad.read_status()
    cfg = st["active"]
    ver = ((blob[226] << 8) | blob[225]) + 1
    blob[225:227] = struct.pack("<H", ver)
    n = write_blob(pad, cfg, blob)
    back = pad.read_config(cfg)
    if bytes(back) != bytes(blob):
        raise RuntimeError("读回不一致")
    if not pad.apply(cfg):
        raise RuntimeError("162 应用无 ACK")
    time.sleep(0.4)
    if not save_version(pad, ver):
        raise RuntimeError("166 保存无 ACK")
    print(f"槽 {cfg} 已写 {n} 包并读回一致，版本 {ver}，已应用+保存 ✓")


def do_set():
    pad = Pad()
    st = pad.read_status()
    blob = bytearray(pad.read_config(st["active"]))
    with open(BACKUP, "wb") as f:
        f.write(blob)
    print(f"已备份 → {BACKUP}")
    for kid, tgt in ATTR_TARGETS.items():
        blob[13 + kid * 3:13 + kid * 3 + 3] = bytes([tgt, 0, 0])
    commit(pad, blob)
    print("映射：", "  ".join(f"kid{k}->{TARGET_NAMES[t]}" for k, t in ATTR_TARGETS.items()))


def do_revert():
    pad = Pad()
    with open(BACKUP, "rb") as f:
        blob = bytearray(f.read())
    commit(pad, blob)
    print("已还原原配置（M4 键盘映射保留）")


def do_capture():
    import hid
    dev = hid.device()
    for d in hid.enumerate(0x37D7, 0x2501):
        if d.get("usage_page") == 0x0001 and d.get("usage") == 0x0005:
            dev.open_path(d["path"])
            break
    else:
        print("游戏盘接口未找到")
        return 1
    dev.set_nonblocking(True)
    print("监听游戏盘接口 90s：按钮区任何字节变化即打印，每 10s 心跳…")
    last = None
    start = time.time()
    end = start + 90
    next_beat = start + 10
    while time.time() < end:
        r = bytes(dev.read(64))
        if len(r) >= 11:
            btn = tuple(r[0:12])
            if btn != last:
                mark = " ".join(f"{i}:{r[i]:02x}" for i in range(12)
                                if last is not None and r[i] != last[i])
                print(f"{time.strftime('%H:%M:%S')} {'Δ ' + mark if mark else '(基线)'}")
                last = btn
                end = max(end, time.time() + 2.0)
        if time.time() >= next_beat:
            print(f"… {int(time.time() - start)}s")
            next_beat += 10
        time.sleep(0.002)
    dev.close()
    return 0


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else ""
    if action == "set":
        do_set()
    elif action == "revert":
        do_revert()
    elif action == "capture":
        sys.exit(do_capture())
    else:
        print(__doc__)
        sys.exit(1)
