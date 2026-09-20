# ADR-022：引入 ApexSenseBridge 游戏清单与协作定位

日期：2026-09-20 · 状态：已接受

## 背景

游戏库仅 86 条（官方空间站 adapterTriggerGames.json 全量 93 条，34 条带震动调参）。
调研发现开源项目 ApexSenseBridge（ASB，github.com/ReynArts/ApexSenseBridge）维护着
211 款「原生支持 DualSense 自适应扳机/触觉」的游戏清单（data/supported_games.json，
云端自动更新，源自 PCGamingWiki + 社区学习的 exe），含标题/进程名/Steam AppID/封面。

## 决策

1. **导入 ASB 清单为内置档案**（tools/update_asb_list.py，手动跑）：
   - 只取 adaptiveTriggers/hapticFeedback 为 true 的条目；
   - 与官方条目重合（exe 或规范化名命中）的跳过，官方优先（官方带实测 vib 参数）；
   - 标记 `"asb": true`，note 说明「原生 DS 自适应扳机游戏」；
   - 无 executables 的条目保留（展示+封面），exe 为空不参与前台匹配。
2. **协作定位**：事件级扳机效果由 ASB 桥实现（虚拟 DualSense → 翻译 → cmd 81 流式），
   本工具不重复造桥（ADR-020 教训）；与 ASB 共存时本工具的代理检测会如实显示外部占用。
3. **扳机模式枚举勘误**（本 ADR 一并决策）：ASB 实测固件 wire 枚举 2/3 与官方 SDK
   字面名相反——wire 2 实际表现为后坐力（Recoil/Rattle），wire 3 实际为狙击突破
   （Sniper Break）。protocol.py 的 TRIGGER_MODES 交换 sniper/recoil 命名，字段布局
   跟 wire 走不跟名字走。待用户实机手感复核。

## 后果

- 游戏库 ~86 → ~280 条，语义三档：官方调参（vib）/ DS 原生（asb）/ 无适配；
- UI 加「DS 原生」角标区分；
- 若实机复核推翻 ASB 结论，回滚 protocol.py 的交换即可（单点）。
