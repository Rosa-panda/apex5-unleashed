# P2 设备设置块探针：cmd 3 一次读回全部能力位图+数值。
# 布局假设（openflydigi settings.py / RESEARCH §I2，待复核）：
#   [5] usable 位图（b0快切 b1XboxHome b2体感去抖 b3映射开关 b4摇杆防抖 b5自动校准
#                  b6回中 b7状态栏）  [6] enabled 同布局  [7]/[8] 关屏+Audio
#   [9] 睡眠分钟  [10] 回报率  [11] 精度  [12] 灵敏度
# 只读。跑前退出工具。
import sys

from _common import bits, exchange_try, hd, open_pad, report

NAMES = ["快切", "XboxHome", "体感去抖", "映射开关", "摇杆防抖", "自动校准", "回中", "状态栏"]
RATE = {1: "1000Hz", 2: "500Hz", 4: "250Hz", 8: "125Hz"}
PREC = {0: "None", 1: "8Bit", 2: "10Bit", 3: "12Bit", 4: "9Bit", 5: "11Bit", 6: "14Bit", 7: "16Bit"}


def main():
    report("P2 cmd3 设置块：能力位图 + 当前值")
    pad = open_pad()
    bodies, used_crc = exchange_try(pad, 3)
    if not bodies:
        print("✗ cmd3 无 ACK（校验和/无校验两版都试了）")
        return 1
    body = next(b for b in bodies if b[2] == 3)
    print(f"ACK：{'校验和帧' if used_crc else '无校验帧'}  原文 {hd(body, 3, 16)}")
    if len(body) < 13:
        print(f"✗ ACK 比预期短（{len(body)}B），布局假设不成立——全量转储：\n  {hd(body)}")
        return 1

    usable, enabled = body[5], body[6]
    print(f"\n[5] usable = 0x{usable:02X}  ({bits(usable)})")
    for i, nm in enumerate(NAMES):
        mark = "✓" if usable >> i & 1 else "✗"
        on = "开" if enabled >> i & 1 else "关"
        print(f"   b{i} {nm}: 支持{mark} 当前{on}")
    print(f"[7] 关屏/屏幕相关 = {body[7]}   [8] Audio/其他 = {body[8]}")
    sleep_min, rate, prec, sens = body[9], body[10], body[11], body[12]
    print(f"[9] 睡眠 = {sleep_min} 分钟（0=永不?）")
    print(f"[10] 回报率 = {rate}（{RATE.get(rate, '未知语义——勿写')}）")
    print(f"[11] 摇杆精度 = {prec}（{PREC.get(prec, '?')}，注意枚举乱序 2=10bit）")
    print(f"[12] 摇杆灵敏度 = {sens}（声明域 14..20，Highest..Lowest）")
    print("\n→ 请对照手柄/官方 UI 核对以上值，结论回填企划书 §三#4 探针结论栏。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
