# 枚举飞智手柄所有 HID 接口
import hid

hits = []
for d in hid.enumerate():
    if d["vendor_id"] == 0x37D7 or "flydigi" in (d.get("product_string") or "").lower() \
            or "apex" in (d.get("product_string") or "").lower():
        hits.append(d)

for d in hits:
    print(f'{d["vendor_id"]:04X}:{d["product_id"]:04X} if={d["interface_number"]} '
          f'usage={d["usage_page"]:04X}/{d["usage"]:04X} product={d["product_string"]!r}')
    print("   path:", d["path"][:90])

if not hits:
    print("NO FLYDIGI DEVICE FOUND — 37d7 全量：")
    for vid, pid in [(0x37D7, 0)]:
        pass
    for d in hid.enumerate():
        pass
    # 全量列出 VID=37d7
    for d in hid.enumerate():
        if d["vendor_id"] == 0x37D7:
            print(f'{d["vendor_id"]:04X}:{d["product_id"]:04X} if={d["interface_number"]} '
                  f'usage={d["usage_page"]:04X}/{d["usage"]:04X} product={d["product_string"]!r}')
