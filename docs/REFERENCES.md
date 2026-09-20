# 参考项目与致谢（REFERENCES）

本项目站在开源社区与公开数据源的肩膀上。哪些部分借用了谁的知识、用在哪、
对应哪个 ADR，全部列在这里——借用别人的成果就应该留名，不做无头案。

## 项目与数据源

### 1. ApexSenseBridge（ASB）

- 仓库：<https://github.com/ReynArts/ApexSenseBridge>
- **借用了什么**：211 款「原生支持 DualSense 自适应扳机/触觉」的游戏清单
  （`data/supported_games.json`）：标题、进程名、Steam AppID、封面元数据；
  清单本身溯源自 PCGamingWiki 与社区学习。
- **用在了哪**：`tools/update_asb_list.py` 导入为内置档案（`asb-*.json`，
  200+ 条 DS转官 档案）；振动参数为本项目按题材自动学习生成，与 ASB 无关。
- **对应 ADR**：ADR-022（引入协作定位）、ADR-024（参数生成）。

### 2. DualSenseX（DSX）

- 仓库：<https://github.com/Paliverse/DualSenseX>
- **借用了什么**：DSX UDP 协议格式——`127.0.0.1:7878` 上的
  `{"instructions":[{"type":1,"parameters":[...]}]}` JSON 事件流，以及
  `%TEMP%\DualSense\DualSenseX_PortNumber.txt` 端口发现文件约定。
- **用在了哪**：`backend/app/dsxingress.py`——本工具 ingress 兼容该协议，
  既消费飞智官方 Mod 的事件级扳机效果，也给 DSX 社区 mod 提供兜底翻译。
- **对应 ADR**：ADR-025（官方 Mod 假身 + 事件级转译）。

### 3. PCGamingWiki

- 站点：<https://www.pcgamingwiki.com/wiki/Home>
- **借用了什么**：自适应扳机（Adaptive Triggers）游戏支持清单——ASB 清单
  的上游出处，本项目经 ASB 间接引用。
- **用在了哪**：游戏档案的 `note` 与适配依据标注。

### 4. 飞智（Flydigi）官方生态

- **引用了什么**：
  - 空间站 `adapterTriggerGames.json`——官方逐游戏震动联动调参数据
    （从**用户本机已安装**的空间站软件读取解析，`import-official` 按钮）；
  - 官方 Mod CDN 直链（`api-web.cdn.flydigi.com`）——Mod 本体不进仓库，
    内置档案只存条目元数据与下载地址；
  - 官方 Mod 的 XGameMonitor 启动参数格式。
- **说明**：协议与端点均为本项目实机逆向所得（`docs/PROTOCOL.md` 为原创
  逆向成果）；官方数据条目版权归飞智所有，本项目与飞智官方无任何关联。

### 5. Steam

- **借用了什么**：游戏封面图（`shared.akamai.steamstatic.com` 等公开 CDN），
  按 Steam AppID 运行时拉取、本地缓存（`backend/app/gameimg.py`），不打包
  进仓库。

## 方法论与知识来源

- **XInput 槽位诊断**：微软 XInput 文档（`XInputGetCapabilities` /
  `XInputSetState`）——2026-09-20 排查「原神不震」时用于定位飞智虚拟手柄
  抢占 0 号槽；诊断结论沉淀为 `backend/app/vibfix.py`（游戏震动修复）。
- **CfgMgr32 设备管理 API**：微软配置管理器文档（`CM_Locate_DevNodeW` /
  `CM_Get_DevNode_Status`）——vibfix 设备树状态检测与 UAC 提权处置。

## 依赖的开源组件

后端：Python / FastAPI / uvicorn / pywebview / Pillow / pystray；
前端：React / TypeScript / Vite / TailwindCSS / lucide-react。
各自遵循其原始许可证，见对应项目主页。

## 许可

本工程代码 GPLv3。引用的数据与第三方成果归各自原作者所有——
若有遗漏的引用来源，欢迎提 issue 补充。
