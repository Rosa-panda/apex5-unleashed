# 检查 data_1 缓存文件：是否含 AdapterTriggerConfigParam / 游戏适配数据
import glob
import os
import re

CACHE = r"C:\Users\laisn\AppData\Roaming\Flydigi Space Station\Cache\Cache_Data"
for fp in glob.glob(os.path.join(CACHE, "data_*")):
    blob = open(fp, "rb").read()
    low = blob.lower()
    if b"adapter" not in low and b"trigger" not in low:
        continue
    print(f"== {os.path.basename(fp)} ({len(blob)//1024}KB) ==")
    # 打印可读字符串样本
    strings = re.findall(rb"[\x20-\x7e]{6,}", blob)
    interesting = [s for s in strings if any(k in s.lower() for k in
                   (b"adapter", b"trigger", b"game", b"config", b"http", b".json", b".bin", b"proto"))]
    for s in interesting[:20]:
        print("  ", s[:120].decode(errors="replace"))
