# P5 摇杆采样流探针：cmd246（0xF6）TestJoystick。RESEARCH §C 只有命令号，
# payload/ACK/流格式全部待探——本脚本做暴力小步探测：试 start payload ∈ {[], [1], [0x01]},
# 收流对比，结束发 [2]/stop 尝试关流（**必须确认流关掉，别留高频流挂着**）。
# 只读。跑前退出工具。
import sys
import time

from _common import exchange_try, hd, open_pad, report


def count_stream(pad, seconds):
    """N 秒内非 ACK 的 0x04 报告数（0xEF 流之外的未知流也算）。"""
    end = time.time() + seconds
    seen = []
    while time.time() < end:
        r = bytes(pad.dev.read(64, timeout_ms=30))
        if len(r) > 7 and r[0] == 0x04:
            if r[1] == 0x5A and r[2] == 0xA5 and r[3] == 0xEF:
                continue          # 已知体感流，不算
            seen.append(r)
    return seen


def main():
    report("P5 cmd246 TestJoystick 采样流探测")
    pad = open_pad()
    print("先测基线：什么都不发，2 秒内非 0xEF 报告数…")
    base = count_stream(pad, 2.0)
    print(f"  基线杂音 {len(base)} 条")

    for payload in (b"", b"\x01", b"\x00"):
        bodies, used_crc = exchange_try(pad, 0xF6, payload)
        acks = [b for b in bodies if b[2] == 0xF6]
        print(f"\npayload={hd(payload) if payload else '(空)'} "
              f"{'校验和' if used_crc else '无校验'} → ACK {len(acks)} 条")
        for b in acks[:3]:
            print(f"  ACK: {hd(b, 3, 16)}")
        time.sleep(0.3)
        stream = count_stream(pad, 2.0)
        print(f"  发完后 2 秒额外流：{len(stream)} 条（基线 {len(base)}）")
        if len(stream) > len(base) * 2 and stream:
            print("  ✓ 疑似采样流开了！前 3 帧原文：")
            for r in stream[:3]:
                print(f"    {hd(r, 0, 32)}")
            print(f"  速率 ~{len(stream) / 2.0:.0f} Hz")
            break

    print("\n尝试关流：发 payload=[2] …")
    exchange_try(pad, 0xF6, b"\x02")
    time.sleep(0.5)
    after = count_stream(pad, 2.0)
    print(f"  关流后 2 秒额外流：{len(after)} 条（基线 {len(base)}）")
    if len(after) > len(base) * 2:
        print("  ⚠ 流还开着！再试空 payload 关流…")
        exchange_try(pad, 0xF6, b"")
        time.sleep(0.5)
        after = count_stream(pad, 2.0)
        print(f"  再关后：{len(after)} 条")
    print("\n→ 结论（哪个 payload 开/关、流帧布局）回填企划书 §三#9 探针结论栏。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
