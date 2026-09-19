# 扫描空间站 HTTP 缓存：找适配包/游戏相关数据
import os
import glob

CACHE = r"C:\Users\laisn\AppData\Roaming\Flydigi Space Station\Cache\Cache_Data"

# 已知官方适配的游戏关键词（小写）。命中即说明该缓存文件含游戏适配数据
GAME_KEYS = [b"elden ring", b"forza", b"call of duty", b"cyberpunk", b"god of war",
             b"eldritch", b"monster hunter", b"sekiro", b"dark souls", b"gtav", b"gta5",
             b"triggerconfig", b"adapter", b"gameid", b"apex5"]
# protobuf 线格式特征：AdapterTriggerConfigParam 字段标签常见字节
PB_TAGS = [b"\x08\x01\x12", b"\x08\x02\x12", b"\x08\x03\x12"]

hits = {k: [] for k in GAME_KEYS}
pbcount = 0
files = glob.glob(os.path.join(CACHE, "f_*")) + glob.glob(os.path.join(CACHE, "data_*"))
print(f"scanning {len(files)} cache files ...")
for fp in files:
    try:
        blob = open(fp, "rb").read()
    except OSError:
        continue
    low = blob.lower()
    matched = [k for k in GAME_KEYS if k in low]
    if matched:
        hits.setdefault(tuple(matched) if False else "m", None)  # noop
        for k in matched:
            hits[k].append((fp, len(blob)))
    # protobuf 特征粗计
    if any(t in blob[:4000] for t in PB_TAGS):
        pbcount += 1

for k, lst in hits.items():
    if lst:
        print(f"{k.decode()}: {len(lst)} files, e.g. {os.path.basename(lst[0][0])} ({lst[0][1]//1024}KB)")
print(f"protobuf-tag-suspect files: {pbcount}")
