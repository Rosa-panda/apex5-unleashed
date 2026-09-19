import { Info, ShieldCheck } from 'lucide-react'

export default function Settings() {
  return (
    <div className="mx-auto max-w-2xl space-y-5">
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

      <div className="card p-5">
        <div className="mb-3 flex items-center gap-2 text-[12px] text-text-mid">
          <ShieldCheck size={14} className="text-accent" /> 安全机制
        </div>
        <div className="space-y-2 text-[12px] leading-relaxed text-text-mid">
          <p>· <b className="text-text-hi">锁存账本</b>：所有下发先记账，状态面板所见即手柄真实状态。</p>
          <p>· <b className="text-text-hi">启动卫生检查</b>：每次手柄连接先无条件复位，清除上次强杀残留的马达/扳机效果。</p>
          <p>· <b className="text-text-hi">代理权检测</b>：总线上出现非本软件命令即为铁证（本进程三条写路径均登记宽限账本，自己人不误报），结合进程扫描（飞智空间站 / Steam / DualSenseX）归因提示。</p>
          <p>· <b className="text-text-hi">预设事务</b>：应用失败自动回滚到 Normal 基线，不留半套效果。</p>
          <p>· <b className="text-text-hi">单 HID 线程</b>：读写集中一个工作线程，流式与队列命令共用写锁防帧交错。</p>
        </div>
      </div>

      <div className="card p-5 text-[12px] leading-relaxed text-text-low">
        下一步：统一游戏配置格式（ADR-015）、社区预设分享。DS 虚拟手柄桥接路线已废弃删除（ADR-020：消费端依赖 Steam Input，结构性缺失）。
        详见仓库 docs\ 下的 TECH-SPEC 与企划书。
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
