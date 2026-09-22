// #15 危险区（ADR-029 F2 自 panels.tsx 逐字搬出）
import { useState } from 'react'
import { AlertTriangle } from 'lucide-react'
import { api } from '../../../api'
import { BTN_DANGER, Err, Row, useFlash } from '../ui'

export function FactoryResetPanel() {
  const [msg, flash] = useFlash()
  const [confirm, setConfirm] = useState('')
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-1 text-[11px] text-red-300">
        <AlertTriangle size={12} /> 恢复出厂前会自动全量备份（四槽 blob + 灯表 → 数据文件夹 backup_时间戳\）。
        单槽=出厂档案写回（<b>灯光不动、k5 宏会被清</b>）；全部=cmd175（四槽连名字全重置）。
      </div>
      <Row label="确认">
        <input value={confirm} placeholder="输入 RESET"
          className="w-32 rounded border border-border-soft bg-black/30 px-1 py-0.5 text-[11px]"
          onChange={e => setConfirm(e.target.value)} />
      </Row>
      <div className="grid grid-cols-4 gap-2">
        {[0, 1, 2, 3].map(i => (
          <button key={i} className={BTN_DANGER} disabled={confirm !== 'RESET'}
            onClick={() => api.expFactorySlot(i, 'RESET')
              .then(() => flash(`✓ 槽 ${i + 1} 已恢复出厂`)).catch(e => flash('', e))}>
            重置槽 {i + 1}
          </button>
        ))}
      </div>
      <Row label="全部">
        <button className={BTN_DANGER} disabled={confirm !== 'RESET-ALL'}
          onClick={() => api.expFactoryAll('RESET-ALL')
            .then(() => flash('✓ 四槽已全部恢复出厂（重连后生效）')).catch(e => flash('', e))}>
          重置全部（输入 RESET-ALL 解锁）
        </button>
      </Row>
      <Err e={msg} />
    </div>
  )
}
