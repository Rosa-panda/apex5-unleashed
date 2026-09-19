# 键盘/鼠标集合读取诊断 v2：尝试所有 usage 0x0001 集合
import hid

for d in hid.enumerate(0x37D7, 0x2501):
    print(f"usage_page={d.get('usage_page'):#06x} usage={d.get('usage'):#06x} "
          f"rel={d.get('release_number')} path=...{d['path'][-30:]}")

for usage in (6, 2, 5):
    hit = [d for d in hid.enumerate(0x37D7, 0x2501)
           if d.get("usage_page") == 1 and d.get("usage") == usage]
    if not hit:
        print(f"usage {usage:#04x}: 无")
        continue
    try:
        dev = hid.device()
        dev.open_path(hit[0]["path"])
        r = dev.read(64, timeout_ms=300)
        print(f"usage {usage:#04x}: read ok {bytes(r).hex(' ')}")
        dev.close()
    except Exception as e:
        print(f"usage {usage:#04x}: FAIL {type(e).__name__}: {e}")
