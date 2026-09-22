# 修复冒烟副作用（2026-09-22）：
# 1) 删掉冒烟误存的 extkeymap.json（回到全 gamepad 默认）
# 2) mapping_backup_slot0.bin 被 mock 合成 blob 覆盖——真机重读当前键表重存备份
# 只读固件，不写任何配置命令（162/166 不碰）。
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import extkeys

# 1) 清测试配置
cfgp = extkeys.os.path.join(os.environ["APPDATA"], "Apex5Unleashed", "extkeymap.json")
if os.path.exists(cfgp):
    os.remove(cfgp)
    print("已删除测试配置 extkeymap.json")
else:
    print("extkeymap.json 不存在（无需清理）")

# 2) 真机读当前键表 → 重存备份
pad = extkeys.Pad()
st = pad.read_status()
blob = bytes(pad.read_config(st["active"]))
print(f"真机读键表: slot={st['active']} 版本={blob[225] | (blob[226] << 8)} 长度={len(blob)}")
kid_of = dict(extkeys.EXT_KEYS)
for name, kid in extkeys.EXT_KEYS:
    tgt = blob[13 + kid * 3]
    print(f"  {name}: target={tgt} ({extkeys.TARGET_NAMES.get(tgt, '?')})")
bp = extkeys.backup_path()
with open(bp, "wb") as f:
    f.write(blob)
print(f"备份已重存: {bp} ({len(blob)} 字节)")
