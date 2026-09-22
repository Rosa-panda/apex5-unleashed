# 只读诊断（2026-09-22）：当前槽位/版本/键表 + cmd16 传输开关现状
import sys
sys.path.insert(0, 'app')
import extkeys

pad = extkeys.Pad()
st = pad.read_status()
print('active slot =', st['active'])
print('versions =', st['versions'])
m = extkeys.MAPPER.read_mapping()
for e in m:
    print(e['name'], 'target=', e['target'], '(', e['target_name'], ') turbo=', e['turbo'], 'freq=', e['freq'])
