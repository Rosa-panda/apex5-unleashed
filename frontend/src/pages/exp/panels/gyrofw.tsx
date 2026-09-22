// #6 体感映射（固件层）（ADR-029 F2 自 panels.tsx 逐字搬出）
import { useCallback, useEffect, useState } from 'react'
import { api } from '../../../api'
import { BTN, BTN_ACC, Err, KEY_NAMES, NoDev, Row, useFlash } from '../ui'

const MOTION_TARGETS = [['0', '关闭'], ['1', '左摇杆（赛车）'], ['2', '右摇杆（射击）']]
const MOTION_KEYS: Array<[number, string]> = [
  [255, '无激活键'],
  ...Object.entries(KEY_NAMES).map(([k, v]): [number, string] => [+k, v]),
]

export function GyroFwPanel() {
  const [p, setP] = useState<any>(null)
  const [msg, flash] = useFlash()
  const load = useCallback(() => { api.expProfile().then(setP).catch(e => flash('', e)) }, [flash])
  useEffect(() => { load() }, [load])
  if (!p) return <div className="space-y-2"><NoDev /><Err e={msg} /></div>
  const m = p.motion
  const save = (patch: any) =>
    api.expMotion({ ...m, ...patch }).then((r: any) => { setP(r); flash('✓ motion 块已写入并保存') }).catch(e => { flash('', e); load() })
  return (
    <div className="space-y-2">
      <div className="text-[10px] text-text-low">
        固件直通：写 blob 137 motion 块，关工具也生效、零软件延迟。<b className="text-amber-300">与软件层体感互斥</b>。
        当前 target={m.target}（0关/1左摇杆/2右摇杆）
      </div>
      <Row label="映射到">
        {MOTION_TARGETS.map(([v, n]) => (
          <button key={v} className={+m.target === +v ? BTN_ACC : BTN}
            onClick={() => save({ target: +v })}>{n}</button>
        ))}
      </Row>
      {m.target !== 0 && (
        <>
          <Row label="激活键">
            <select className="rounded border border-border-soft bg-black/30 px-1 py-0.5 text-[11px]"
              value={m.enable_key} onChange={e => save({ enable_key: +e.target.value })}>
              {MOTION_KEYS.map(([v, n]) => <option key={v} value={v}>{n}</option>)}
            </select>
            <select className="rounded border border-border-soft bg-black/30 px-1 py-0.5 text-[11px]"
              value={m.enable_type} onChange={e => save({ enable_type: +e.target.value })}>
              <option value={0}>点按切换</option>
              <option value={1}>按住生效</option>
            </select>
          </Row>
          <Row label={`死区 ${m.dead_zone}`}>
            <input type="range" min={0} max={100} value={m.dead_zone} className="w-32"
              onChange={e => save({ dead_zone: +e.target.value })} />
          </Row>
          <Row label={`灵敏度 X/Y ${m.sens_x}/${m.sens_y}`}>
            <input type="range" min={0} max={100} value={m.sens_x} className="w-28" onChange={e => save({ sens_x: +e.target.value })} />
            <input type="range" min={0} max={100} value={m.sens_y} className="w-28" onChange={e => save({ sens_y: +e.target.value })} />
          </Row>
        </>
      )}
      <Err e={msg} />
    </div>
  )
}
