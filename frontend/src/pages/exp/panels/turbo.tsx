// #2 连发 Turbo（ADR-029 F2 自 panels.tsx 逐字搬出）
import { useCallback, useEffect, useState } from 'react'
import { api } from '../../../api'
import { BTN, Err, NoDev, TARGET_NAMES, TURBO_MODES, useFlash } from '../ui'

export function TurboPanel() {
  const [p, setP] = useState<any>(null)
  const [msg, flash] = useFlash()
  const load = useCallback(() => { api.expProfile().then(setP).catch(e => flash('', e)) }, [flash])
  useEffect(() => { load() }, [load])
  if (!p) return <div className="space-y-2"><NoDev /><Err e={msg} /></div>
  const apply = (k: any) =>
    api.expTurbo(k.kid, k.turbo, k.freq)
      .then((r: any) => { setP(r); flash('✓ 已写入并保存（flash，稍慢属正常）') })
      .catch(e => { flash('', e); load() })
  return (
    <div className="space-y-1">
      <div className="text-[10px] text-text-low">
        固件级连发：写进档案 blob，关工具也生效。开启连发的键会自动映射回自身（官方同款）。
        档案：槽 {p.slot + 1}「{p.title}」（版本 {p.data_version}）
      </div>
      <div className="max-h-64 space-y-0.5 overflow-y-auto pr-1">
        {p.keys.map((k: any) => (
          <div key={k.kid} className="flex items-center gap-2 text-[11px]">
            <span className="w-14 text-text-mid">{k.name}</span>
            <span className="w-12 text-text-low">→{TARGET_NAMES[k.target] ?? k.target}</span>
            <select className="rounded border border-border-soft bg-black/30 px-1 py-0.5 text-[11px]"
              value={k.turbo}
              onChange={e => setP({ ...p, keys: p.keys.map((x: any) => x.kid === k.kid ? { ...x, turbo: +e.target.value } : x) })}>
              {TURBO_MODES.map((m, i) => <option key={i} value={i}>{m}</option>)}
            </select>
            <input type="number" min={1} max={255} value={k.freq} disabled={k.turbo === 0}
              className="w-14 rounded border border-border-soft bg-black/30 px-1 py-0.5 text-[11px] disabled:opacity-40"
              onChange={e => setP({ ...p, keys: p.keys.map((x: any) => x.kid === k.kid ? { ...x, freq: +e.target.value } : x) })} />
            <button className={BTN} onClick={() => apply(k)}>写入</button>
          </div>
        ))}
      </div>
      <Err e={msg} />
    </div>
  )
}
