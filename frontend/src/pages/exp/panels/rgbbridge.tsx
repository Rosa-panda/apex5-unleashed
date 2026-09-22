// #8 Mod 灯效桥（ADR-029 F2 自 panels.tsx 逐字搬出）
import { useCallback, useEffect, useState } from 'react'
import { AlertTriangle } from 'lucide-react'
import { api } from '../../../api'
import { BTN, BTN_ACC, Err, NoDev, Row, useFlash } from '../ui'

export function RgbBridgePanel() {
  const [st, setSt] = useState<any>(null)
  const [msg, flash] = useFlash()
  const load = useCallback(() => { api.expRgb().then(setSt).catch(e => flash('', e)) }, [])
  useEffect(() => {
    load()
    const t = setInterval(load, 2000)
    return () => clearInterval(t)
  }, [load])
  if (!st) return <div className="space-y-2"><NoDev /><Err e={msg} /></div>
  const toggle = () =>
    api.expRgbSet(!st.enabled, st.port).then((r: any) => { setSt(r); flash(r.enabled ? '✓ 桥已启动' : '已停止') }).catch(e => flash('', e))
  const testColor = (rgb: number[]) =>
    api.expRgbTest(rgb).then((r: any) => { setSt(r); flash(rgb[0] ? '✓ 已发红' : rgb[1] ? '✓ 已发绿' : '✓ 已发蓝') }).catch(e => flash('', e))
  return (
    <div className="space-y-2">
      <Row label="监听">
        <button className={st.enabled ? BTN_ACC : BTN} onClick={toggle}>
          {st.enabled ? `运行中 127.0.0.1:${st.port}（点此停止）` : `已停止（点此启动 :${st.port}）`}
        </button>
        <span className="text-[10px] text-text-low">DSX 等往 7878 发的 RGB 颜色 → 翻译成手柄灯效（官方静默丢弃的部分）</span>
      </Row>
      {st.enabled && (
        <Row label="测试色">
          <button className="h-6 w-9 rounded border border-red-500/50 bg-red-600/70 text-[10px]" onClick={() => testColor([255, 0, 0])}>红</button>
          <button className="h-6 w-9 rounded border border-emerald-500/50 bg-emerald-600/70 text-[10px]" onClick={() => testColor([0, 255, 0])}>绿</button>
          <button className="h-6 w-9 rounded border border-blue-500/50 bg-blue-600/70 text-[10px]" onClick={() => testColor([0, 0, 255])}>蓝</button>
          <button className={BTN} onClick={() => testColor([0, 0, 0])}>熄灯</button>
          <span className="text-[10px] text-text-low">手柄连着工具时点一下，灯应该立即变色——这就是桥的效果</span>
        </Row>
      )}
      <Row label="游戏事件闪灯">
        <button
          className={st.flash_enabled ? BTN_ACC : BTN}
          onClick={() => api.expRgbFlash(!st.flash_enabled, [255, 0, 0]).then((r: any) => { setSt(r); flash(r.flash_enabled ? '✓ 已开启' : '已关闭') }).catch(e => flash('', e))}>
          {st.flash_enabled ? '开启中（游戏 Mod 扳机事件时闪红）' : '已关闭（点此开启）'}
        </button>
        <span className="text-[10px] text-text-low">普通游戏不会发灯色；装了 Mod 的游戏（Mod 管家）事件流经过工具时灯闪一下</span>
      </Row>
      {st.stats?.note && <div className="text-[11px] text-amber-300"><AlertTriangle size={12} className="inline" /> {st.stats.note}</div>}
      <div className="text-[10px] text-text-low">
        收包 {st.stats?.packets ?? 0} ｜ 应用 {st.stats?.applied ?? 0}（限频 ≥1s，同色不重写）｜ 未识别 {st.stats?.unknown ?? 0}
        {st.stats?.last_rgb && ` ｜ 最近 RGB(${st.stats.last_rgb.join(',')})`}
        {st.stats?.last_error && ` ｜ 错误: ${st.stats.last_error}`}
      </div>
      <Err e={msg} />
    </div>
  )
}
