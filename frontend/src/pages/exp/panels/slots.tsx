// #10 四槽快切（ADR-029 F2 自 panels.tsx 逐字搬出）
import { useCallback, useEffect, useState } from 'react'
import { api } from '../../../api'
import { Err, NoDev, useFlash } from '../ui'

export function SlotsPanel() {
  const [d, setD] = useState<any>(null)
  const [msg, flash] = useFlash()
  const load = useCallback(() => { api.expSlots().then(setD).catch(e => flash('', e)) }, [flash])
  useEffect(() => { load() }, [load])
  if (!d) return <div className="space-y-2"><NoDev /><Err e={msg} /></div>
  return (
    <div className="space-y-2">
      <div className="grid grid-cols-2 gap-2">
        {[0, 1, 2, 3].map(i => (
          <button key={i} className={`rounded-md border p-2 text-left text-[11px] ${d.active === i ? 'border-accent/60 bg-accent/10' : 'border-border-soft hover:border-accent/40'}`}
            onClick={() => api.expSlotApply(i).then(() => { flash(`✓ 已切到槽 ${i + 1}`); load() }).catch(e => flash('', e))}>
            <div className="font-semibold text-text-hi">槽 {i + 1}{d.active === i ? ' ｜ 当前' : ''}</div>
            <div className="text-text-mid">{d.titles[i] || '（未命名）'}</div>
          </button>
        ))}
      </div>
      <div className="text-[10px] text-text-low">
        点卡片即切（162 应用，立即生效不落 flash）。手柄端 Fn+十字键 也能切——「快切」开关在设备设置页。
      </div>
      <Err e={msg} />
    </div>
  )
}
