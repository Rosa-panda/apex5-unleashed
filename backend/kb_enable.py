# cmd16/17 原始数据传输开关：读状态 → 使能键盘数据 → 复读
# 帧：03 5A A5 [cmd] [len] [payload] [CRC]，len=payload+2，CRC=sum(frame[3:3+len])
import sys

sys.path.insert(0, "app")
from extkeys import Pad, build

FLAG_NAMES = ["手柄数据", "私有原始数据", "键盘数据", "鼠标数据", "第三方控制"]


def read_flags(pad):
    for body in pad.exchange(build(16)):
        if body[2] == 16:
            flags = {n: body[5 + i] for i, n in enumerate(FLAG_NAMES)}
            ctrl = bytes(body[10:30]).split(b"\0")[0].decode("ascii", "replace")
            return flags, ctrl
    raise RuntimeError("cmd16 无应答")


def main():
    pad = Pad()
    f1, ctrl = read_flags(pad)
    print(f"当前开关: {f1}  控制方={ctrl!r}")
    # 使能键盘数据（其余 255=保持不变）
    acks = pad.exchange(build(17, bytes([255, 255, 1, 255, 255])))
    ok = any(b[2] == 17 for b in acks)
    print(f"cmd17 使能键盘: {'ACK' if ok else '无 ACK'}")
    f2, ctrl2 = read_flags(pad)
    print(f"复读开关: {f2}  控制方={ctrl2!r}")


if __name__ == "__main__":
    main()
