# 真机只读探针：出厂宏区解析（新代码）+ 键表 M 键现状
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))
import extkeys
import macro

r = macro.MANAGER.read()
print(f"宏区: cfg={r['cfg']} size={r['size']}B version={r['version']} 宏数={len(r['macros'])}")
for m in r["macros"]:
    print(" ", m)
print("\n键表:")
for k in extkeys.MAPPER.read_mapping():
    print(f"  {k['name']}: {k['target_name']} (target={k['target']})")
