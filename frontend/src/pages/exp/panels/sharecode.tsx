// #11 分享码（ADR-029 F2 自 panels.tsx 逐字搬出）
import { useState } from 'react'
import { api } from '../../../api'
import { BTN, BTN_ACC, BTN_DANGER, Err, Row, useFlash } from '../ui'

export function ShareCodePanel() {
  const [code, setCode] = useState('')
  const [dec, setDec] = useState<any>(null)
  const [msg, flash] = useFlash()
  return (
    <div className="space-y-2">
      <Row label="导出">
        <button className={BTN_ACC} onClick={() =>
          api.expShareEncode('profile').then((r: any) => { setCode(r.code); flash('✓ 当前槽已编码（zlib+base62，含校验）') }).catch(e => flash('', e))
        }>编码当前槽 → 分享码</button>
      </Row>
      <textarea value={code} onChange={e => setCode(e.target.value)} rows={3}
        placeholder="APX5-… 分享码贴这里（导入导出同一框）"
        className="w-full rounded border border-border-soft bg-black/30 p-2 font-mono text-[10px] break-all" />
      <Row label="导入">
        <button className={BTN} onClick={() =>
          api.expShareDecode(code).then((r: any) => { setDec(r); flash('✓ 解码成功，检查预览后再应用') }).catch(e => flash('', e))
        }>解码预览</button>
        {dec && <button className={BTN_DANGER} onClick={() =>
          api.expShareApply(code).then(() => flash('✓ 已写入当前槽（覆盖！）')).catch(e => flash('', e))
        }>应用到当前槽（覆盖）</button>}
      </Row>
      {dec?.profile && (
        <div className="text-[10px] text-text-low">
          预览：槽{dec.slot !== undefined ? `（源槽 ${dec.slot + 1}）` : ''}「{dec.profile.title}」版本 {dec.profile.data_version} ｜
          {' '}连发键 {dec.profile.keys.filter((k: any) => k.turbo).map((k: any) => k.name).join(',') || '无'} ｜
          {' '}体感 target={dec.profile.motion.target}
        </div>
      )}
      <Err e={msg} />
    </div>
  )
}
