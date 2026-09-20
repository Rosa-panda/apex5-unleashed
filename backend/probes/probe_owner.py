# P3 代理权实名探针：cmd16 ACK 的 control_by 标签（[10..30) ASCII）。
# 三态各跑一次，对比标签变化（企划书 §三#5 前置）：
#   态1：只开本工具（正常态）  态2：Steam 大模式接管时  态3：飞智空间站服务在跑时
# 只读。跑前退出工具。
import sys

from _common import exchange_try, hd, open_pad, report


def main():
    report("P3 cmd16：占用方实名标签（control_by）")
    pad = open_pad()
    bodies, used_crc = exchange_try(pad, 0x10)
    if not bodies:
        print("✗ cmd16 无 ACK（两版帧都试了）")
        return 1
    body = next(b for b in bodies if b[2] == 0x10)
    print(f"ACK：{'校验和帧' if used_crc else '无校验帧'}  长度 {len(body)}")
    print(f"原文 [3..32)：{hd(body, 3, 32)}")
    if len(body) >= 10:
        print(f"[5] XInputEnabled = {body[5]}")
        print(f"[6] PrivateData   = {body[6]}")
        print(f"[7] Keyboard      = {body[7]}")
        print(f"[8] Mouse         = {body[8]}")
        print(f"[9] 第三方接管Enabled = {body[9]}")
    if len(body) >= 30:
        tag = bytes(body[10:30])
        printable = tag.decode("ascii", errors="replace").rstrip("\x00 ")
        print(f"[10..30) 占用方标签 = {printable!r}")
    else:
        print(f"⚠ ACK 短于 30B，标签区不完整；全文：{hd(body)}")
    print("\n→ 分别在「仅本工具 / Steam大模式 / 空间站服务」三态下各跑一次，")
    print("  把三份标签贴进企划书 §三#5 探针结论栏。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
