# 任务#8 归因抓取：六拓展键(LM/RM/M1-M4)按下时，vendor 流/键盘接口哪些字节变化
# 用法：python capture_extkeys.py [秒数=25]
# 输出：每个接口的「变化报告」流（去重：只有字节变化才打印），带时间戳
# 目的：找拓展键专用 bit（有则直接显示+还原透传；无则映射到 6 个不同目标键归因）
import sys
import time

import hid

VID, PID = 0x37D7, 0x2501
DUR = int(sys.argv[1]) if len(sys.argv) > 1 else 25


def open_all():
    devs = []
    for d in hid.enumerate(VID, PID):
        dev = hid.device()
        dev.open_path(d["path"])
        dev.set_nonblocking(True)
        devs.append((f"usage {d['usage_page']:04X}/{d['usage']:04X}", dev))
    return devs


def fmt(prev, cur):
    marks = " ".join(f"{i}:{prev[i]:02x}->{cur[i]:02x}" for i in range(len(cur))
                     if i < len(prev) and prev[i] != cur[i])
    return marks or "(新报告)"


def main():
    devs = open_all()
    alive = dict(devs)
    print(f"监听 {len(devs)} 个接口，{DUR} 秒，逐键按下即记录 ^C 可提前结束")
    last = {name: None for name, _ in devs}
    end = time.time() + DUR
    try:
        while time.time() < end:
            for name in list(alive):
                try:
                    r = bytes(alive[name].read(64))
                except OSError:
                    print(f"{time.strftime('%H:%M:%S')} [{name}] 读取失败，跳过该接口")
                    del alive[name]
                    continue
                if not r:
                    continue
                prev = last[name]
                if prev is None or bytes(r) != bytes(prev):
                    # vendor 体感流(ef)高频，只打印非 ef 或 ef 首次变化
                    body = r[1:] if r[0] in (0x01, 0x03, 0x04) and len(r) > 3 and r[1] == 0x5A else r
                    is_motion = len(body) > 3 and body[0] == 0x5A and body[3] == 0xEF
                    if not is_motion:
                        print(f"{time.strftime('%H:%M:%S')} [{name}] {r.hex(' ')}  |Δ {fmt(prev or r, r)}")
                    last[name] = r
            time.sleep(0.002)
    except KeyboardInterrupt:
        pass
    finally:
        for _, dev in devs:
            dev.close()


if __name__ == "__main__":
    main()
