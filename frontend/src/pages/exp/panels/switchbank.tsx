// #12 Switch 第二银行（ADR-029 F2 自 panels.tsx 逐字搬出）
import { useCallback, useEffect, useState } from 'react'
import { api } from '../../../api'
import { BTN, BTN_ACC, BTN_DANGER, Err, NoDev, Row, useFlash } from '../ui'

export function SwitchBankPanel() {
  const [d, setD] = useState<any>(null)
  const [slot, setSlot] = useState(0)
  const [msg, flash] = useFlash()
  const load = useCallback(() => { api.expSlots().then(setD).catch(e => flash('', e)) }, [flash])
  useEffect(() => { load() }, [load])
  if (!d) return <div className="space-y-2"><NoDev /><Err e={msg} /></div>
  return (
    <div className="space-y-2">
      <Row label="源槽">
        {[0, 1, 2, 3].map(i => (
          <button key={i} className={slot === i ? BTN_ACC : BTN} onClick={() => setSlot(i)}>
            槽 {i + 1}（{d.titles[i] || '未命名'}）
          </button>
        ))}
      </Row>
      <Row label="同步">
        <button className={BTN_DANGER} onClick={() =>
          api.expSwitchSync(slot).then((r: any) => flash(`✓ 已写入 Switch 银行槽 ${r.switch_slot}（171 落 flash，稍慢）`)).catch(e => flash('', e))
        }>写入 Switch 银行（槽 {slot + 4}）</button>
        <span className="text-[10px] text-text-low">键盘映射自动回透传、被映射走的摇杆回直通（normalise 同官方）</span>
      </Row>
      <Err e={msg} />
    </div>
  )
}
