# ADR-020 修订 B：DS 桥接功能彻底删除（2026-09-19）

## 状态

已接受 —— 从「休眠保留」（revA）升级为**全量删除**，用户拍板（2026-09-19 会话）。

## 背景

revA 封存时保留了后端代码（asb.py / engine bridge 仲裁 / API / 前端仅下线入口），
理由是"未来正版 Steam 用户群可低成本复活"。后续本机卸载 ASB+usbip+HidHide 引发
USB 栈事故（根集线器孤儿扩展 + 三类过滤器残留，详见 APEX5-DEV-STATUS.md 2026-09-19），
用户决定与该路线彻底切割：外部驱动依赖的隐性风险不值得为"不可达的未来"保留代码。

## 决策

1. 删除 `backend/app/asb.py` 整个模块。
2. engine.py 删除 holder=bridge 第三态与 ASB 进程归因（PROXY_PROCESS 中的 ASB 条目、
   bridge 事件发射）；仲裁回归 self/external 两态。
3. service.py 删除 `/api/bridge/{status,launch,open-download,restore-visibility}` 与
   `/api/games/{gid}/dsbridge` 端点及 DsBridgeReq 模型。
4. gameprofiles.py 删除 ds_bridge 让位逻辑与 set_ds_bridge()；档案 JSON 中已存的
   ds_bridge 字段变为无害冗余数据（不主动清洗用户文件）。
5. tray.py 删除 bridge 紫色图标态。
6. 前端删除 Bridge.tsx、导航项、桥接横幅、api.ts 桥接函数、游戏库 DS 徽标/开关。
7. 删除 test_bridge_arbitration.py。
8. ADR-020 原文与 revA 保留作为决策史；实测方法论（B1-B5）记录于 APEX5-DEV-STATUS.md
   不随代码删除。

## 后果

- 若未来重启该路线，需从 git 历史找回（本 ADR 为删除前的最后锚点）。
- 主路径（扳机模式 / cmd 0x52 通用震动 / 官方逐游戏适配 / 灯光 / 屏幕 / 拓展键）
  完全不受影响。
- 产品不再包含任何指向 ApexSenseBridge/驱动层的引用，"零外部依赖"承诺彻底兑现。
