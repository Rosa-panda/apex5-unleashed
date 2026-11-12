// 全局状态横幅：任何页面一眼可见，并直接给出解决办法。
// 红：后台断了 / 黄：手柄没连 / 橙：手柄被别的软件接管 / 橙（或灰）：飞智虚拟手柄占用 XInput 0 号槽
import { useState } from 'react'
import { ChevronDown, Gamepad, ShieldAlert, Wrench } from 'lucide-react'
import { api } from '../api'
import { usePolling } from '../hooks/usePolling'
import type { VibFixStatus } from '../api/types'

interface Proxy { holder: string; detail: string; mild?: boolean }

// 接管者 → 解决步骤（按软件分别写，用户照着做）
function guideFor(who: string): string[] {
  if (who.includes('飞智')) {
    return [
      '空间站在手柄接入时会短暂接管做初始化，一般 15 秒后自动收回，先点「立即夺回」即可。',
      '如果一直被接管：关闭飞智空间站的窗口（托盘图标右键 → 退出），它的界面在改配置时会持续写手柄。',
      '注意别停掉空间站的后台服务：游戏震动要靠它转发（见下方「虚拟手柄」提示）。',
    ]
  }
  if (who.includes('Steam')) {
    return [
      'Steam 开了手柄支持会接管手柄：Steam 设置 → 控制器 → 关闭「Xbox 手柄支持」「Steam 输入」。',
      '或者玩非 Steam 游戏时直接退出 Steam。',
      '处理后点「立即夺回」。',
    ]
  }
  if (who.includes('DualSense')) {
    return ['退出 DualSenseX（托盘图标右键 → 退出），然后点「立即夺回」。']
  }
  return [
    '先点「立即夺回」，对方 15 秒无动作也会自动收回。',
    '一直被抢：按 Ctrl+Shift+Esc 打开任务管理器，结束手柄类软件（DS4Windows、Xbox 配件、手柄映射工具等）。',
    '仍然不行：到「设置」页的「游戏震动修复」查看，或重新插拔手柄。',
  ]
}

export function StatusBanner({ connected, online, mock, proxy, onGoto }: {
  connected: boolean; online: boolean; mock: boolean
  proxy?: Proxy
  onGoto: (page: 'settings') => void
}) {
  const [vf, setVf] = useState<VibFixStatus | null>(null)
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState('')
  const [msg, setMsg] = useState('')
  const [hidden, setHidden] = useState(() => sessionStorage.getItem('vibfix-hint-hidden') === '1')

  usePolling(() => { api.vibfix().then(setVf).catch(() => {}) }, 5000, [])

  const taken = proxy?.holder === 'external' && !proxy.mild
  const who = proxy?.detail || '未知进程'

  const reclaim = async () => {
    setBusy('reclaim')
    try { await api.reclaim(); setMsg('已夺回') } catch { setMsg('夺回失败，请按下方步骤处理') }
    setBusy('')
  }
  const fixVib = async () => {
    setBusy('fix')
    setMsg('请在弹出的系统授权框点「是」…')
    try {
      await api.vibfixSet(false, 'temporary')
      setMsg('已临时禁用虚拟手柄，软件退出后自动恢复')
      api.vibfix().then(setVf).catch(() => {})
    } catch (e) { setMsg((e as Error).message) }
    setBusy('')
  }

  // 虚拟手柄占 0 号槽：服务不在跑 = 震动必丢（醒目）；服务在跑 = 一般会转发（淡提示，可关）
  const virtualPad = vf?.state === 'enabled'
  const svcDown = virtualPad && vf?.service_running === false

  return (
    <>
      {!connected ? (
        <div className="flex items-center gap-2 border-b border-err/30 bg-err/10 px-6 py-1.5 text-[12px] text-err">
          <Gamepad size={13} /> 无法连接软件后台（127.0.0.1:18765），正在自动重连…
        </div>
      ) : !online && !mock ? (
        <div className="flex items-center gap-2 border-b border-warn/30 bg-warn/10 px-6 py-1.5 text-[12px] text-warn">
          <Gamepad size={13} /> 手柄未连接 —— 请检查 USB 线或重新插拔手柄；接上后设备功能自动恢复
        </div>
      ) : null}

      {connected && taken && (
        <div className="border-b border-warn/40 bg-warn/15 px-6 py-2 text-[12px] text-warn">
          <div className="flex flex-wrap items-center gap-3">
            <ShieldAlert size={14} className="shrink-0" />
            <span className="min-w-0 flex-1">
              <b>手柄正被「{who}」接管</b>——此时本软件的扳机设置、游戏适配都不会生效（对方停手 15 秒后会自动收回）
            </span>
            <button className="btn btn-primary shrink-0 !py-0.5 !text-[12px]" disabled={busy === 'reclaim'} onClick={reclaim}>
              立即夺回
            </button>
            <button className="btn shrink-0 !py-0.5 !text-[12px]" onClick={() => setOpen(o => !o)}>
              怎么解决 <ChevronDown size={12} className={open ? 'rotate-180' : ''} />
            </button>
          </div>
          {open && (
            <ol className="mt-2 list-decimal space-y-1 pl-9 text-[12px] leading-relaxed text-text-hi/90">
              {guideFor(who).map((s, i) => <li key={i}>{s}</li>)}
            </ol>
          )}
        </div>
      )}

      {connected && virtualPad && (svcDown || !hidden) && (
        <div className={`flex flex-wrap items-center gap-3 border-b px-6 py-1.5 text-[12px] ${
          svcDown ? 'border-warn/40 bg-warn/15 text-warn' : 'border-border-soft bg-white/3 text-text-mid'}`}>
          <Wrench size={13} className="shrink-0" />
          <span className="min-w-0 flex-1">
            {svcDown
              ? <><b>飞智虚拟手柄占用了 0 号槽，而且空间站服务没在运行</b>：原神等游戏的震动会丢，震动联动不会有反馈。</>
              : <>检测到飞智虚拟手柄占用了 0 号槽。空间站服务在运行时，游戏震动一般会被转发；若游戏里仍没有震动，点右侧修复。</>}
            {msg && <span className="ml-2 text-text-hi">{msg}</span>}
          </span>
          <button className="btn btn-primary shrink-0 !py-0.5 !text-[12px]" disabled={busy === 'fix'} onClick={fixVib}
            title="需要系统授权（UAC）。临时禁用飞智虚拟手柄，本软件退出后自动恢复，不留永久改动">
            一键临时修复
          </button>
          <button className="btn shrink-0 !py-0.5 !text-[12px]" onClick={() => onGoto('settings')}>查看详情</button>
          {!svcDown && (
            <button className="shrink-0 text-text-low hover:text-text-mid" title="本次运行不再提示"
              onClick={() => { sessionStorage.setItem('vibfix-hint-hidden', '1'); setHidden(true) }}>×</button>
          )}
        </div>
      )}
    </>
  )
}
