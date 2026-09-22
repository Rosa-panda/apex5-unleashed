// 屏幕卡（ADR-018 R4 二期，2026-09-22 并入总览）：GIF/图片 → LVGL 帧打包 → 串口 OTA 写入
// 红线：烧写为固件级操作，UI 两步确认 + 预计耗时明示
import { useEffect, useRef, useState } from 'react'
import { MonitorPlay, Upload, TriangleAlert } from 'lucide-react'
import { api } from '../api'
import type { EngineEvent } from '../api'

type ConvInfo = { frames: number; interval_ms: number; total_frames: number; truncated: boolean; seconds: number }

/** 总览页「手柄屏幕」卡：显示开关 + 自定义动画烧写（嵌入用，offline 时整体降级） */
export default function ScreenCard({ events, online }: { events: EngineEvent[]; online: boolean }) {
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
  useEffect(() => { if (online) refreshFlags() }, [online])

  const toggleAnimation = async () => {
    if (!flags) return
    try {
      const r = await api.screenAnimation(!flags.animation_on)
      if (r.ok) setFlags(r)
    } catch (e) { setMsg(`✗ ${(e as Error).message}`) }
  }
  const toggleStatusBar = async () => {
    if (!flags) return
    try {
      const r = await api.screenStatusBar(!flags.status_bar)
      if (r.ok) setFlags(r)
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
    <div className="card p-5">
      <div className="mb-3 flex items-center gap-2 text-[12px] text-text-mid">
        <MonitorPlay size={14} className="text-accent" /> 手柄屏幕
      </div>

      {!online ? (
        <div className="text-[12px] text-text-low">手柄未连接——屏幕功能需要真机在线。</div>
      ) : (
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-[230px_1fr]">
          {/* 左：显示开关 */}
          <div className="space-y-2">
            <button className={`btn w-full justify-center !py-1.5 text-[12px] ${flags?.animation_on ? 'btn-primary' : ''}`}
              disabled={!flags || flashing} onClick={toggleAnimation}
              title="关闭后面板熄灭，按 Logo 键可临时点亮状态栏">
              动画显示：{flags ? (flags.animation_on ? '开' : '关') : '读取中…'}
            </button>
            <button className={`btn w-full justify-center !py-1.5 text-[12px] ${flags?.status_bar ? 'btn-primary' : ''}`}
              disabled={!flags || flashing} onClick={toggleStatusBar}>
              状态栏：{flags ? (flags.status_bar ? '常亮' : '默认') : '…'}
            </button>
            <div className="text-[11px] leading-relaxed text-text-low">
              烧写走固件升级通道：切模式 → 串口写入 → 自动重启（约 15 秒，期间勿断电）。出厂动画可用官方空间站随时恢复。
            </div>
          </div>

          {/* 右：自定义动画 */}
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <input ref={fileRef} type="file" accept="image/gif,image/*" className="hidden"
                onChange={e => { const f = e.target.files?.[0]; if (f) onFile(f) }} />
              <button className="btn !py-1.5 text-[12px]" disabled={busy || flashing} onClick={pick}>
                <Upload size={13} /> 选择 GIF / 图片
              </button>
              {name && <span className="truncate text-[12px] text-text-mid">{name}</span>}
              <div className="ml-auto flex items-center gap-2 text-[11px] text-text-low">
                抽帧目标
                <input type="range" min={1} max={255} value={target} className="w-28 accent-[#22d3ee]"
                  onChange={e => setTarget(+e.target.value)}
                  onMouseUp={() => file && convert(file, target)}
                  onTouchEnd={() => file && convert(file, target)} />
                <span className="font-mono text-accent">{target} 帧</span>
              </div>
            </div>

            {info && (
              <div className="rounded-lg border border-border-soft bg-[#0d0d14] p-3">
                <div className="grid grid-cols-2 gap-y-1 font-mono text-[12px] text-text-mid md:grid-cols-4">
                  <span>帧数 <span className="text-text-hi">{info.frames}/255</span>{info.total_frames > info.frames ? `（原 ${info.total_frames}）` : ''}</span>
                  <span>帧间隔 <span className="text-text-hi">{info.interval_ms} ms</span></span>
                  <span>预计 <span className="text-warn">{Math.floor(info.seconds / 60)} 分 {info.seconds % 60} 秒</span></span>
                  <span className="col-span-2 md:col-span-1">
                    <button className={`btn !py-1 text-[12px] ${armed ? 'btn-danger' : 'btn-primary'}`} disabled={busy || flashing} onClick={flash}>
                      <TriangleAlert size={12} /> {armed ? '再次点击确认烧写' : '写入屏幕'}
                    </button>
                  </span>
                </div>
                {info.truncated && <div className="mt-2 text-warn">⚠ 帧数超上限，已截断到 255 帧</div>}
                {armed && (
                  <button className="mt-2 text-[11px] text-text-low underline" onClick={() => setArmed(false)}>取消烧写</button>
                )}
                {(progress || msg) && (
                  <div className="mt-2 flex items-center gap-3 text-[12px] text-text-mid">
                    {progress && <span className="font-mono text-accent">{progress} 包</span>}
                    {msg && <span>{msg}</span>}
                  </div>
                )}
              </div>
            )}
            {!info && msg && <span className="text-[12px] text-text-mid">{msg}</span>}
          </div>
        </div>
      )}
    </div>
  )
}
