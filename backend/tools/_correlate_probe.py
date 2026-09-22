# 被动对时探针（2026-09-22）：同时监听 0xEF 位图（物理按压）与标准 gamepad 接口（映射输出），
# 用户正常使用手柄即可，两个流自动按时间戳对齐——M 键按下时刻若出现对应老按键输出即铁证。
# 只读，不写任何命令；与后台进程多句柄并存。
import os
import sys
import threading
import time

sys.path.insert(0, 'app')
import hid
import extkeys

VID = 0x37D7
DUR = 600  # 10 分钟

# 目标输出 bit 对照（映射目标 → gamepad 报告里期望的按钮位，跑起来后从实测校准）
TARGETS = {'m1': 6, 'm2': 9, 'm3': 10, 'm4': 11, 'lm': 16, 'rm': 17}

lock = threading.Lock()
t0 = time.time()

def log(msg):
    with lock:
        print(f'[{time.time()-t0:7.2f}s] {msg}', flush=True)

def bitmap_names(bits):
    return [n for n, kid in extkeys.EXT_KEYS if bits >> kid & 1]

def vendor_thread():
    # 第二句柄开 vendor 集合，解码 0xEF 位图（与 engine._classify 同解码）
    try:
        d = hid.device()
        opened = False
        for info in hid.enumerate(VID):
            if info['usage_page'] == 0xFFA0:
                d.open_path(info['path'])
                opened = True
                break
        if not opened:
            log('VENDOR 打开失败')
            return
        log('VENDOR 监听中（0xEF 位图）')
        last = None
        while time.time() - t0 < DUR:
            try:
                r = bytes(d.read(64, timeout_ms=100))
            except Exception as e:
                log(f'VENDOR 读异常 {e}，重开')
                time.sleep(0.5)
                try:
                    d.open_path(info['path'])
                except Exception:
                    pass
                continue
            if len(r) > 14 and r[0] == 0x04 and r[3] == 0xEF:
                bits = r[11] | (r[12] << 8) | (r[13] << 16) | (r[14] << 24)
                if bits != last:
                    names = bitmap_names(bits)
                    if names:
                        log(f'物理按压: {"+".join(names)}')
                    last = bits
    except Exception as e:
        log(f'VENDOR 线程退出: {e}')

def pad_thread():
    try:
        d = hid.device()
        opened = False
        for info in hid.enumerate(VID):
            if info['usage_page'] == 1 and info['usage'] == 5:
                d.open_path(info['path'])
                opened = True
                break
        if not opened:
            log('GAMEPAD 打开失败')
            return
        log('GAMEPAD 监听中（映射输出）')
        last = None
        while time.time() - t0 < DUR:
            r = bytes(d.read(64, timeout_ms=100))
            if r and r != last:
                # 按钮位在 byte[10]（byte[8..9]=LT 16bit；中性 byte10=0x00，
                # 实测出现过 0x10/0x20/0x80/0xa0）
                btn = r[10] if len(r) > 10 else 0
                prev = (last[10] if len(last) > 10 else 0) if last else 0
                if btn != prev:
                    log(f'按钮输出: 0x{btn:02x}  (完整: {r.hex(" ")})')
                last = r
    except Exception as e:
        log(f'GAMEPAD 线程退出: {e}')

log(f'启动：被动监听 {DUR}s，用户正常使用手柄即可')
threading.Thread(target=vendor_thread, daemon=True).start()
pad_thread()
log('结束')
