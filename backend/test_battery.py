# 电量显示端到端自测（Mock 全链路）：attach → cmd1 心跳 → _capture_battery → snapshot。
# 跑法：python test_battery.py
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "app"))

import engine as E
import transport

eng = E.Engine(force_mock=True)
eng.attach(transport.MockPad())
time.sleep(0.1)
eng.refresh_battery()

deadline = time.time() + 2
while time.time() < deadline and eng.battery is None:
    time.sleep(0.05)

assert eng.battery is not None, "cmd1 心跳没抓到电量"
assert eng.battery["level"] == 4 and eng.battery["charging"] is False, eng.battery
print("✓ Mock 端到端电量:", eng.battery)

snap = eng.snapshot()["device"]
assert snap["battery"]["level"] == 4, snap
print("✓ snapshot 携带电量:", snap["battery"])

# 解析层：充电位（高半字节 1）。合成帧按真机布局：body[5]=0x80 设备类型，body[11]=电量
BATT_BODY = bytes([0x5A, 0xA5, 0x01, 0x01, 0x00, 0x80, 0x02]) + bytes(4)   # body[0..10]
eng._capture_battery(BATT_BODY + b"\x14")
assert eng.battery["level"] == 4 and eng.battery["charging"] is True, eng.battery
print("✓ 充电位解析:", eng.battery)

# 边界：超量程钳位
eng._capture_battery(BATT_BODY + b"\x0f")
assert eng.battery["level"] == 5, eng.battery
print("✓ 超量程钳位到 5:", eng.battery)

eng.detach("收尾")
print("\n全部通过")
