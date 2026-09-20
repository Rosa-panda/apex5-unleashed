# ADR-025：官方 Mod 路线——直连 DSX 协议消费官方 Mod 事件流

日期：2026-09-20 · 状态：**侦察完成，H1 已证实**（待立项实现）

## 背景

用户拍板补齐工具最后一块短板：43 条官方 mod_only 游戏的事件级适配。
用户原则：**不开空间站常驻、零外部驱动依赖**（ADR-020 教训），让官方 Mod 给我们打工。

## 逆向结论（2026-09-20，全部实锤）

**空间站架构**（`C:\Program Files\Flydigi Space Station`）：
- Electron 壳 ↔ `SpaceStationService.exe`（.NET 8 单文件，80MB）：命名管道 `fcs.sock`，
  帧格式 `FDG_PROTOCOL\n` + 4B LE 长度 + protobuf IpcCommand（>1MB 走 FDG_CHUNK 分块，
  >5MB 走 FDG_COMPRESSED gzip）——CommunicationProtocolHandler.cs 全文已逆
- 服务主程序集反编译：`spacestation\decomp\biz`（Flydigi.ControllerService）+
  `decomp\runner`（AdapterTriggerService）——carve 脚本 `spacestation\carve_biz.py` 可复跑

**官方 Mod 系统真面目（比预想简单得多）**：

1. **官方 Mod = 独立 exe**（如 `AdapterTrigger_F1Game23.exe`），从公开 CDN 下载：
   `https://api-web.cdn.flydigi.com/pcspacegame/...zip`（本地列表 45 条全带 ModDownLoadUrl，
   无鉴权直链）。ModStartType=1 装到服务目录，=0 装进游戏目录。
2. **Mod 往 `127.0.0.1:7878/UDP` 发 JSON——DualSenseX 协议原样**：
   `{"instructions":[{"type":1,"parameters":[侧,模式,start,end,力参数...]}]}`
   （InstructionType：1=TriggerUpdate 2=RGB 3=PlayerLED 4=TriggerThreshold 5=MicLED；
   侧 0=左 2=右）。飞智整个监听端就是抄的 DSX 服务器（连 7878/转发 8787 端口都一致）。
3. 服务端翻译（ControllerBusinessService.OnTriggerCommandReceived）：type 1 →
   `ForceTriggerConfigCommon(byte[7])`（array[0]=parameters[1] 模式，array[1..]=
   parameters[3..]）→ UpdateAdapterTriggerConfig → **SetForceTrigger 0x1011 下发**——
   与我们 protocol.py cmd 51 同一条路。
4. 游戏运行检测（CheckGame 1Hz 轮询进程名）+ Mod 进程生命周期管理（游戏退出 Kill mod）
   全在服务端 AdapterTriggerRunner，逻辑简单可整体复刻。

## 决策（H1 已证实，升级为可实施）

**我们不需要伪装任何东西**：本机空间站服务已停用（Manual），UDP 7878 空置。
实现路径：
1. 工具内置 DSX UDP ingress 7878 监听（ADR-009 早已设计！防洪坝照抄）
2. 从官方 CDN 下载 mod zip → 解压到我们自己的 mods 目录（不装进游戏目录/服务目录）
3. 游戏前台 + 有 mod → 拉起 mod exe；游戏退出 → 收掉（照抄 CheckGame 状态机）
4. 7878 包 → 翻译成 cmd 51（映射表官方翻译逻辑已逆，直接照抄）
- 附带红利：**整个 DSX mod 开源生态（github DSX 社区 mod）自动兼容我们的工具**——
  它们全都往 7878 发同款协议。飞智的 mod 本身大概率就是 DSX 社区 mod 的换皮。
- 风险：mod exe 可能探测服务是否在跑（未验证，需实测一例）；7878 被占时官方
  fallback 到 8787，我们同样处理。版权：mod zip 属飞智分发物，工具只做「下载引导+
  事件翻译」，不随软件分发 mod 本体（与封面图同策略，R2）。

## 后果

- 成则 43 条 mod_only 游戏获得官方同款事件级适配，且零空间站、零驱动、零桥接；
- DSX 生态 mod 直接可用，工具成为「DSX mod 兼容 + 飞智官方 mod 兼容」双生态收端；
- 后续工作：P1 实测一个 mod（F1 23 或 FH5）验证收包；P2 实现 ingress+mod 管家；
  P3 前端接入（游戏库 Mod 条目点亮）。
