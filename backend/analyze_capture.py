# 分析抓包日志：按钮位变化（字节>=10）按 bit 聚合统计
import re
import sys
from collections import Counter

LOG = sys.argv[1] if len(sys.argv) > 1 else None
if not LOG:
    import glob
    import os
    LOG = max(glob.glob(r"C:\Users\laisn\.claude\projects\C--Users-laisn--claude-ctf-workspace\*\tool-results\b9w13be68.txt"), key=os.path.getmtime)

bit_stats = Counter()       # (offset, bit) -> 翻转次数
samples = []
for line in open(LOG, encoding="utf-8", errors="replace"):
    m = re.match(r"\[(\d+)\] (?:[0-9a-f]{2} )+ ?changed: (.+)$", line.strip())
    if not m:
        continue
    iface, changes = m.group(1), m.group(2)
    for off, prev, cur in re.findall(r"([0-9A-F]{2}):([0-9A-F]{2})->([0-9A-F]{2})", changes):
        off = int(off, 16)
        if off < 10:            # 0-9 = 轴数据，跳过
            continue
        xor = int(prev, 16) ^ int(cur, 16)
        for b in range(8):
            if xor & (1 << b):
                bit_stats[f"iface{iface} byte{off} bit{b}"] += 1
        samples.append(line.strip())

print("=== 按钮位翻转统计（字节>=10）===")
for k, v in bit_stats.most_common(30):
    print(f"{k}: {v} 次")
print(f"\n=== 样本（前 15 条）===")
for s in samples[:15]:
    print(s)
