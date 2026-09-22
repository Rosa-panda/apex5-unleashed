# 一次性修复脚本（2026-09-22）：把 9-19 归因实验还原透传前备份的用户键表写回固件。
# 证据链见当天对话：检测链（0xEF→UI）正常，键表六键全 255 透传才是「拓展键不能用」根因；
# 备份 ver=55679 内容 m1:6 m2:9 m3:10 m4:11 lm:16 rm:17。
# 流程：保护历史备份 → set_targets 写回 → 读回验证（_commit 自带写后读回校验+保存+流保险）。
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'app'))
import extkeys  # noqa: E402

RESTORE = {'m1': 6, 'm2': 9, 'm3': 10, 'm4': 11, 'lm': 16, 'rm': 17}

src = extkeys.backup_path()
bak = src + '.user-55679'
if os.path.exists(src) and not os.path.exists(bak):
    shutil.copy2(src, bak)
    print(f'[1] 历史备份已保护 → {os.path.basename(bak)}')
else:
    print(f'[1] 备份保护跳过（原件缺失或已存在保护副本）')

pad = extkeys.Pad()
st = pad.read_status()
print(f'[2] active 槽={st["active"]}  版本={st["versions"]}')

# 第二句柄偶发 OSError: read error（与后台进程句柄读竞争），整体重试兜底
for attempt in range(1, 4):
    try:
        r = extkeys.MAPPER.set_targets(RESTORE)
        print(f'[3] 写回完成 version={r["version"]}（第 {attempt} 次尝试）')
        break
    except OSError as e:
        print(f'[3] 第 {attempt} 次尝试 HID 抖动：{e}，重试…')
else:
    raise SystemExit('连续 3 次 HID 读失败——手柄可能忙/休眠，稍后重试')

m = extkeys.MAPPER.read_mapping()
print('[4] 读回验证:')
for e in m:
    mark = 'OK' if e['target'] == RESTORE[e['name']] else '!! 不一致'
    print(f'    {e["name"]}: target={e["target"]} ({e["target_name"]})  {mark}')
print('[5] 立即生效（162 已应用、166 已保存掉电不丢）；按 M 键应在手柄/游戏里看到对应键输出')
