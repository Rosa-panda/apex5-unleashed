import { useEffect, useRef, useState } from 'react'
import { Activity, BatteryCharging, BatteryFull, BatteryLow, BatteryMedium, Gamepad, Gamepad2, LayoutDashboard, LibraryBig, Lightbulb, MonitorPlay, Settings as SettingsIcon, SlidersHorizontal, TriangleAlert, Wand2, Zap } from 'lucide-react'
import { api, type EngineEvent } from './api'
import { useEngine } from './useEngine'
import { ErrorBoundary } from './ErrorBoundary'
import { DeviceGate } from './Offline'
import Overview from './pages/Overview'
import TriggerLab from './pages/TriggerLab'
import PresetLibrary from './pages/PresetLibrary'
import PadTest from './pages/PadTest'
import GameLibrary from './pages/GameLibrary'
import Macros from './pages/Macros'
import Lights from './pages/Lights'
import Screen from './pages/Screen'
import Settings from './pages/Settings'

type PageId = 'overview' | 'lab' | 'presets' | 'games' | 'macros' | 'lights' | 'screen' | 'padtest' | 'settings'

const NAV: Array<{ id: PageId; label: string; icon: typeof Activity }> = [
  { id: 'overview', label: '总览', icon: LayoutDashboard },
  { id: 'lab', label: '扳机实验室', icon: SlidersHorizontal },
  { id: 'presets', label: '预设库', icon: Gamepad2 },
  { id: 'games', label: '游戏库', icon: LibraryBig },
  { id: 'macros', label: '宏', icon: Wand2 },
  { id: 'lights', label: '灯光', icon: Lightbulb },
  { id: 'screen', label: '屏幕', icon: MonitorPlay },
  { id: 'padtest', label: '手柄测试', icon: Gamepad },
  { id: 'settings', label: '设置', icon: SettingsIcon },
]

