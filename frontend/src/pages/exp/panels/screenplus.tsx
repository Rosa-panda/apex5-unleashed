// #14 屏幕补全（ADR-029 F2 自 panels.tsx 逐字搬出）
import { useState } from 'react'
import { api } from '../../../api'
import { BTN, Err, Row, useFlash } from '../ui'

export function ScreenPlusPanel() {
  const [msg, flash] = useFlash()
  const [busy, setBusy] = useState(false)
  const toggle = (sub: number, on: boolean, name: string) => {
    setBusy(true)
    api.expSetting('bit', { sub, on })
      .then(() => flash(`✓ ${name} 已${on ? '开' : '关'}`))
      .catch(e => flash('', e))
      .finally(() => setBusy(false))
  }
  return (
    <div className="space-y-2">
      <Row label="状态栏">
        <button className={BTN} disabled={busy} onClick={() => toggle(8, true, '状态栏常亮')}>常亮开</button>
        <button className={BTN} disabled={busy} onClick={() => toggle(8, false, '状态栏常亮')}>关</button>
        <span className="text-[10px] text-text-low">= 设置块 sub8（屏幕页也有同款）</span>
      </Row>
      <Row label="动画常亮">
        <button className={BTN} disabled={busy} onClick={() => toggle(9, true, '动画常亮')}>开</button>
        <button className={BTN} disabled={busy} onClick={() => toggle(9, false, '动画常亮')}>关</button>
        <span className="text-[10px] text-text-low">= sub9（实测语义可能反转，以真机为准）</span>
      </Row>
      <Row label="GIF 裁剪">
        <span className="text-[10px] text-text-low">帧范围裁剪和恢复出厂动画在「屏幕」页（上传前选帧区间）</span>
      </Row>
      <Err e={msg} />
    </div>
  )
}
