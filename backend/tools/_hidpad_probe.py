# HID 手柄输出探针（2026-09-22）：直读八爪鱼5 的标准 gamepad HID 集合输入报告。
# 与浏览器 Gamepad API / 游戏同源。拓展键固件映射若生效，按 M 键这里应看到
# 对应老按键的 bit 翻转（M1→select 等）。
# 用法：跑 60s；先打印枚举清单自证连通，再打印报告字节变化。
import sys
import time

import hid

VID = 0x37D7

# 1) 枚举：列出该厂商所有接口
print('=== HID 枚举（vid=0x37D7） ===')
targets = []
for d in hid.enumerate(VID):
    print(f"path=...{d['path'][-28:]}  usage_page=0x{d['usage_page']:04X} usage=0x{d['usage']:02X}  rel={d['release_number']}")
    # 标准 gamepad top-level collection：usage page 0x01(generic desktop) usage 0x05(gamepad)
    if d['usage_page'] == 1 and d['usage'] == 5:
        targets.append(d)
print(f'gamepad 集合数: {len(targets)}')
if not targets:
    print('!! 没找到 gamepad 集合——手柄可能休眠/未连，或以其他 usage 枚举')
    sys.exit(0)

# 2) 打开并监听报告变化（60 秒）
dev = hid.device()
dev.open_path(targets[0]['path'])
dev.set_nonblocking(0)
print(f'已打开 gamepad 集合，监听 300 秒（5 分钟）……随时按：M1-M4 各几次 + 真 A / LB 对照 + 摇杆晃一下')
print('提示：M1 应映射为 select(视图)，M3 应映射为 lb——若这些 bit 不动即固件映射未生效')

last = None
t0 = time.time()
n = 0
distinct = {}
next_hb = 10
while time.time() - t0 < 300:
    r = bytes(dev.read(64, timeout_ms=100))
    if r:
        n += 1
        distinct[r] = distinct.get(r, 0) + 1
        if r != last:
            print(f'  [{time.time()-t0:5.1f}s] 变化: {r.hex(" ")}')
            last = r
    if time.time() - t0 >= next_hb:
        print(f'  -- 心跳 {next_hb}s: 累计 {n} 份报告，{len(distinct)} 种不同内容 --')
        next_hb += 30
print(f'共 {n} 份报告，{len(distinct)} 种内容。若只有 1 种 = 窗口内没人按/无输出；')
print('出现 2+ 种 = 有按键输出，上面逐条列出。')
