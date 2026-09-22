// #5 共存仲裁（ADR-029 F2 自 panels.tsx 逐字搬出）
import { useCallback, useEffect, useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { api } from '../../../api'
import { BTN, BTN_ACC, Err, Row, useFlash } from '../ui'

export function ArbitrationPanel() {
  const [o, setO] = useState<any>(null)
  const [msg, flash] = useFlash()
  const load = useCallback(() => { api.expOwner().then((r: any) => setO(r.owner)).catch(e => flash('', e)) }, [flash])
  useEffect(() => { load() }, [load])
  const F = ['xinput', 'private_data', 'keyboard', 'mouse', 'third_party']
  return (
    <div className="space-y-2">
      <Row label="占用方">
        <button className={BTN} onClick={load}><RefreshCw size={11} /> 重新读取</button>
        {o && <span className="text-[11px] text-text-mid">
          标签：<b className="text-text-hi">{o.control_by ?? '（无名）'}</b>
        </span>}
      </Row>
      {o && (
        <div className="text-[10px] text-text-low">
          {F.map(k => `${k}=${o[k]}`).join('  ')}
        </div>
      )}
      <Row label="夺回">
        <button className={BTN_ACC} onClick={() =>
          api.expAcquire().then((r: any) => { setO(r.owner); flash('✓ cmd28 已发（设备实名申请，语义待真机核）') }).catch(e => flash('', e))
        }>发送申请（cmd28，报上名号）</button>
        <span className="text-[10px] text-text-low">配合侧栏的「夺回控制权」一起用：那边重放账本，这边让设备记住是谁</span>
      </Row>
      <Err e={msg} />
    </div>
  )
}
