# 拓展键→键盘通道编码实验（ADR-019 修订A）：六键键表写 [254, F13+i usage, 0]
# 验证目标：按拓展键时键盘接口（MI_01）是否输出 F13-F18 —— 确认键码在中间字节。
# 用法：python extkey_kbtest.py set     写入键盘实验态
#       python extkey_kbtest.py revert  还原为测试模式 TEST_TARGETS
import sys

import extkeys

KB_TARGETS = {name: 0x68 + i for i, (name, _) in enumerate(extkeys.EXT_KEYS)}  # F13-F18


def set_kb():
    pad = extkeys.Pad()
    st = pad.read_status()
    blob = bytearray(pad.read_config(st["active"]))
    kid_of = dict(extkeys.EXT_KEYS)
    cur = {n: blob[13 + k * 3] for n, k in kid_of.items()}
    if cur == KB_TARGETS:
        print("已是键盘实验态，跳过")
        return
    if cur != extkeys.TEST_TARGETS:
        extkeys.MAPPER._save_backup(blob)   # 非测试态才快照（防污染备份）
    for name, kid in kid_of.items():
        blob[13 + kid * 3:13 + kid * 3 + 3] = bytes([254, KB_TARGETS[name], 0])
    ver = extkeys.MAPPER._commit(pad, blob)
    print(f"已写入键盘实验态 版本={ver}: " +
          " ".join(f"{n}=[254,{KB_TARGETS[n]:#04x}]" for n, _ in extkeys.EXT_KEYS))


def revert():
    """直接写回测试模式目标（不走 set_targets——当前态非测试态，会被误存成备份）。"""
    pad = extkeys.Pad()
    st = pad.read_status()
    blob = bytearray(pad.read_config(st["active"]))
    kid_of = dict(extkeys.EXT_KEYS)
    for name, kid in kid_of.items():
        blob[13 + kid * 3:13 + kid * 3 + 3] = bytes([extkeys.TEST_TARGETS[name], 0, 0])
    ver = extkeys.MAPPER._commit(pad, blob)
    print(f"已还原测试模式 版本={ver}")


if __name__ == "__main__":
    (revert if (sys.argv[1:] or ["set"])[0] == "revert" else set_kb)()
