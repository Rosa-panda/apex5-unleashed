// 滑杆填充轨道辅助：range 轨道的已填充段靠 --fill CSS 变量驱动（Chromium 无
// ::-webkit-range-progress，纯 CSS 算不出百分比）。用法：
//   <input type="range" min={0} max={255} value={v} style={fill(v, 0, 255)} ... />
// 对 NaN / max≤min 做了防御：非法值回退 0%（灰轨），不会让轨道整体消失。
import type { CSSProperties } from 'react'

export const fill = (v: number, min: number, max: number): CSSProperties => {
  const span = max - min
  const pct = span > 0 ? ((v - min) / span) * 100 : 0
  const safe = Number.isFinite(pct) ? Math.max(0, Math.min(100, pct)) : 0
  return { '--fill': `${safe}%` } as CSSProperties
}
