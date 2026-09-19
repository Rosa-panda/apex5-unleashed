// 屏幕页（ADR-018 R4 二期）：GIF/图片 → LVGL 帧打包 → 串口 OTA 写入
// 红线：烧写为固件级操作，UI 两步确认 + 预计耗时明示；离线自检全绿是前置条件
import { useEffect, useRef, useState } from 'react'
import { MonitorPlay, Upload, TriangleAlert } from 'lucide-react'
import { api } from '../api'
import type { EngineEvent } from '../api'

type ConvInfo = { frames: number; interval_ms: number; total_frames: number; truncated: boolean; seconds: number }

export default function Screen({ events }: { events: EngineEvent[] }) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [name, setName] = useState('')
  const [info, setInfo] = useState<ConvInfo | null>(null)
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)
  const [armed, setArmed] = useState(false)          // 第一步确认
  const [flashing, setFlashing] = useState(false)
  const [target, setTarget] = useState(30)
  const [file, setFile] = useState<File | null>(null)
  const [flags, setFlags] = useState<{ animation_on: boolean; status_bar: boolean } | null>(null)

  const refreshFlags = () => api.screenFlags().then(r => { if (r.ok) setFlags(r) }).catch(() => {})
  useEffect(() => { refreshFlags() }, [])

  const toggleAnimation = async () => {
    if (!flags) return
    setMsg('切换中…')
    try {
      const r = await api.screenAnimation(!flags.animation_on)
      if (r.ok) setFlags(r)
      setMsg(r.animation_on === !flags.animation_on ? '' : '⚠ 设备回读与预期不符')
    } catch (e) { setMsg(`✗ ${(e as Error).message}`) }
  }
  const toggleStatusBar = async () => {
    if (!flags) return
    setMsg('切换中…')
    try {
      const r = await api.screenStatusBar(!flags.status_bar)
      if (r.ok) setFlags(r)
      setMsg('')
    } catch (e) { setMsg(`✗ ${(e as Error).message}`) }
  }

  const screenEvents = events.filter(e => e.kind === 'screen')
  const last = screenEvents[screenEvents.length - 1]
  const progress = last && last.stage === 'flash' ? `${last.done}/${last.total}` : ''

  const pick = () => fileRef.current?.click()

  const convert = async (f: File, tgt: number) => {
    setBusy(true); setMsg('解析中…'); setInfo(null); setArmed(false)
    try {
      const buf = await f.arrayBuffer()
      let bin = ''
      const bytes = new Uint8Array(buf)
      for (let i = 0; i < bytes.length; i += 0x8000)
        bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000))
      const r = await api.screenConvert(btoa(bin), f.name, 'fill', tgt)
      setInfo(r)
      setName(f.name)
      setMsg('')
    } catch (e) { setMsg(`✗ ${(e as Error).message}`) }
    setBusy(false)
  }

  const onFile = async (f: File) => {
    setFile(f)
    await convert(f, target)
  }

  const flash = async () => {
    if (!armed) { setArmed(true); return }
    setFlashing(true); setMsg('烧写中，请勿断开手柄、勿关机…')
    try {
      const r = await api.screenFlash(true)
      setMsg(`已下发（${r.frames} 帧，预计 ${Math.round(r.seconds / 60)} 分钟）——等待设备自重启`)
    } catch (e) { setMsg(`✗ ${(e as Error).message}`) }
    setFlashing(false); setArmed(false)
  }

  return (
    <div className="max-w-3xl space-y-4">
      <div className="card p-4">
        <div className="mb-3 flex items-center gap-2 text-[14px] font-medium">
          <MonitorPlay size={15} className="text-accent" /> 屏幕自定义动画
        </div>

        <input ref={fileRef} type="file" accept="image/gif,image/*" className="hidden"
          onChange={e => { const f = e.target.files?.[0]; if (f) onFile(f) }} />
        <button className="btn" disabled={busy || flashing} onClick={pick}>
          <Upload size={13} /> 选择 GIF / 图片
        </button>
        {name && <span className="ml-2 text-[12px] text-text-mid">{name}</span>}

        <div className="mt-4 max-w-xs text-[12px] text-text-mid">
          抽帧目标 <span className="font-mono text-accent">{target} 帧</span>
          {info && info.total_frames > info.frames && (
            <span className="ml-1 text-text-low">（原 {info.total_frames} 帧）</span>
          )}
          <input type="range" min={1} max={255} value={target}
            onChange={e => setTarget(+e.target.value)}
            onMouseUp={() => file && convert(file, target)}
            onTouchEnd={() => file && convert(file, target)}
            className="mt-1 w-full accent-[#22d3ee]" />
          <div className="text-[11px] text-text-low">
            烧写约 3 秒/帧（真机实测），高帧率 GIF 等距抽帧保持原速，观感几乎无差
          </div>
        </div>

        {info && (
          <div className="mt-4 rounded-lg border border-border-soft bg-[#0d0d14] p-3 text-[12px] text-text-mid">
            <div className="grid grid-cols-2 gap-y-1 font-mono">
              <span>帧数</span><span className="text-text-hi">{info.frames} / 255{info.total_frames > info.frames ? `（原 ${info.total_frames}）` : ''}</span>
              <span>帧间隔</span><span className="text-text-hi">{info.interval_ms} ms</span>
              <span>预计烧写耗时</span><span className="text-warn">约 {Math.floor(info.seconds / 60)} 分 {info.seconds % 60} 秒</span>
            </div>
            {info.truncated && <div className="mt-2 text-warn">⚠ 帧数超上限，已截断到 255 帧</div>}
            <div className="mt-2 text-[11px] text-text-low">
              烧写走固件升级通道：手柄会切模式 → 串口写入 → 自动重启（重启约 15 秒，期间勿断电）。
            </div>
          </div>
        )}

        {info && (
          <div className="mt-4 flex items-center gap-2">
            <button className={`btn ${armed ? 'btn-danger' : 'btn-primary'}`} disabled={busy || flashing} onClick={flash}>
              <TriangleAlert size={13} /> {armed ? '再次点击确认烧写' : '写入屏幕'}
            </button>
            {armed && (
              <button className="btn" onClick={() => setArmed(false)}>取消</button>
            )}
            {progress && <span className="font-mono text-[12px] text-accent">{progress} 包</span>}
            {msg && <span className="text-[12px] text-text-mid">{msg}</span>}
          </div>
        )}
        {!info && msg && <span className="ml-3 text-[12px] text-text-mid">{msg}</span>}
      </div>

      {/* 动画开关（cmd 19/9、19/8，官方同款功能） */}
      <div className="card p-4">
        <div className="mb-3 text-[13px] font-medium">动画显示</div>
        <div className="flex flex-wrap gap-2">
          <button className={`btn ${flags?.animation_on ? 'btn-primary' : ''}`} disabled={!flags}
            onClick={toggleAnimation}>
            {flags ? (flags.animation_on ? '动画：开启中' : '动画：已关闭') : '动画状态读取中…'}
          </button>
          <button className={`btn ${flags?.status_bar ? 'btn-primary' : ''}`} disabled={!flags}
            onClick={toggleStatusBar}>
            {flags ? (flags.status_bar ? '状态栏：常亮' : '状态栏：默认') : '…'}
          </button>
        </div>
        <div className="mt-2 text-[11px] text-text-low">
          关闭动画后面板熄灭，按 Logo 键可临时点亮状态栏（官方「息屏显示」位，语义按真机实测）。
        </div>
      </div>

      <div className="card p-4 text-[11px] leading-relaxed text-text-low">
        <div className="mb-1 text-[12px] text-text-mid">安全说明（ADR-018 R4）</div>
        · 帧格式已用官方出厂动画逐字节验证；写入地址由芯片读回的图区基址限定，程序固件区不可达
        · 写入过程每包等待设备回执，任一步失败立即中止
        · 出厂动画可用官方空间站随时恢复
      </div>
    </div>
  )
}
