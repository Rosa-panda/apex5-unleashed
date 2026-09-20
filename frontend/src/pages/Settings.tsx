// 设置页（2026-09-20 重构）：真设置，不只说明文字——
// 联动行为开关 / 开机自启 / 封面缓存管理 / 数据目录 / 关于与安全机制。
import { useCallback, useEffect, useState } from 'react'
import {
  FolderOpen, Gamepad2, HardDrive, Info, Power, ShieldCheck, ToggleLeft, Zap,
} from 'lucide-react'
import { api } from '../api'

function Toggle({ on, onChange, label, desc }: {
  on: boolean
  onChange: (v: boolean) => void
  label: string
  desc: string
}) {
  return (
    <button onClick={() => onChange(!on)}
      className="flex w-full items-start gap-3 rounded-lg border border-border-soft bg-[#0d0d14] p-3 text-left transition-colors hover:border-accent-dim">
      <span className={`mt-0.5 flex h-5 w-9 shrink-0 items-center rounded-full p-0.5 transition-colors ${
        on ? 'bg-accent' : 'bg-white/15'}`}>
        <span className={`h-4 w-4 rounded-full bg-white shadow transition-transform ${
          on ? 'translate-x-4' : ''}`} />
      </span>
      <span className="min-w-0">
        <span className={`block text-[13px] ${on ? 'text-accent' : 'text-text-mid'}`}>{label}</span>
        <span className="mt-0.5 block text-[11px] leading-snug text-text-low">{desc}</span>
      </span>
    </button>
  )
}

