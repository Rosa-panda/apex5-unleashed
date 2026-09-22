# 只读诊断（2026-09-22）：cmd16 传输开关五标志现状
# 顺序（ADR-019 修订B）：手柄数据 / 私有原始 / 键盘 / 鼠标 / 第三方控制；255=保持
import os
import sys

sys.path.insert(0, 'app')
import extkeys

pad = extkeys.Pad()
for body in pad.exchange(extkeys.build(16)):
    if body[2] == 16:
        flags = [body[5 + i] for i in range(5)]
        names = ['手柄数据', '私有原始', '键盘', '鼠标', '第三方控制']
        for n, v in zip(names, flags):
            print(n, '=', v)
        break
