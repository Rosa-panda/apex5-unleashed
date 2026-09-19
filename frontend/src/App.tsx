import { useState } from 'react'
import { Activity, BatteryCharging, BatteryFull, BatteryLow, BatteryMedium, Gamepad, Gamepad2, LayoutDashboard, LibraryBig, Lightbulb, MonitorPlay, Settings as SettingsIcon, SlidersHorizontal, TriangleAlert, Wand2, Zap } from 'lucide-react'
import { api } from './api'
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

  const proxy = snap?.proxy
  const taken = proxy?.holder === 'external'
  const online = snap?.device.online ?? false
  const mock = snap?.device.kind === 'mock'
  const batt = snap?.device.battery

  const doPanic = async () => {
    setPanicFlash(true)
    try { await api.panic() } catch { /* 后端事件会同步状态 */ }
    setTimeout(() => setPanicFlash(false), 800)
  }

  return (
    <div className="flex h-full">
      {/* 侧栏 */}
      <aside className="flex w-52 shrink-0 flex-col border-r border-border-soft bg-[#0d0d14]">
        <div className="flex items-center gap-2.5 px-5 py-5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent/15 text-accent">
            <Zap size={17} strokeWidth={2.2} />
          </div>
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
            <div className={`mt-1 flex items-center gap-1.5 ${taken ? 'text-warn' : 'text-text-low'}`}>
              <span className={`h-1.5 w-1.5 rounded-full ${taken ? 'bg-warn' : 'bg-ok'}`} />
              {taken ? `被接管：${proxy?.detail || '未知进程'}` : '代理权：本软件'}
            </div>
          </div>
          <button
            onClick={doPanic}
            className={`btn w-full justify-center btn-danger ${panicFlash ? 'border-err' : ''}`}
            title="马达归零 + 扳机复位 Normal"
          >
            <TriangleAlert size={13} /> 紧急复位
          </button>
        </div>
      </aside>

      {/* 主区 */}
      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-border-soft px-6 py-3">
          <div className="flex items-center gap-2 text-[13px] text-text-mid">
            <Activity size={14} className={connected ? 'text-ok' : 'text-err'} />
            {connected ? '实时连接' : '连接断开，重连中…'}
            <span className="text-text-low">· 127.0.0.1:18765</span>
          </div>
          {taken && (
            <div className="flex items-center gap-2">
              <div className="rounded-md border border-warn/40 bg-warn/10 px-3 py-1 text-[12px] text-warn">
                手柄当前由「{proxy?.detail || '未知进程'}」代理，15s 无活动自动接管回来
              </div>
              <button className="btn !py-1 text-[12px] text-warn" onClick={() => api.reclaim().catch(() => {})}>
                立即夺回
              </button>
            </div>
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

        <div className="min-h-0 flex-1 overflow-y-auto p-6">
          <ErrorBoundary page={page}>
            {page === 'overview' && <Overview snap={snap} events={events} onPanic={doPanic} />}
            {page === 'lab' && <TriggerLab snap={snap} />}
            {page === 'presets' && <PresetLibrary />}
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