export default function Settings() {
  const [autoswitch, setAutoswitch] = useState(true)
  const [universalVib, setUniversalVib] = useState(false)
  const [autostart, setAutostart] = useState(false)
  const [cache, setCache] = useState<{ count: number; bytes: number } | null>(null)
  const [msg, setMsg] = useState('')

  const load = useCallback(() => {
    api.games().then(g => {
      setAutoswitch(g.autoswitch)
      setUniversalVib(g.universal_vib)
    }).catch(() => {})
    api.autostart().then(r => setAutostart(r.enabled)).catch(() => {})
    api.imgCacheStatus().then(r => setCache({ count: r.count, bytes: r.bytes })).catch(() => {})
  }, [])
  useEffect(() => { load() }, [load])

  const flash = (t: string) => { setMsg(t); setTimeout(() => setMsg(''), 3500) }

  const fmtBytes = (b: number) =>
    b >= 1024 * 1024 ? `${(b / 1024 / 1024).toFixed(1)} MB` : `${Math.round(b / 1024)} KB`

  return (
    <div className="mx-auto max-w-2xl space-y-5">
      {/* ---------- 联动行为 ---------- */}
      <div className="card p-5">
        <div className="mb-3 flex items-center gap-2 text-[12px] text-text-mid">
          <Zap size={14} className="text-accent" /> 联动行为
          <span className="text-text-low">· 与游戏库工具条同源，两边改哪边都算数</span>
        </div>
        <div className="space-y-2">
          <Toggle on={autoswitch} label="切到游戏自动套用"
            desc="前台检测到已收录的游戏时，自动应用它的适配/预设；关掉后一切只手动。"
            onChange={v => { setAutoswitch(v); api.setAutoswitch(v).then(() => flash('✓ 已保存')).catch(() => flash('✗ 保存失败')) }} />
          <Toggle on={universalVib} label="通用震动联动"
            desc="没有专属适配的游戏也把游戏震动转到扳机上（设备端固件路由，全局生效）。"
            onChange={v => { setUniversalVib(v); api.setUniversalVib(v).then(() => flash('✓ 已保存')).catch(() => flash('✗ 保存失败')) }} />
        </div>
        <div className="mt-2 text-[11px] text-text-low">
          两个开关都会记住（重启不丢）；适配优先级：官方适配 &gt; 通用联动 &gt; 标准模式。
        </div>
      </div>

      {/* ---------- 应用与系统 ---------- */}
      <div className="card p-5">
        <div className="mb-3 flex items-center gap-2 text-[12px] text-text-mid">
          <Power size={14} className="text-accent" /> 应用与系统
        </div>
        <div className="space-y-2">
          <Toggle on={autostart} label="开机自动启动"
            desc="写入当前用户的注册表 Run 项（不需要管理员）；开机后在托盘待命，不弹窗。"
            onChange={v => api.setAutostart(v)
              .then(() => { setAutostart(v); flash(v ? '✓ 已开启开机自启' : '✓ 已关闭开机自启') })
              .catch(() => flash('✗ 写入失败'))} />
        </div>
        <div className="mt-2 text-[11px] text-text-low">
          窗口 X = 最小化到托盘（后台继续联动），真退出在角标菜单「退出」。
        </div>
      </div>

      {/* ---------- 数据与缓存 ---------- */}
      <div className="card p-5">
        <div className="mb-3 flex items-center gap-2 text-[12px] text-text-mid">
          <HardDrive size={14} className="text-accent" /> 数据与缓存
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-md border border-border-soft bg-[#0d0d14] px-3 py-1.5 text-[12px] text-text-mid">
            封面图缓存：{cache ? `${cache.count} 张 · ${fmtBytes(cache.bytes)}` : '统计中…'}
          </span>
          <button className="btn !py-1 text-[12px]" disabled={!cache || cache.count === 0}
            onClick={() => api.imgCacheClear()
              .then(r => { flash(`✓ 已清除，释放 ${fmtBytes(r.freed_bytes)}`); load() })
              .catch(() => flash('✗ 清除失败'))}
            title="删除已下载的封面图；清掉后后台会按需重新下载，网络不好时游戏库会暂时没图">
            清除封面缓存
          </button>
          <button className="btn !py-1 text-[12px]" onClick={() => api.openDataFolder()
            .then(() => flash('✓ 已在资源管理器打开')).catch(() => flash('✗ 打开失败'))}>
            <FolderOpen size={12} /> 打开数据文件夹
          </button>
        </div>
        <div className="mt-2 text-[11px] text-text-low">
          游戏档案/预设/灯表备份都在 <code className="text-text-mid">%APPDATA%\Apex5Unleashed</code>，备份这个文件夹即备份你的全部数据。
        </div>
      </div>

      {/* ---------- 关于 ---------- */}
      <div className="card p-5">
        <div className="mb-3 flex items-center gap-2 text-[12px] text-text-mid">
          <Info size={14} className="text-accent" /> 关于
        </div>
        <div className="space-y-1.5 text-[13px]">
          <Row k="产品" v="Apex5 Unleashed v0.1" />
          <Row k="协议" v="飞智 Apex 5 私有 HID（VID 37D7 / PID 2501 / usage FFA0）· 实机逆向验证" />
          <Row k="许可证" v="GPLv3（开源）" />
          <Row k="作者" v="laisn + Claude Code 全自动流水线" />
        </div>
      </div>

      {/* ---------- 安全机制 ---------- */}
      <div className="card p-5">
        <div className="mb-3 flex items-center gap-2 text-[12px] text-text-mid">
          <ShieldCheck size={14} className="text-accent" /> 安全机制（自动生效，无需配置）
        </div>
        <div className="space-y-2 text-[12px] leading-relaxed text-text-mid">
          <p>· <b className="text-text-hi">锁存账本</b>：所有下发先记账，状态面板所见即手柄真实状态。</p>
          <p>· <b className="text-text-hi">启动卫生检查</b>：每次手柄连接先无条件复位，清除上次强杀残留的马达/扳机效果。</p>
          <p>· <b className="text-text-hi">代理权检测</b>：总线上出现非本软件命令即为铁证（本进程三条写路径均登记宽限账本，自己人不误报），结合进程扫描（飞智空间站 / Steam / DualSenseX）归因提示。</p>
          <p>· <b className="text-text-hi">预设事务</b>：应用失败自动回滚到 Normal 基线，不留半套效果。</p>
          <p>· <b className="text-text-hi">单 HID 线程</b>：读写集中一个工作线程，流式与队列命令共用写锁防帧交错。</p>
        </div>
      </div>

      <div className="flex items-center gap-2 text-[11px] text-text-low">
        <Gamepad2 size={12} /> <ToggleLeft size={12} />
        路线图：统一游戏配置格式（ADR-015）、社区预设分享。DS 虚拟手柄桥接已废弃（ADR-020）。
        {msg && <span className="ml-auto text-[12px] text-accent">{msg}</span>}
      </div>
    </div>
  )
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex gap-4">
      <span className="w-16 shrink-0 text-text-low">{k}</span>
      <span>{v}</span>
    </div>
  )
}
