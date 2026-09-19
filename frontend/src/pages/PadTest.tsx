// 手柄测试页：Gamepad API 实时读标准输入接口（摇杆/按键/扳机模拟量）
// 震动测试走自家 vendor 通道 (/api/rumble)
// 特殊键（背键/扩展肩键）：不在标准接口里，吃后端 hidkey(键盘接口)/rawhid(vendor非协议帧) 事件
import { useEffect, useMemo, useState } from 'react'
import { Circle, Gamepad, Keyboard, Radio, Vibrate, Zap } from 'lucide-react'
import { api, type EngineEvent } from '../api'

interface PadSnap {
  id: string
  axes: number[]
  buttons: { pressed: boolean; value: number }[]
}

function useGamepad() {
  const [pad, setPad] = useState<PadSnap | null>(null)
  useEffect(() => {
    let raf = 0
    const tick = () => {
      const raw = Array.from(navigator.getGamepads?.() ?? []).find((g) => g)
      if (raw) {
        setPad({
          id: raw.id,
          axes: [...raw.axes],
          buttons: raw.buttons.map((b) => ({ pressed: b.pressed, value: b.value })),
        })
      } else {
        setPad(null)
      }
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [])
  return pad
}

function Stick({ snap, base }: { snap: PadSnap | null; base: number }) {
  const x = snap?.axes[base] ?? 0
  const y = snap?.axes[base + 1] ?? 0
  const press = snap?.buttons[base === 0 ? 10 : 11]?.pressed ?? false
  return (
    <div className="flex flex-col items-center gap-2">
      <div className="relative h-40 w-40 rounded-full border-2 border-border-soft bg-[#0d0d14]">
        <div className="absolute inset-0 m-auto h-px w-full bg-border-soft" />
        <div className="absolute inset-0 m-auto h-full w-px bg-border-soft" />
        <div
          className={`absolute h-4 w-4 rounded-full transition-transform duration-[16ms] ${press ? 'bg-accent ring-4 ring-accent/30' : 'bg-accent/80'}`}
          style={{ left: '50%', top: '50%', transform: `translate(-50%,-50%) translate(${x * 70}px, ${y * 70}px)` }}
        />
      </div>
      <div className="font-mono text-[11px] tabular-nums text-text-low">
        {x.toFixed(2)}, {y.toFixed(2)} {press ? '· L3' : ''}
      </div>
    </div>
  )
}

const FACE = [
  { i: 0, label: 'A / 交叉', pos: 'bottom-0 left-1/2 -translate-x-1/2' },
  { i: 1, label: 'B / 圆圈', pos: 'right-0 top-1/2 -translate-y-1/2' },
  { i: 2, label: 'X / 方块', pos: 'left-0 top-1/2 -translate-y-1/2' },
  { i: 3, label: 'Y / 三角', pos: 'top-0 left-1/2 -translate-x-1/2' },
]
const DPAD = [
  { i: 12, label: '↑', pos: 'top-0 left-1/2 -translate-x-1/2' },
  { i: 13, label: '↓', pos: 'bottom-0 left-1/2 -translate-x-1/2' },
  { i: 14, label: '←', pos: 'left-0 top-1/2 -translate-y-1/2' },
  { i: 15, label: '→', pos: 'right-0 top-1/2 -translate-y-1/2' },
]
const SMALL = [
  { i: 4, label: 'LB' }, { i: 5, label: 'RB' }, { i: 6, label: 'LT' }, { i: 7, label: 'RT' },
  { i: 8, label: '视图' }, { i: 9, label: '菜单' }, { i: 16, label: 'LOGO' },
]

// 拓展键六颗（ADR-019）：官方命名+物理位置；id=0xEF 键位图事件里的键名
const EXT_CHIP = [
  { key: 'M1', id: 'm1', pos: '背右上' },
  { key: 'M2', id: 'm2', pos: '背左上' },
  { key: 'M3', id: 'm3', pos: '背右下' },
  { key: 'M4', id: 'm4', pos: '背左下' },
  { key: 'LM', id: 'lm', pos: '头左·M5' },
  { key: 'RM', id: 'rm', pos: '头右·M6' },
]

export default function PadTest({ events }: { events: EngineEvent[] }) {
  const pad = useGamepad()
  const btn = (i: number) => pad?.buttons[i]
  const pressed = (i: number) => btn(i)?.pressed

  // 特殊键：后端两条监听通道的最新事件
  const hidkeys = useMemo(() => events.filter(e => e.kind === 'hidkey').slice(-8).reverse(), [events])
  const rawhids = useMemo(() => events.filter(e => e.kind === 'rawhid').slice(-8).reverse(), [events])
  const lastKeys: string[] = (hidkeys[0]?.keys as string[]) ?? []

  // 拓展键（ADR-019）：0xEF 物理键位图直读——映射前的真实按压，与老按键天然区分
  const extKeysNow = useMemo(
    () => new Set((events.filter(e => e.kind === 'extkey').slice(-1)[0]?.keys as string[]) ?? []),
    [events])
  const [keyMap, setKeyMap] = useState<Array<{ name: string; target_name: string }> | null>(null)
  useEffect(() => { api.extKeys().then(m => { if (m.ok) setKeyMap(m.keys) }).catch(() => {}) }, [])

  // 受控键位校准（ADR-016）：跟随 attrib 事件展示引导浮层
  const [attrib, setAttrib] = useState<{ phase: string; key?: string; mapping?: Record<string, string>; missing?: string[] } | null>(null)
  const attribEvts = useMemo(() => events.filter(e => e.kind === 'attrib'), [events])
  useEffect(() => {
    const e = attribEvts[attribEvts.length - 1]
    if (e) setAttrib({ phase: e.phase as string, key: e.key as string | undefined, mapping: e.mapping as Record<string, string> | undefined, missing: e.missing as string[] | undefined })
  }, [attribEvts.length])  // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      {!pad && (
        <div className="card flex items-center gap-3 p-5 text-[13px] text-text-mid">
          <Gamepad size={18} className="text-text-low" />
          未检测到游戏控制器——手柄开机/重插一次（此页读的是 Windows 标准输入接口，与 vendor 协议通道相互独立）
        </div>
      )}
      {pad && (
        <div className="card px-5 py-3 font-mono text-[11px] text-text-low">
          已连接：{pad.id}
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        {/* 摇杆 */}
        <div className="card flex flex-col items-center gap-5 p-5">
          <div className="self-start text-[12px] text-text-mid">摇杆</div>
          <Stick snap={pad} base={0} />
          <Stick snap={pad} base={2} />
        </div>

        {/* 按键 */}
        <div className="card p-5">
          <div className="mb-4 text-[12px] text-text-mid">按键</div>
          <div className="flex items-center gap-6">
            <div className="relative h-28 w-28 shrink-0">
              {/* 十字键 */}
              {DPAD.map(({ i, label, pos }) => (
                <div key={i} className={`absolute h-9 w-9 ${pos} flex items-center justify-center rounded-md border text-[13px] transition-colors ${
                  pressed(i) ? 'border-accent bg-accent/20 text-accent' : 'border-border-soft bg-[#161622] text-text-low'
                }`}>{label}</div>
              ))}
            </div>
            <div className="relative h-28 w-28 shrink-0">
              {/* 功能键 */}
              {FACE.map(({ i, label, pos }) => (
                <div key={i} className={`absolute h-9 w-9 ${pos} flex items-center justify-center rounded-full border text-[11px] transition-colors ${
                  pressed(i) ? 'border-accent bg-accent/20 text-accent' : 'border-border-soft bg-[#161622] text-text-low'
                }`} title={label}>{label[0]}</div>
              ))}
            </div>
          </div>
          <div className="mt-5 flex flex-wrap gap-2">
            {SMALL.map(({ i, label }) => (
              <span key={i} className={`tag ${pressed(i) ? 'border-accent/60 !text-accent' : ''}`}>
                {label}{i === 6 || i === 7 ? ` ${(btn(i)?.value ?? 0).toFixed(2)}` : ''}
              </span>
            ))}
          </div>
        </div>

        {/* 扳机行程 + 震动 */}
        <div className="card flex flex-col p-5">
          <div className="mb-4 text-[12px] text-text-mid">扳机模拟行程</div>
          {(['LT', 'RT'] as const).map((label, k) => {
            const v = btn(6 + k)?.value ?? 0
            return (
              <div key={label} className="mb-4">
                <div className="mb-1 flex justify-between text-[12px]">
                  <span className="text-text-mid">{label}</span>
                  <span className="tabular-nums text-accent">{(v * 100).toFixed(0)}%</span>
                </div>
                <div className="h-5 overflow-hidden rounded-md bg-[#0d0d14]">
                  <div className="h-full bg-gradient-to-r from-accent-dim to-accent transition-[width] duration-[16ms]"
                    style={{ width: `${v * 100}%` }} />
                </div>
              </div>
            )
          })}
          <div className="mt-auto space-y-2 border-t border-border-soft pt-4">
            <div className="text-[11px] leading-relaxed text-text-low">
              物理行程 ≠ 模拟值：如果拖满行程数值到不了 1.0，说明手柄行程标定有问题，来这里验证。
            </div>
            <div className="flex gap-2">
              <button className="btn flex-1 justify-center" onClick={() => api.rumble(200, 200, 0.3).catch(() => {})}>
                <Vibrate size={13} /> 双震 0.3s
              </button>
              <button className="btn flex-1 justify-center" onClick={() => api.sine(2, 4, 220).catch(() => {})}>
                <Circle size={13} /> 正弦 2s
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* 拓展键（ADR-019）：直读 0xEF 物理键位图——映射前的真实按压，与老按键天然区分 */}
      <div className="card p-5">
        <div className="mb-4 flex items-center gap-2 text-[12px] text-text-mid">
          <Zap size={14} className="text-accent" /> 拓展键（LM / RM / M1-M4）
          <span className="text-text-low">· 直读固件物理键位图（0xEF 帧），与老按键天然区分</span>
        </div>
        <div className="flex flex-wrap gap-3">
          {EXT_CHIP.map(({ key, id, pos }) => {
            const on = extKeysNow.has(id)
            return (
              <div key={key}
                className={`flex h-16 w-16 flex-col items-center justify-center rounded-xl border-2 transition-all ${
                  on ? 'border-accent bg-accent/20 text-accent shadow-[0_0_16px_rgba(34,211,238,.35)]'
                    : 'border-border-soft bg-[#161622] text-text-mid'}`}>
                <span className="font-mono text-[13px]">{key}</span>
                <span className="text-[10px] text-text-low">{pos}</span>
              </div>
            )
          })}
          <div className="self-center max-w-xs text-[11px] leading-relaxed text-text-low">
            六键已还原透传（游戏内零占用，不触发任何老键位）。这里亮灯 = 物理按压实时直读，
            和老按键各走各的信号。宏功能（下一步）直接以此作触发源。
          </div>
        </div>
        {keyMap && (
          <div className="mt-3 font-mono text-[11px] text-text-low">
            当前固件映射：{keyMap.map(k => `${k.name.toUpperCase()}→${k.target_name}`).join('  ')}
          </div>
        )}
      </div>

      {/* 特殊键监听（宏的前置侦察） */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div className="card p-5">
          <div className="mb-3 flex items-center gap-2 text-[12px] text-text-mid">
            <Keyboard size={14} className="text-accent" /> 键盘接口（背键常见通道）
          </div>
          <div className="mb-3 flex min-h-8 flex-wrap gap-1.5">
            {lastKeys.length
              ? lastKeys.map(k => <span key={k} className="tag border-accent/50 !text-accent">{k}</span>)
              : <span className="text-[12px] text-text-low">按下背键 / 扩展键试试…</span>}
          </div>
          <div className="space-y-0.5 font-mono text-[11px] text-text-low">
            {hidkeys.map((e, i) => (
              <div key={i} className="truncate">{e.ts}  {(e.keys as string[])?.join('+') || '—'}  <span className="text-text-low/60">{e.raw as string}</span></div>
            ))}
          </div>
        </div>
        <div className="card p-5">
          <div className="mb-3 flex items-center gap-2 text-[12px] text-text-mid">
            <Radio size={14} className="text-accent" /> vendor 接口非协议帧
          </div>
          <div className="space-y-0.5 font-mono text-[11px] text-text-low">
            {rawhids.length
              ? rawhids.map((e, i) => <div key={i} className="truncate">{e.ts}  {e.hex as string}</div>)
              : <span className="text-[12px]">暂无原始帧——若按键时这里跳动，说明该键走 vendor 协议</span>}
          </div>
        </div>
      </div>

      <div className="text-center text-[11px] text-text-low">
        本页输入走 Windows 标准游戏控制器接口（60fps 实时），震动测试走 vendor 协议通道——两条通道都通，说明手柄双接口健康。
        特殊键确认编码后即可做按键宏（v0.2）。
      </div>

      {/* 校准引导浮层 */}
      {attrib && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm">
          <div className="card w-[420px] p-8 text-center">
            {attrib.phase === 'prompt' && (
              <>
                <div className="mb-2 text-[12px] text-text-mid">准备——下一步请按住</div>
                <div className="font-mono text-6xl font-bold text-accent">{attrib.key}</div>
              </>
            )}
            {attrib.phase === 'window' && (
              <>
                <div className="mb-2 text-[12px] text-text-mid">现在按住不放</div>
                <div className="font-mono text-6xl font-bold text-accent shadow-[0_0_32px_rgba(34,211,238,.5)]">{attrib.key}</div>
                <div className="mt-4 text-[12px] text-text-low">持续按住并松开几次（5 秒采集窗口）…</div>
              </>
            )}
            {(attrib.phase === 'done' || attrib.phase === 'error') && (
              <>
                <div className="mb-3 text-[13px] text-text-mid">
                  {attrib.phase === 'done' ? '校准完成' : '校准出错'}
                </div>
                {attrib.phase === 'done' && (
                  <div className="space-y-2 font-mono text-[12px]">
                    {Object.entries(attrib.mapping ?? {}).map(([raw, name]) => (
                      <div key={raw} className="flex justify-between text-accent"><span>{name}</span><span className="text-text-low">{raw}</span></div>
                    ))}
                    {(attrib.missing ?? []).map(k => (
                      <div key={k} className="flex justify-between text-text-low/60"><span>{k}</span><span>无输出（静默）</span></div>
                    ))}
                    {(attrib.missing ?? []).some(k => k.startsWith('M')) && (
                      <div className="pt-2 text-left text-[11px] leading-relaxed text-text-low">
                        背键静默 = 固件默认无映射，需设备端 0xA3 映射写入后才有输出（v0.2 逆向中，ADR-016）。
                      </div>
                    )}
                  </div>
                )}
                <button className="btn mt-5 justify-center" onClick={() => setAttrib(null)}>关闭</button>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
