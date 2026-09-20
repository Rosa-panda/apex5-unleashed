# ADR-025：官方 Mod 路线——直连 DSX 协议消费官方 Mod 事件流

日期：2026-09-20 · 状态：**已实现**（ingress + Mod 管家 + 数据/API/前端全链路落地，待真机验证）

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
- ~~后续工作：P1 实测一个 mod（F1 23 或 FH5）验证收包；P2 实现 ingress+mod 管家；
  P3 前端接入（游戏库 Mod 条目点亮）。~~ **全部落地（2026-09-20 同日）**：

## 实现（2026-09-20）

- `backend/app/dsxingress.py`：DsxIngress——7878（被占落 8787，照官方 fallback）UDP 收包
  → magic19 飞智包**直通** cmd51（parameters[3]=wire 模式、[4..9]=成品字节，补零到定长 5）；
  DSX 社区包（TriggerMode 0-18）走近似翻译子集（Resistance/Bow→race、VibrateTrigger→
  vibration、固定阻尼档映射），不认识的不硬译并计数。去重 + 每侧 15ms 限频（ADR-009）+
  `proxy.holder != "self"` 时只收不发。写 `C:\Temp\DualSenseX\DualSenseX_PortNumber.txt`
  兼容 DSX 生态端口发现。
- `backend/app/modmgr.py`：ModManager——官方 CDN 下载 zip（64MB 上限）→ 解压展平到
  `%APPDATA%\Apex5Unleashed\mods\<gid>\`；前台事件驱动（挂 `games.subscribers`，不占轮询
  线程）：游戏前台 + 已启用 + 已安装 → `Popen([exe, "<port> name=<游戏进程> port=<port>"])`
  （GameHelper.StartGameMod 同款参数；进程名取 `mod.process`=官方 ProcessGameName，不是
  档案 exe[0]）+ 双侧 unbind_grip 抑制 cmd82 抢扳机；游戏退出 kill + 清扳机 + 重套档案 vib。
  XGameMonitor 型先改写 `game_folder.txt` 为真实游戏目录（zip 里写死打包者路径）。
  **start_type=0（F4SE/ScriptHookV 插件型 7 条）v1 明确拒绝自动安装**（要写游戏目录，
  ADR-025 R3）。
- `tools/merge_mod_fields.py`：官方 adapterTriggerGames.json 的 mod 字段按 official_id
  并入内置 of-*.json（44 条已合并入库；mod 本体不进仓库，只存 CDN 直链）。
- `service.py`：`/api/mods`（状态）、`/api/mods/{gid}/install|uninstall|enable`、
  `/api/mods/stop`。
- `main.py`：ingress 启动 + mods 挂前台订阅 + 退出/panic 前 stop_mod 杀子进程。
- 前端 GameLibrary：Mod条目角标三级（未启用灰 / 已启用琥珀 / ⚡运行中青色），卡内
  安装/启用/停行，顶栏 DSX 收发计数。
- 测试 `backend/test_dsx_mod.py` 9 条（F1 23 实测包直通帧断言、去重/限频/代理守门、
  UDP 回环、生命周期、插件型拒绝）全绿。

**关键实锤修正**：侧枚举以 DSX 官方源码为准——1=左 2=右（本文件上文「0=左 2=右」为
侦察早期误记，F1 23 mod 反编译 `int[8]{0,2,19,...}` 油门=右侧、`{0,1,19,...}` 刹车=
左侧佐证）；parameters[0] 为手柄号（官方恒 0）。7878 被占时 ingress 落 8787，mod 拉起
参数同步用 ingress 实际端口（否则 mod 发包进官方服务）。

**待真机验证**：装一个 F1 23 mod 实测收包→扳机手感；XGameMonitor 型（30 条）的
configs 键名匹配与 game_folder.txt 改写实测；DSX 社区 mod 兼容性抽测。

**后续项（R 系列）**：R1 4 条 ModName 空/特殊的条目（鬼泣5/骑砍2/RE3/RE7——插件型处理）；
R2 mod 版本更新检测（Version 字段已在档）；R3 插件型自动安装（需游戏路径选择 UI +
风险提示）；R4 mod 控制台日志（showConsole=true）诊断面板。