export default function App() {
  const [page, setPage] = useState<PageId>('overview')
  const { snap, connected, events } = useEngine()
  const [panicFlash, setPanicFlash] = useState(false)
  const [toast, setToast] = useState('')
  const lastAutoRef = useRef<EngineEvent | null>(null)
  const toastTimer = useRef(0)

  const proxy = snap?.proxy
  const taken = proxy?.holder === 'external'
  const online = snap?.device.online ?? false
  const mock = snap?.device.kind === 'mock'
  const batt = snap?.device.battery

  // 适配状态推导：gripBind/triggers 的 source 是工具行为的事实记录（game:名称 / preset:名称 / vib:universal）
  const gripSrc = snap?.state.gripBind.left?.source ?? snap?.state.gripBind.right?.source ?? ''
  const trigSrc = snap?.state.triggers.left?.source ?? snap?.state.triggers.right?.source ?? ''
  const gameAdapted = gripSrc.startsWith('game:') && !gripSrc.endsWith(':novib')
    ? gripSrc.slice('game:'.length)
    : null
  const universalVib = gripSrc.startsWith('vib:universal')
  const presetApplied = trigSrc.startsWith('preset:') ? trigSrc.slice('preset:'.length) : null
  const adapted = !!(gameAdapted || universalVib || presetApplied)

  // 自动切换 toast：只认 WS 实时推送（hist 标记的历史事件在重连/开窗时重放，不弹）。
  // ⚠ 定时器必须放 ref、不能当 effect cleanup：cleanup 在 effect 每次重跑（任意其他
  // WS 事件到达）时都会执行，若在这里清了 4s 定时器又提前 return 不重排 → 弹窗
  // 永不消失（2026-09-20 用户实测「离开游戏」提示赖着不走）。
  useEffect(() => {
    const latest = [...events].reverse().find(e => e.kind === 'autoswitch' && !e.hist)
    if (!latest || latest === lastAutoRef.current) return
    lastAutoRef.current = latest
    setToast(typeof latest.detail === 'string' ? latest.detail : '')
    if (toastTimer.current) clearTimeout(toastTimer.current)
    toastTimer.current = window.setTimeout(() => setToast(''), 4000)
  }, [events])

  const doPanic = async () => {
    setPanicFlash(true)
    try {
      await api.panic()
      setToast('已复位：马达归零，双扳机恢复出厂手感')
      setTimeout(() => setToast(''), 3000)
    } catch { /* 后端事件会同步状态 */ }
    setTimeout(() => setPanicFlash(false), 800)
  }

  return (
    <div className="flex h-full">
      {/* 侧栏 */}
      <aside className="flex w-52 shrink-0 flex-col border-r border-border-soft bg-[#0d0d14]">
        <div className="flex items-center gap-2.5 px-5 py-5">
          {/* 品牌图标：与窗口/托盘同源的自绘手柄（icon.py 的 SVG 版） */}
          <svg viewBox="0 0 64 64" className="h-8 w-8 shrink-0" aria-label="Apex5 Unleashed">
            <rect x="3" y="3" width="58" height="58" rx="14" fill="#0a0a0f" />
            <rect x="13" y="23" width="38" height="18" rx="9" fill="#22d3ee" />
            <ellipse cx="19" cy="37" rx="10" ry="11" fill="#22d3ee" />
            <ellipse cx="45" cy="37" rx="10" ry="11" fill="#22d3ee" />
            <rect x="19.5" y="27" width="5" height="12" rx="1.5" fill="#0a0a0f" />
            <rect x="16" y="30.5" width="12" height="5" rx="1.5" fill="#0a0a0f" />
            <circle cx="42.5" cy="28.5" r="2.2" fill="#0a0a0f" />
            <circle cx="46.5" cy="32.5" r="2.2" fill="#0a0a0f" />
            <circle cx="42.5" cy="36.5" r="2.2" fill="#0a0a0f" />
            <circle cx="38.5" cy="32.5" r="2.2" fill="#0a0a0f" />
            <circle cx="30.5" cy="28.6" r="1.4" fill="#0a0a0f" />
            <circle cx="33.5" cy="28.6" r="1.4" fill="#0a0a0f" />
          </svg>
          <div>
            <div className="text-[13px] font-semibold tracking-wide">Apex5 Unleashed</div>
            <div className="text-[10px] text-text-low">v0.1 · 八爪鱼5 工具箱</div>
          </div>
        </div>

        <nav className="flex-1 space-y-1 px-3">
          {NAV.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setPage(id)}
              className={`flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] transition-colors ${
                page === id
                  ? 'bg-accent/12 text-accent'
                  : 'text-text-mid hover:bg-white/4 hover:text-text-hi'
              }`}
            >
              <Icon size={15} />
              {label}
            </button>
          ))}
        </nav>

        <div className="space-y-2 px-4 pb-4">
          <div className="rounded-lg border border-border-soft bg-card px-3 py-2.5 text-[11px]">
            <div className="mb-1 flex items-center gap-1.5 text-text-low">设备状态</div>
            <div className={`flex items-center gap-1.5 ${online ? 'text-ok' : 'text-err'}`}>
              <span className={`h-1.5 w-1.5 rounded-full ${online ? 'bg-ok animate-pulse' : 'bg-err'}`} />
              {online ? (mock ? 'Mock 设备' : 'Apex 5 已连接') : '手柄未连接'}
            </div>
            {online && batt && (
              <div className={`mt-1 flex items-center gap-1.5 ${
                batt.charging ? 'text-ok' : batt.level <= 1 ? 'text-err' : 'text-text-mid'}`}>
                {batt.charging ? <BatteryCharging size={11} />
                  : batt.level >= 4 ? <BatteryFull size={11} />
                  : batt.level >= 2 ? <BatteryMedium size={11} />
                  : <BatteryLow size={11} />}
                {batt.charging ? `充电中 · ${batt.level}/5` : `电量 ${batt.level}/5`}
              </div>
            )}
            {/* 适配状态：工具行为可视化——当前套用了哪个游戏适配/预设，一眼可见 */}
            {online && (adapted ? (
              <div className="mt-1 flex items-center gap-1.5 text-accent" title="自动切换已应用的适配">
                <Zap size={11} />
                <span className="truncate">
                  {gameAdapted ? `适配中：${gameAdapted}`
                    : universalVib ? '通用震动联动' : ''}
                  {presetApplied ? ` · 预设 ${presetApplied}` : ''}
                </span>
              </div>
            ) : (
              <div className="mt-1 flex items-center gap-1.5 text-text-low">
                <Zap size={11} /> 标准模式（无适配）
              </div>
            ))}
            <div className={`mt-1 flex items-center gap-1.5 ${taken && !proxy?.mild ? 'text-warn' : 'text-text-low'}`}>
              <span className={`h-1.5 w-1.5 rounded-full ${taken && !proxy?.mild ? 'bg-warn' : 'bg-ok'}`} />
              {taken
                ? proxy?.mild ? '飞智空间站初始化中' : `被接管：${proxy?.detail || '未知进程'}`
                : '代理权：本软件'}
            </div>
          </div>
          <button
            onClick={doPanic}
            className={`btn w-full justify-center btn-danger ${panicFlash ? 'border-err' : ''}`}
            title="手感的保险丝：效果卡死 / 马达乱震 / 扳机锁住时按一下——马达立刻归零、双扳机恢复出厂 Normal。平时正常玩用不着。"
          >
            <TriangleAlert size={13} /> {panicFlash ? '已复位 ✓' : '手柄复位'}
          </button>
        </div>
      </aside>

      {/* 主区 */}
      <main className="relative flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-border-soft px-6 py-3">
          <div className="flex items-center gap-2 text-[13px] text-text-mid">
            <Activity size={14} className={connected ? 'text-ok' : 'text-err'} />
            {connected ? '实时连接' : '连接断开，重连中…'}
            <span className="text-text-low">· 127.0.0.1:18765</span>
          </div>
          {taken && (
            proxy?.mild ? (
              /* ADR-023：飞智空间站 init 指纹命中 → 中性提示，不弹「被接管」警告 */
              <div className="rounded-md border border-border-soft bg-white/5 px-3 py-1 text-[12px] text-text-mid">
                飞智空间站服务初始化手柄，稍后自动收回
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <div className="rounded-md border border-warn/40 bg-warn/10 px-3 py-1 text-[12px] text-warn">
                  手柄当前由「{proxy?.detail || '未知进程'}」代理，15s 无活动自动接管回来
                </div>
                <button className="btn !py-1 text-[12px] text-warn" onClick={() => api.reclaim().catch(() => {})}>
                  立即夺回
                </button>
              </div>
            )
          )}
        </header>

          {/* 全局离线横幅：后台断了（红）/ 手柄没连（黄），让断连在任何页面都一眼可见 */}
          {!connected ? (
            <div className="flex items-center gap-2 border-b border-err/30 bg-err/10 px-6 py-1.5 text-[12px] text-err">
              <Gamepad size={13} /> 无法连接软件后台（127.0.0.1:18765），正在自动重连…
            </div>
          ) : !online && !mock ? (
            <div className="flex items-center gap-2 border-b border-warn/30 bg-warn/10 px-6 py-1.5 text-[12px] text-warn">
              <Gamepad size={13} /> 手柄未连接 —— 请检查 USB 线或重新插拔手柄；接上后设备功能自动恢复
            </div>
          ) : null}

        {/* 自动切换 toast：进入/离开游戏时全页面可见的工具行为提示 */}
        {toast && (
          <div className="pointer-events-none absolute left-1/2 top-12 z-50 -translate-x-1/2">
            <div className="flex items-center gap-2 rounded-lg border border-accent/50 bg-[#0d0d14] px-4 py-2 text-[13px] text-accent shadow-lg">
              <Zap size={13} /> {toast}
            </div>
          </div>
        )}

        <div className="min-h-0 flex-1 overflow-y-auto p-6">
          <ErrorBoundary page={page}>
            {page === 'overview' && <Overview snap={snap} events={events} onPanic={doPanic} />}
            {page === 'lab' && <TriggerLab snap={snap} />}
            {page === 'presets' && <PresetLibrary snap={snap} />}
            {page === 'games' && <GameLibrary />}
            {page === 'macros' && <Macros events={events} online={online} />}
            {page === 'lights' && <DeviceGate online={online}><Lights /></DeviceGate>}
            {page === 'screen' && <DeviceGate online={online}><Screen events={events} /></DeviceGate>}
            {page === 'padtest' && <PadTest events={events} />}
            {page === 'settings' && <Settings />}
          </ErrorBoundary>
        </div>
      </main>
    </div>
  )
}
