# P4 固件版本探针：cmd48 ExtraInfo，七模块版本（主控/接收器/RF星闪/SI/扳机/屏幕/ADC）。
# 布局假设：BCD 编码，全零=该模块不存在。具体偏移未定，本探针全量转储 + 尽力解码。
# 只读。跑前退出工具。
import sys

from _common import exchange_try, hd, open_pad, report

MODULES = ["主控", "接收器", "RF星闪", "SI", "扳机", "屏幕", "ADC"]


def bcd(v):
    """0x12 -> '1.2'；非 BCD 字节（半字节>9）返回 None。"""
    hi, lo = v >> 4, v & 0xF
    if hi > 9 or lo > 9:
        return None
    return f"{hi}.{lo}"


def main():
    report("P4 cmd48 七模块固件版本")
    pad = open_pad()
    for cmd in (0x30,):
        bodies, used_crc = exchange_try(pad, cmd)
        if bodies:
            print(f"cmd{cmd}（0x{cmd:X}）：{'校验和帧' if used_crc else '无校验帧'} 有 ACK")
            break
    else:
        print("✗ cmd48 无 ACK")
        return 1
    body = next(b for b in bodies if b[2] == 0x30)
    print(f"ACK 长度 {len(body)}  原文：\n  {hd(body)}")

    # 尽力解码：从 [5] 起按 2 字节一版（hi.lo BCD），连零跳过
    print("\n[尽力解码·2B/模块 BCD]")
    got = []
    for i in range(7):
        if 6 + 2 * i + 1 < len(body):
            hi, lo = body[5 + 2 * i], body[6 + 2 * i]
            ver = bcd(lo)
            got.append(f"{MODULES[i]}={hi}/{bcd(lo) if ver else f'0x{lo:02X}?'}")
    print("  " + "  ".join(got))
    print("\n→ 对照官方 UI「关于/固件版本」页核读数；偏移结论回填企划书 §三#4。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
