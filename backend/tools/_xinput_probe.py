# XInput 探针（诊断用，2026-09-22）：验证拓展键固件映射是否真的产生系统输入。
# 键表当前应为 m1:select(back) m2:start m3:lb m4:rb lm:c rm:z。
# 用法：跑起来后依次按 M1/M2/M3/M4 各 1 秒，看哪些 XInput 按钮亮。
import ctypes, sys
sys.stdout.reconfigure(encoding='utf-8')

XINPUT = ctypes.windll.xinput1_4


class XINPUT_STATE(ctypes.Structure):
    _fields_ = [("dwPacketNumber", ctypes.c_uint32),
                ("sLX", ctypes.c_int16), ("sLY", ctypes.c_int16),
                ("sBX", ctypes.c_int16), ("sBY", ctypes.c_int16),
                ("sLT", ctypes.c_int16), ("sRT", ctypes.c_int16),
                ("wButtons", ctypes.c_uint16)]


BTN = [(0x0001, 'UP'), (0x0002, 'DOWN'), (0x0004, 'LEFT'), (0x0008, 'RIGHT'),
       (0x0010, 'START(=m2)'), (0x0020, 'BACK/SELECT(=m1)'), (0x0040, 'LS'), (0x0080, 'RS'),
       (0x0100, 'LB(=m3)'), (0x0200, 'RB(=m4)'), (0x1000, 'A'), (0x2000, 'B'),
       (0x4000, 'X'), (0x8000, 'Y')]

state = XINPUT_STATE()
last = 0
print('监听 XInput 0 号槽 40 秒……请依次按 M1(期望BACK) M2(期望START) M3(期望LB) M4(期望RB)，再按一下真 LB 确认探针正常')
print('（同时也观察：普通 ABXY/十字键按下是否显示——证明探针本身工作正常）')
import time
t0 = time.time()
while time.time() - t0 < 40:
    if XINPUT.XInputGetState(0, ctypes.byref(state)) == 0:
        b = state.wButtons
        if b != last:
            on = [n for m, n in BTN if b & m]
            print(f'  buttons=0x{b:04x}  {on}')
            last = b
    time.sleep(0.03)
print('结束')
