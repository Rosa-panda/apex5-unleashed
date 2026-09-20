# P1 体感流探针（企划书 §一）：验证 0xEF 流的 gyro/accel 字节活着 + 采零偏基线。
# 只读。跑前退出工具。布局（openflydigi 同源，待本探针复核）：摇杆@4/6/8/10、
# 32键位图@11..14、gyro@18/20/22、accel@24/26/28（i16 LE），gyro scale=1000/16384 mdps。
import struct
import sys
import time

from _common import exchange_try, open_pad, report, wait_user
import extkeys


def frames(pad, seconds):
    """收 N 秒 0xEF 帧，返回 [(t, body)]（body=已剥报告头 4B 的流帧体，含 0xEF@0）。"""
    end = time.time() + seconds
    out = []
    while time.time() < end:
        r = bytes(pad.dev.read(64, timeout_ms=30))
        if len(r) > 29 and r[0] == 0x04 and r[1] == 0x5A and r[2] == 0xA5 and r[3] == 0xEF:
            out.append((time.time(), r))
    return out


def stats(samples, off):
    vals = [struct.unpack_from("<h", r, off)[0] for _, r in samples]
    if not vals:
        return None
    return {"min": min(vals), "max": max(vals), "avg": sum(vals) / len(vals)}


def main():
    report("P1 体感流探针：gyro@18/20/22 accel@24/26/28")
    pad = open_pad()
    ok = extkeys.enable_raw_stream(pad)
    print(f"cmd17 开流（0xFF=保持不变语义）：{'OK' if ok else '无 ACK（继续观察流）'}")

    print("静置采样 3 秒，手柄放桌上别动…")
    base = frames(pad, 3.0)
    print(f"  收到 {len(base)} 帧（{len(base) / 3.0:.0f} Hz）")
    if not base:
        print("✗ 0xEF 流没有帧——检查 cmd17 是否真的开了（见 DEV-STATUS 开关 RAM 态坑）")
        return 1

    scale = 1000.0 / 16384
    names = ["gyroX@18", "gyroY@20", "gyroZ@22", "accX@24", "accY@26", "accZ@28"]
    print("\n[静置基线] 字段  min / avg / max（原始值）")
    base_stats = {}
    for i, nm in enumerate(names):
        s = stats(base, 18 + 2 * i)
        base_stats[nm] = s
        extra = f"  ({s['avg'] * scale:+.1f} mdps)" if nm.startswith("gyro") else ""
        print(f"  {nm:9s} {s['min']:+6d} / {s['avg']:+8.1f} / {s['max']:+6d}{extra}")

    wait_user("\n现在【持续晃动手柄】5 秒（播完自动停）…")
    move = frames(pad, 5.0)
    print(f"  收到 {len(move)} 帧（{len(move) / 5.0:.0f} Hz）")
    print("\n[晃动对比] 字段  静置max幅 → 晃动max幅（判定该轴活没活）")
    alive = 0
    for i, nm in enumerate(names):
        s2 = stats(move, 18 + 2 * i)
        b = base_stats[nm]
        span_b = b["max"] - b["min"]
        span_m = s2["max"] - s2["min"]
        hit = "✓活" if span_m > max(3 * span_b, 8) else "✗死"
        if hit.startswith("✓"):
            alive += 1
        print(f"  {nm:9s} {span_b:6d} → {span_m:6d}  {hit}")

    print("\n[结论回填企划书 §三#1]")
    print(f"  流速率：~{len(base) / 3.0:.0f} Hz（静置）/ ~{len(move) / 5.0:.0f} Hz（晃动）")
    print(f"  活轴：{alive}/6")
    print("  零偏（静置 avg，软件层死区/校准用）：")
    for nm, s in base_stats.items():
        print(f"    {nm}: {s['avg']:+.1f}")
    print("  首帧原文：", " ".join(f"{x:02X}" for x in base[0][1][:30]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
