// #13 握把震动（ADR-029 F2 自 panels.tsx 逐字搬出）
import { useCallback, useEffect, useState } from 'react'
import { api } from '../../../api'
import { BTN, BTN_ACC, Err, NoDev, Row, useFlash } from '../ui'

function SideVib({ s, set }: { s: any; set: (p: any) => void }) {
  return (
    <div className="space-y-1">
      <label className="flex items-center gap-1 text-[11px]">
        <input type="checkbox" checked={!!s.on} onChange={e => set({ on: e.target.checked })} /> 启用
      </label>
      {(['min', 'max', 'scale'] as const).map(k => (
        <Row key={k} label={`${k} ${s[k] ?? 0}`}>
          <input type="range" min={0} max={255} value={s[k] ?? 0} className="w-36"
            onChange={e => set({ [k]: +e.target.value })} />
        </Row>
      ))}
    </div>
  )
}

export function GripVibPanel() {
  const [p, setP] = useState<any>(null)
  const [msg, flash] = useFlash()
  const load = useCallback(() => { api.expProfile().then(setP).catch(e => flash('', e)) }, [flash])
  useEffect(() => { load() }, [load])
  if (!p) return <div className="space-y-2"><NoDev /><Err e={msg} /></div>
  const g = p.grip_vib
  const save = (ng: any) =>
    api.expGripVib(ng.enabled, ng.left, ng.right).then((r: any) => { setP(r); flash('✓ 握把震动已写入') }).catch(e => { flash('', e); load() })
  const set = (patch: any) => { const ng = { ...g, ...patch }; setP({ ...p, grip_vib: ng }); return ng }
  return (
    <div className="space-y-2">
      <Row label="总开关">
        <button className={g.enabled ? BTN_ACC : BTN} onClick={() => save(set({ enabled: !g.enabled }))}>
          {g.enabled ? '开启中' : '已关闭'}
        </button>
        <button className={BTN} onClick={() =>
          save(set({ left: { ...g.left, on: true, min: 0, max: 255, scale: 128 }, right: { ...g.right, on: true, min: 0, max: 255, scale: 128 } }))
        }>「Xbox 感」预设（50%）</button>
        <span className="text-[10px] text-text-low">Min/Max 是触发窗口，Scale 是输出比例</span>
      </Row>
      <div className="grid grid-cols-2 gap-4">
        {(['left', 'right'] as const).map(side => (
          <div key={side} className="space-y-1">
            <div className="text-[11px] font-semibold text-text-mid">{side === 'left' ? '左握把' : '右握把'}</div>
            <SideVib s={g[side]} set={patch => set({ [side]: { ...g[side], ...patch } })} />
          </div>
        ))}
      </div>
      <Row label="">
        <button className={BTN_ACC} onClick={() => save(g)}>写入</button>
      </Row>
      <Err e={msg} />
    </div>
  )
}
