// #18 模拟器体感桥（DSU/Cemuhook）（ADR-029 F2 自 panels.tsx 逐字搬出）
import { useState } from 'react'
import { api } from '../../../api'
import { usePolling } from '../../../hooks/usePolling'
import { BTN, BTN_ACC, Err, Row, useFlash } from '../ui'

export function DsuPanel() {
  const [st, setSt] = useState<any>(null)
  const [msg, flash] = useFlash()
  // （原实现带 alive 守卫防 unmount 后 setState；React 18 下该 setState 本就是
  // no-op，F3 收敛为 usePolling 后守卫随之去除——无可观察行为差异）
  usePolling(() => api.expDsu().then(setSt).catch(() => {}), 600)
  const setInvert = (i: number) => {
    const next = [...(st?.invert ?? [false, false, false])]
    next[i] = !next[i]
    api.expDsuSet(!!st?.enabled, st?.port ?? 26760, next)
      .then((j: any) => { setSt(j); flash('✓ 已更新（下一包即生效）') })
      .catch((e: any) => flash('', e))
  }
  return (
    <div className="space-y-2.5">
      {/* Yuzu 配置指引（核心文案：用户就是卡在这一步找过来的） */}
      <div className="rounded-md border border-cyan-500/30 bg-cyan-500/10 p-2 text-[11px] text-cyan-200">
        模拟器里怎么接：输入设备保持 XInput 不动 → 配置 →
        「Motion 体感」提供者选 <b>CemuhookUDP</b> → 服务器 <b>127.0.0.1</b> 端口{' '}
        <b>{st?.port ?? 26760}</b> → 点 Test 应显示「connected」，再对要绑定的
        Motion 按键点 Configure 晃动手柄即绑定。Cemu/Dolphin/PCSX2 同理（都认 DSU 协议）。
      </div>
      <Row label="服务">
        <button className={st?.enabled ? BTN_ACC : BTN}
          onClick={() => api.expDsuSet(!st?.enabled, st?.port ?? 26760)
            .then((j: any) => { setSt(j); flash(j.enabled ? `✓ 监听 127.0.0.1:${j.port}` : '已停止') })
            .catch((e: any) => flash('', e))}>
          {st === null ? '…' : st.enabled ? `运行中（:${st.port}）— 点击停止` : `启动（端口 ${st?.port ?? 26760}）`}
        </button>
        <span className="text-[10px] text-text-low">
          客户端 {st?.stats?.clients ?? 0} ｜ 已发数据包 {st?.stats?.motion_sent ?? 0}
          {st?.stats?.note ? ` ｜ ${st.stats.note}` : ''}
        </span>
      </Row>
      {/* 实时预览：模拟器视角看到的体感值（转动/平放能直接对上号） */}
      <div className="rounded-md border border-border-soft p-2 font-mono text-[10px] text-text-low">
        {st?.has_imu ? (
          <>
            加速度(g)：{st.preview.accel.join(', ')}<br />
            陀螺(deg/s)：pitch {st.preview.gyro[0]} ｜ yaw {st.preview.gyro[1]} ｜ roll {st.preview.gyro[2]}
          </>
        ) : '等待 0xEF 运动流…（手柄在线即自动来数）'}
      </div>
      <Row label="轴向">
        {['pitch', 'yaw', 'roll'].map((k, i) => (
          <button key={k} className={st?.invert?.[i] ? BTN_ACC : BTN} onClick={() => setInvert(i)}>
            {k} {st?.invert?.[i] ? '（反转）' : ''}
          </button>
        ))}
        <span className="text-[10px] text-text-low">游戏里某个轴反了手感就翻它</span>
      </Row>
      <Err e={msg} />
    </div>
  )
}
