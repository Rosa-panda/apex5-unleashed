// #9 摇杆体检（ADR-029 F2 自 panels.tsx 逐字搬出）
import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../../../api'
import { BTN, BTN_ACC, Err, Row, useFlash } from '../ui'

export function DiagnosticsPanel() {
  const [d, setD] = useState<any>(null)
  const [msg, flash] = useFlash()
  const ref = useRef<HTMLCanvasElement>(null)
  const load = useCallback(() => { api.expDiagData().then(setD).catch(e => flash('', e)) }, [])
  useEffect(() => { load() }, [load])
  useEffect(() => {
    if (!d?.running) { const t = setTimeout(load, 700); return () => clearTimeout(t) }
    const t = setInterval(load, 400)
    return () => clearInterval(t)
  }, [d?.running, load])
  useEffect(() => {
    const cv = ref.current
    if (!cv || !d?.points) return
    const g = cv.getContext('2d')
    if (!g) return
    const W = cv.width, H = cv.height
    g.fillStyle = 'rgba(0,0,0,0.25)'
    g.fillRect(0, 0, W, H)
    g.strokeStyle = 'rgba(255,255,255,0.15)'
    g.beginPath(); g.moveTo(W / 2, 0); g.lineTo(W / 2, H); g.moveTo(0, H / 2); g.lineTo(W, H / 2); g.stroke()
    const M = 32000
    for (const [c, col] of [[0, '#67e8f9'], [2, '#fbbf24']] as Array<[number, string]>) {
      g.fillStyle = col
      for (const p of d.points) {
        const x = W / 2 + (p[c] / M) * (W / 2 - 4)
        const y = H / 2 + (p[c + 1] / M) * (H / 2 - 4)
        g.fillRect(x, y, 1.5, 1.5)
      }
    }
  }, [d])
  const sample = () =>
    api.expDiag('sample', { seconds: 5 }).then(() => { flash('采样中：匀速画圈 5 秒…'); setTimeout(load, 300) }).catch(e => flash('', e))
  return (
    <div className="space-y-2">
      <Row label="采样">
        <button className={BTN_ACC} onClick={sample}>采 5 秒（画圈）</button>
        {d?.rate_hz && <span className="text-[10px] text-text-low">回报率 ~{d.rate_hz}Hz（{d.n} 样本）</span>}
      </Row>
      <canvas ref={ref} width={340} height={170} className="rounded border border-border-soft" />
      {d?.left && (
        <div className="text-[10px] text-text-low">
          左 [{d.left.min_x},{d.left.max_x}]×[{d.left.min_y},{d.left.max_y}] 中心({d.left.center_x.toFixed(0)},{d.left.center_y.toFixed(0)})
          {'  '}右 [{d.right.min_x},{d.right.max_x}]×[{d.right.min_y},{d.right.max_y}] 中心({d.right.center_x.toFixed(0)},{d.right.center_y.toFixed(0)})
          {'  '}(青=左 黄=右)
        </div>
      )}
      <Row label="校准">
        <button className={BTN} onClick={() => api.expDiag('adccalib', { stage: 'start' }).then(() => flash('✓ 校准开始：松开摇杆别碰')).catch(e => flash('', e))}>ADC 开始</button>
        <button className={BTN} onClick={() => api.expDiag('adccalib', { stage: 'stop' }).then(() => flash('✓ 校准结束')).catch(e => flash('', e))}>结束</button>
        <span className="text-[10px] text-amber-300">报文细节待真机核（cmd240）</span>
      </Row>
      <Row label="自动校准">
        <button className={BTN} onClick={() => api.expDiag('autocal', { on: true }).then(() => flash('✓ 已开')).catch(e => flash('', e))}>开</button>
        <button className={BTN} onClick={() => api.expDiag('autocal', { on: false }).then(() => flash('已关')).catch(e => flash('', e))}>关</button>
        <span className="text-[10px] text-text-low">= 设置块 sub6（摇杆自动校准）</span>
      </Row>
      <Err e={msg} />
    </div>
  )
}
