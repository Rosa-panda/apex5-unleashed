// 体感中心（ADR-028）：体感四件套的独立顶级栏目 + 总闸。
// 总闸 = 模拟器桥(DSU) + 陀螺瞄准 + 体感 UI 推送 的联动编排（后端 /api/motion/master），
// 状态持久化在 %APPDATA%\Apex5Unleashed\motion_hub.json——上次开着，这次启动就还是开着。
// ⚠ 0xEF 位图流是基础设施恒开（拓展键直读/宏录制也吃它），总闸不碰——
// 2026-09-22 实锤：总闸连带关流 → 手柄测试页拓展键全瞎。
import { useCallback, useState } from 'react'
import { Orbit } from 'lucide-react'
import { api } from '../api'
import { usePolling } from '../hooks/usePolling'
import { DsuPanel, GyroFwPanel, GyroPanel, MazePanel } from './exp/panels'

function Chip({ on, children }: { on: boolean; children: React.ReactNode }) {
  return (
    <span className={`rounded-md border px-2 py-0.5 text-[11px] ${on
      ? 'border-accent/40 bg-accent/10 text-accent'
      : 'border-border-soft bg-white/5 text-text-low'}`}>
      {on ? '● ' : '○ '}{children}
    </span>
  )
}

function Section({ title, desc, children }: { title: string; desc: string; children: React.ReactNode }) {
  return (
    <div className="card space-y-2 p-4">
      <div>
        <div className="text-[13px] font-semibold text-text-hi">{title}</div>
        <p className="mt-0.5 text-[11px] leading-relaxed text-text-mid">{desc}</p>
      </div>
      <div className="rounded-md border border-border-soft bg-black/20 p-3">{children}</div>
    </div>
  )
}

export default function Motion() {
  const [st, setSt] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const load = useCallback(() => {
    api.motionMaster().then(setSt).catch(() => setErr('✗ 状态加载失败'))
  }, [])
  // 状态定时同步：后台/别处改了开关（甚至手柄休眠导致流断）这里 2s 内可见
  usePolling(load, 2000, [load])

  const toggle = () => {
    const on = !st?.master
    setBusy(true)
    // 15s 兜底：post 自带 6s 超时+一次重试（最坏 ~12.4s），这里保证 busy 最终一定释放
    const timer = window.setTimeout(() => setBusy(false), 15000)
    api.motionMasterSet(on)
      .then(() => { setErr(''); load() })
      .catch(() => setErr('✗ 切换失败（后台未响应或手柄未连接，2 秒后状态自动刷新为准）'))
      .finally(() => { window.clearTimeout(timer); setBusy(false) })
  }

  const master = !!st?.master
  return (
    <div className="mx-auto max-w-4xl space-y-5">
      {/* 总闸大卡：开/关状态必须一眼可辨（大字 + 整卡变色 + 徽标），切换后立即可见 */}
      <div className={`card p-5 ${master ? 'border-accent/50 bg-accent/8' : 'opacity-90'}`}>
        <div className="flex items-center gap-3">
          <div className={`rounded-lg border p-2 ${master ? 'border-accent/50 bg-accent/10 text-accent' : 'border-border-soft bg-white/5 text-text-low'}`}>
            <Orbit size={20} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-[15px] font-semibold text-text-hi">体感总闸</span>
              {/* 状态大字：不靠按钮文字判断开没开 */}
              <span className={`rounded-md px-2 py-0.5 text-[12px] font-bold ${master ? 'bg-accent/15 text-accent' : 'bg-white/5 text-text-low'}`}>
                {master ? '● 已开启' : '○ 已关闭'}
              </span>
            </div>
            <div className="text-[11px] text-text-low">
              模拟器桥 + 陀螺瞄准一键联动；状态自动保存，重开软件不用再开一次
            </div>
          </div>
          <button
            onClick={toggle}
            disabled={busy}
            className={`btn ml-auto justify-center ${master ? 'btn-danger' : 'btn-primary'}`}
            style={{ minWidth: 96 }}>
            {busy ? '切换中…' : master ? '关闭体感' : '开启体感'}
          </button>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Chip on={!!st?.raw}>0xEF 位图流（按需）</Chip>
          <Chip on={!!st?.dsu?.enabled}>
            模拟器桥{st?.dsu?.enabled ? ` :${st.dsu.port ?? 26760}` : ''}
          </Chip>
          <Chip on={!!st?.gyro?.enabled}>陀螺瞄准</Chip>
          {err && <span className="text-[11px] text-err">{err}</span>}
        </div>
        <p className="mt-2 text-[11px] leading-relaxed text-text-low">
          开闸 = 常备模拟器桥（Yuzu/Cemu/Dolphin/PCSX2 直连 127.0.0.1:{st?.dsu?.port ?? 26760}）+ 体感数据流通，
          陀螺瞄准尊重你上次的选择、不自动开。关闸 = 桥和瞄准全关、试玩场停止响应；
          0xEF 位图流按需供给——只有拓展键监听（测试页）或宏录制在用时才开，没人用自动收流，手柄可正常休眠。
        </p>
        <p className="mt-1 text-[11px] leading-relaxed text-text-low">
          注意：总闸只管<b className="text-text-mid">软件层</b>（桥/瞄准/试玩场）。手柄固件里的陀螺→摇杆映射写在手柄自身档案里，
          关软件也生效——总闸没开摇杆还在自己动，去下方面板「固件层陀螺映射」关。
        </p>
      </div>

      <Section
        title="试玩场 · 弹珠迷宫"
        desc="手柄当板子，倾斜滚弹珠到终点。matter.js 物理（240Hz 子步）+ 撞墙音效/手柄震动——练手感、验延迟，先把这里玩顺再进游戏。总闸关闭时无体感输入。">
        <MazePanel />
      </Section>

      <Section
        title="模拟器桥（DSU/Cemuhook UDP）"
        desc="把 0xEF 运动流翻译成标准 DSU 协议，喂给 Yuzu / Cemu / Dolphin / PCSX2。模拟器里「控制器 → Motion Source → UDP」填 127.0.0.1 即可。">
        <DsuPanel />
      </Section>

      <Section
        title="陀螺瞄准（软件层 · 陀螺转鼠标）"
        desc="不用改游戏：陀螺直接转系统鼠标。受总闸节制——总闸关闭时这里开不起来。">
        <GyroPanel />
      </Section>

      <Section
        title="固件层陀螺映射（陀螺转摇杆）"
        desc="写进手柄固件的陀螺→右摇杆映射，关软件也生效。适合原生不支持陀螺的主机/游戏。">
        <GyroFwPanel />
      </Section>
    </div>
  )
}
