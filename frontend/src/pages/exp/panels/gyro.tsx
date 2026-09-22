// #1 体感瞄准（软件层）（ADR-029 F2 自 panels.tsx 逐字搬出）
import { useCallback, useState } from 'react'
import { api } from '../../../api'
import { usePolling } from '../../../hooks/usePolling'
import { BTN, BTN_ACC, Err, NoDev, Row, useFlash } from '../ui'

export function GyroPanel() {
  const [st, setSt] = useState<any>(null)
  const [msg, flash] = useFlash()
  const load = useCallback(() => { api.expGyro().then(setSt).catch(e => flash('', e)) }, [])
  usePolling(load, 1000, [load])
  if (!st) return <div className="space-y-2"><NoDev /><Err e={msg} /></div>
  const c = st.cfg
  const set = (patch: Record<string, unknown>) =>
    api.expGyroSet(patch).then((r: any) => { setSt(r); flash('✓ 已保存') }).catch(e => flash('', e))
  const g = st.stats?.last_gyro ?? [0, 0, 0]
  return (
    <div className="space-y-2">
      {/* 路标：三种「游戏用体感」的通道，防止重复造不存在的开关 */}
      <div className="rounded-md border border-border-soft bg-black/20 p-2 text-[10px] leading-relaxed text-text-low">
        <span className="text-text-mid">游戏怎么用上手柄体感？三条路：</span>
        ① 普通 XInput 游戏（不认体感）→ <b>固件层陀螺→摇杆</b>（测试区 #6，关软件也生效）或本面板软件层陀螺→鼠标；
        ② 原生体感游戏（Steam Input / DS5 移植 / NSO）→ <b>手柄拨硬件模式键切 Switch 模式</b>，
        切换后手柄在 USB 层变成任天堂设备（057e:2009），本工具和飞智空间站都看不见它，由游戏/Steam 自己接管——软件开关对此无解，不是功能缺失。
      </div>
      <Row label="总开关">
        <button className={c.enabled ? BTN_ACC : BTN} onClick={() => set({ enabled: !c.enabled })}>
          {c.enabled ? '开启中（点此关闭）' : '已关闭（点此开启）'}
        </button>
        <span className="text-[10px] text-text-low">软件层：工具运行时才生效，与固件层互斥；受「体感总闸」节制</span>
      </Row>
      <Row label="激活方式">
        <select className="rounded border border-border-soft bg-black/30 px-1 py-0.5 text-[11px]"
          value={c.activation} onChange={e => set({ activation: e.target.value })}>
          <option value="always">常开</option>
          <option value="key">按住拓展键</option>
        </select>
        {c.activation === 'key' && (
          <select className="rounded border border-border-soft bg-black/30 px-1 py-0.5 text-[11px]"
            value={c.activation_key} onChange={e => set({ activation_key: e.target.value })}>
            {['m1', 'm2', 'm3', 'm4', 'lm', 'rm'].map(k => <option key={k} value={k}>{k.toUpperCase()}</option>)}
          </select>
        )}
      </Row>
      <Row label={`灵敏度 ${c.sens}`}>
        <input type="range" min={1} max={200} value={c.sens} className="w-40"
          onChange={e => set({ sens: +e.target.value })} />
      </Row>
      <Row label={`像素增益 ${c.gain}`}>
        <input type="range" min={2} max={40} step={0.5} value={c.gain} className="w-32"
          onChange={e => set({ gain: +e.target.value })} />
        <span className="text-[10px] text-text-low">手感待真机调（官方标定常数未公开）</span>
      </Row>
      <Row label="轴向">
        yaw
        <select className="rounded border border-border-soft bg-black/30 px-1 py-0.5 text-[11px]"
          value={c.yaw_axis} onChange={e => set({ yaw_axis: e.target.value })}>
          {['x', 'y', 'z'].map(a => <option key={a}>{a}</option>)}
        </select>
        pitch
        <select className="rounded border border-border-soft bg-black/30 px-1 py-0.5 text-[11px]"
          value={c.pitch_axis} onChange={e => set({ pitch_axis: e.target.value })}>
          {['x', 'y', 'z'].map(a => <option key={a}>{a}</option>)}
        </select>
        <label className="flex items-center gap-1"><input type="checkbox" checked={c.invert_x} onChange={e => set({ invert_x: e.target.checked })} /> 反转X</label>
        <label className="flex items-center gap-1"><input type="checkbox" checked={c.invert_y} onChange={e => set({ invert_y: e.target.checked })} /> 反转Y</label>
      </Row>
      <div className="text-[10px] text-text-low">
        陀螺实时 [{g.map((v: number) => v.toFixed(0)).join(', ')}] ｜ 流速率 ~{st.stats?.rate?.toFixed?.(0) ?? '—'}Hz ｜ 帧数 {st.stats?.frames ?? 0}
      </div>
      <Err e={msg} />
    </div>
  )
}
