# 任务#8 写路径真机验证（ADR-016）：最小映射 M1->A，可一键还原
# 流程：读槽0 → 备份 blob → 改 M1 目标=A(4) → 版本+1 → 写(164+165 全42包)
#       → 读回逐字节比对 → 应用(162) → 永久保存(166)
# 还原：python mapping_write_test.py revert（写回备份 blob，同样流程）
import struct
import sys
import time

from mapping_probe import CMD_APPLY, KEY_NAMES, Pad, build

SAVE = None  # cmd 166 在下方定义常量（避免循环依赖）
CMD_SAVE = 166
BACKUP = "mapping_backup_slot0.bin"


def save_version(pad, version):
    """cmd 166：把当前编辑缓冲永久落 flash，payload=uint16 版本 LE。"""
    return any(b[2] == CMD_SAVE for b in pad.exchange(build(CMD_SAVE, struct.pack("<H", version)), wait=1.5))


def write_blob(pad, cfg_id, blob, pkg=20):
    packs = [blob[i:i + pkg] for i in range(0, len(blob), pkg)]
    # 164 写-开始：[cfgId, startIndex, packetNum, packetSize]
    ack = pad.exchange(build(164, bytes([cfg_id, 0, len(packs), pkg])), wait=1.0)
    if not any(b[2] == 164 for b in ack):
        raise RuntimeError("164 写-开始无 ACK")
    for i, p in enumerate(packs):
        ack = pad.exchange(build(165, bytes([i]) + p), wait=1.0)
        if not any(b[2] == 165 for b in ack):
            raise RuntimeError(f"165 包 {i} 无 ACK")
    return len(packs)


def full_flow(pad, blob, note):
    st = pad.read_status()
    cfg = st["active"]
    ver = (blob[226] << 8) | blob[225]
    n = write_blob(pad, cfg, blob)
    print(f"[{note}] 已写槽 {cfg}：{n} 包 {len(blob)}B，新版本 {ver}")
    back = pad.read_config(cfg)
    if bytes(back) != bytes(blob):
        diff = [i for i in range(min(len(back), len(blob))) if back[i] != blob[i]]
        raise RuntimeError(f"读回不一致！{len(diff)} 处差异，首个 offset={diff[0] if diff else '?'}")
    print(f"[{note}] 读回逐字节一致 ✓")
    if not pad.apply(cfg):
        raise RuntimeError("162 应用无 ACK")
    time.sleep(0.5)
    st2 = pad.read_status()
    print(f"[{note}] 已应用槽 {cfg}，回读活动槽={st2['active']}，版本={[hex(v) for v in st2['versions']]}")
    if not save_version(pad, ver):
        raise RuntimeError("166 保存无 ACK")
    print(f"[{note}] 已永久保存（166，版本 {ver}）✓")


def main():
    pad = Pad()
    if len(sys.argv) > 1 and sys.argv[1] == "revert":
        with open(BACKUP, "rb") as f:
            blob = bytearray(f.read())
        blob[225:227] = struct.pack("<H", ((blob[226] << 8) | blob[225]) + 1)
        full_flow(pad, blob, "还原")
        m1 = blob[67:70]
        print(f"还原后 M1 = {list(m1)}（应为原值）")
        return 0

    # 正向：读当前 → 备份 → 改 M1->A
    st = pad.read_status()
    cfg = st["active"]
    blob = bytearray(pad.read_config(cfg))
    with open(BACKUP, "wb") as f:
        f.write(blob)
    print(f"已备份槽 {cfg} 原 blob（{len(blob)}B）→ {BACKUP}")
    m1_old = blob[67:70]
    blob[67], blob[68], blob[69] = 4, 0, 0          # M1(kid18) -> A(kid4)，无 turbo
    blob[225:227] = struct.pack("<H", ((blob[226] << 8) | blob[225]) + 1)
    print(f"M1 {list(m1_old)} ({KEY_NAMES.get(m1_old[0])}) -> [4,0,0] (a)，版本+1")
    full_flow(pad, blob, "写入")
    print("\n>>> 现在按 M1 应该等于按 A。验证后跑: python mapping_write_test.py revert")
    return 0


if __name__ == "__main__":
    sys.exit(main())
