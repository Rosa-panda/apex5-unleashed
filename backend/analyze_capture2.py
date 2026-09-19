# 分析二次抓包：偏移按十进制解析（capture_keys.py 输出 {o:02d} 是十进制）
import re
import sys
from collections import Counter

LOG = sys.argv[1] if len(sys.argv) > 1 else None
if not LOG:
    import os
    LOG = os.path.join(os.environ.get("TEMP", "."), "cap2.log")

bit_stats = Counter()
samples = []
for line in open(LOG, encoding="utf-8-sig", errors="replace"):
    m = re.match(r"\[(\d+)\] (?:[0-9A-Fa-f]{2} )+ ?changed: (.+)$", line.strip())
    if not m:
        continue
    iface, changes = m.group(1), m.group(2)
    for off, prev, cur in re.findall(r"(\d{2}):([0-9A-F]{2})->([0-9A-F]{2})", changes):
        off = int(off)                      # 十进制偏移
        if off < 10:
            continue
        xor = int(prev, 16) ^ int(cur, 16)
        for b in range(8):
            if xor & (1 << b):
                bit_stats[f"iface{iface} byte{off} bit{b}"] += 1
        samples.append(line.strip())

print("=== 偏移>=10 的位翻转统计 ===")
for k, v in bit_stats.most_common(20):
    print(f"{k}: {v} 次")
if not bit_stats:
    print("（无 —— 可能没按到键，或背键不在该接口上报）")
print("\n=== 样本 ===")
for s in samples[:12]:
    print(s)
