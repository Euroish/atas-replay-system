# A 股订单流回放分析系统产品开发设计

## 0. 文档治理与工作流

本项目文档以 `atas开发/project.md` 为唯一主文档。凡是会影响产品范围、架构边界、数据口径、回放语义、验收标准、开发顺序的内容，最终都必须回写到本文件，其他文档不得独立定义这些事实。

当前文档职责固定如下：

| 文件 | 角色 | 是否权威 | 允许写入内容 |
| --- | --- | --- | --- |
| `atas开发/project.md` | 主文档 / 单一事实源 | 是 | 需求、约束、架构、数据模型、模块职责、开发阶段、验收标准、文档规则 |
| `atas开发/READ.ME.md` | 入口导航 | 否 | 项目一句话目标、当前应先读什么、各文档用途 |
| `atas开发/订单流分析系统设计.md` | 历史草案 / 思路沉淀 | 否 | 早期问题、候选方案、被采纳或废弃的思路，禁止单独定义当前事实 |
| `task_plan.md` | 当前任务计划 | 否 | 当前一次工作分解、阶段状态、成功标准 |
| `findings.md` | 当前任务发现 | 否 | 本轮调研结论、核对结果、证据摘要 |
| `progress.md` | 当前任务日志 | 否 | 本轮执行记录、错误、验证结果 |

开发过程统一按以下工作流处理，避免漂移：

1. 新需求、争议点、重大设计变化先落到 `findings.md` 或 issue 草稿，不直接散落到多个正式文档。
2. 结论一旦确认，只更新 `atas开发/project.md`，把它作为唯一需要长期维护的正式事实。
3. `READ.ME.md` 只做导读，不复制 `project.md` 的章节内容。
4. `订单流分析系统设计.md` 只保留为历史输入；如果其中某条思路被正式采纳，必须改写进 `project.md`，而不是只留在草案里。
5. 实现阶段的临时计划、阶段进度、验证记录只写 `task_plan.md`、`findings.md`、`progress.md`，任务结束后不反向污染正式设计。
6. 任何 PR 或阶段提交，如果修改了代码语义但没有同步更新 `project.md` 中对应约束、接口、阶段或验收标准，则视为文档未完成。

每次开发前后只回答四个问题：

- 这次变化是否改变了产品事实或技术边界？
- 如果改变了，`project.md` 哪一节要更新？
- 这次只是执行计划还是改变设计？
- 当前信息是长期事实，还是本轮任务的临时记录？

判定规则：

- 长期事实写入 `project.md`。
- 导航说明写入 `READ.ME.md`。
- 历史讨论保留在 `订单流分析系统设计.md`。
- 临时任务信息写入 `task_plan.md`、`findings.md`、`progress.md`。

## 0.1 Harness 工作流

本项目的 harness 目标不是把 agent 变成只能照步骤执行的流水线，而是给 agent 足够自由去选择最优路径，同时用少量硬约束把质量、漂移和返工成本压住。

### 0.1.1 设计原则

- 自由选择路径，不自由改变目标。
- 自由选择实现顺序，不自由突破产品边界。
- 自由做局部试错，不自由跳过验证。
- 优先最小闭环交付，不优先表面完整度。
- 任何自主决策都必须能回到 `project.md` 的事实、约束和验收标准。

### 0.1.2 Harness 输入层

agent 每次开始工作时，只允许从以下四层读取约束，按优先级自上而下决策：

1. 用户当前任务：当前这次明确要完成什么。
2. `atas开发/project.md`：长期事实、边界、架构和验收。
3. `task_plan.md`：本轮任务计划、阶段和成功标准。
4. `findings.md` / `progress.md`：本轮发现、执行记录和验证结果。

如果低优先级文件与高优先级文件冲突，按高优先级执行，并在本轮任务中修正低优先级文件。

### 0.1.3 Agent 自主权边界

允许 agent 自主决定：

- 先读哪些代码或数据文件。
- 采用哪条实现路径和拆分顺序。
- 是否先做验证脚本、测试、原型或最小实现。
- 在不改变产品事实的前提下，怎样做最小改动获得最高确定性。

不允许 agent 自主决定：

- 扩大产品范围。
- 改写已确认的产品边界和回放语义。
- 用未验证假设替代数据事实。
- 跳过测试、校验或关键验证就宣称完成。
- 为了“更完整”引入与当前任务无关的大型重构。

### 0.1.4 标准执行循环

每轮开发固定走以下闭环：

1. 对齐目标：读取当前任务与 `project.md` 对应约束。
2. 缩小问题：把任务拆成一个可验证的最小闭环。
3. 自主选路：选择当前最小风险、最高信息增益的实现路径。
4. 先证后改：能先复现、先量化、先写验证的地方，优先验证。
5. 小步提交：一次只解决一个明确问题，避免多目标混改。
6. 强制校验：运行测试、脚本、构建、对比或数据校验。
7. 回写结果：把事实变化写回 `project.md`，把过程记录写入 `progress.md`。

### 0.1.5 阶段门

为降低返工，agent 必须遵守以下阶段门，允许在门内自由探索，但不能跨门跳结论：

1. 定义门
   当前任务目标、范围、验收标准明确，才能进入实现。
2. 证据门
   问题、数据、接口、依赖、现状已核对，才能修改关键逻辑。
3. 实现门
   改动必须直接服务当前目标，不夹带顺手重构。
4. 验证门
   至少有一项真实验证结果，才能标记该阶段完成。
5. 归档门
   如果改动改变长期事实、接口、约束或阶段定义，必须更新 `project.md`。

### 0.1.6 质量门

agent 完成任务前至少通过以下质量门：

- 正确性：结果与数据、需求、边界一致。
- 可验证性：存在可重复的测试、脚本、构建或人工核对结果。
- 最小改动：没有为未来假设做额外抽象。
- 可维护性：命名、结构、注释和模块边界不制造新债务。
- 可追踪性：用户能从文档和日志里追溯为什么这样改。

### 0.1.7 低损耗策略

为了把开发损耗压到最低，默认执行以下策略：

- 先修主链路，再修边缘体验。
- 先保证数据内核和验证，再做视觉和交互。
- 先做可关闭的最小实现，再做扩展能力。
- 优先复用现有结构，不为单次需求创造新框架。
- 发现范围变大时先收口，不把一次任务拖成项目重构。

### 0.1.8 失败与回退策略

agent 遇到阻塞时按以下顺序处理：

1. 检查当前假设是否未经验证。
2. 换一种更小、更直接的验证方式。
3. 缩小任务闭环，先完成可确认部分。
4. 记录阻塞点、已尝试路径和证据。
5. 只有在无法安全假设时才向用户升级问题。

连续三次在同一路径上失败，视为路径错误，不继续机械重试。

### 0.1.9 完成判定

agent 只有同时满足以下条件，才能宣称任务完成：

- 当前任务目标已实现。
- 相关验证已运行，结果已记录。
- 若长期事实发生变化，`project.md` 已同步。
- `progress.md` 已记录做了什么、怎么验证、剩余什么风险。
- 没有把未完成事项伪装成“后续优化”。

## 1. 产品目标

本项目要实现一个本地运行的 A 股历史订单流回放分析系统。系统导入每只股票、每个交易日的 `行情.csv`、`逐笔委托.csv`、`逐笔成交.csv`，重建可回放的盘口、成交、热力图和足迹图，用浏览器多窗口方式完成复盘分析。

核心目标不是普通 K 线软件，而是：

- 逐笔事件驱动的订单簿重建。
- 基于历史挂单流动性的 Heatmap。
- 基于逐笔成交主动买卖的 Footprint。
- 与单窗口回放时钟严格绑定的 DOM、Time & Sales、Volume Profile、POC、Delta、EMA 等模块。
- 多股票、多日期、多浏览器窗口独立回放；每个窗口独立选择股票、日期、模式、周期，并独立播放、暂停、倍速、跳转。

产品验收优先级：

1. 数据标准化正确。
2. 订单簿重建不产生负数、不伪造订单。
3. 每个窗口的回放时钟不漂移，暂停、倍速、跳转只影响当前窗口。
4. Heatmap 能表现挂单出现、延续、撤单、成交冲击。
5. Footprint 能在每根 bar 内显示价格档主动买、主动卖、总量、Delta、POC。
6. UI 接近实例材料中的 ATAS 工作台布局，但不以牺牲数据正确性换取视觉效果。

## 2. 已验证输入材料

项目已有材料：

- `atas开发/订单流分析系统设计.md`：第一版需求和架构草案。
- `atas开发/READ.ME.md`：项目目标说明。
- `实例材料/heatmap.png`：ATAS 风格深色 Heatmap 参考，包含横向流动性热力带、成交气泡、当前价格线、右侧 profile/DOM 区域。
- `实例材料/足迹图放大.png`：Footprint 放大视图参考，包含价格档成交数字、买卖量列、Delta 类列、右侧成交分布。
- `实例材料/足迹图缩小，k线.png`：K 线缩小视图参考，包含 K 线、成交量、EMA 类指标、交易气泡、右侧 profile。

样例数据位于 `实例材料/600726.SH`：

| 文件 | 已验证行数 | 关键字段 |
| --- | ---: | --- |
| `行情.csv` | 5006 行含表头 | `万得代码`、`自然日`、`时间`、成交价/量/额、申卖价 1-10、申卖量 1-10、申买价 1-10、申买量 1-10 |
| `逐笔委托.csv` | 291703 行含表头 | `时间`、`委托编号`、`交易所委托号`、`委托类型`、`委托代码`、`委托价格`、`委托数量` |
| `逐笔成交.csv` | 222531 行含表头 | `时间`、`成交编号`、`BS标志`、`成交价格`、`成交数量`、`叫卖序号`、`叫买序号` |

已验证样例事实：

- 样例股票为 `600726.SH`，样例自然日为 `20260424`。
- 时间字段示例为 `91400130`、`92500400`，按 `HHMMSSmmm` 标准化为毫秒。
- 价格字段示例为 `55300`、`58000`，内部保留整数 `price_int`，展示时再按价格精度格式化。
- `逐笔委托.csv` 中 `委托类型` 至少包含 `S`、`A`；样例中 `委托代码` 包含 `I`、`B`、`S`。
- `逐笔成交.csv` 中 `成交代码`、`委托代码` 样例存在空字符，导入阶段必须清洗。
- 所有输入都必须允许 GBK/ANSI/UTF-8 探测，不得假定单一编码。

## 3. 外部依据

技术路线只采用与产品目标直接相关的成熟能力：

- Bookmap 官方说明 Heatmap 用于显示订单簿中的静态/历史流动性，亮度反映被动挂单集中程度，并可观察流动性随时间变化：[Bookmap Heatmap Overview](https://bookmap.com/learning-center/en/getting-started/liquidity-heatmap/heatmap-overview)。
- ATAS 官方说明 Footprint 基于逐笔交易数据，在每根 candle 内按价格档展示成交量、买卖主动性、最大/最小成交集中区：[ATAS Footprint Charts](https://atas.net/footprint-charts/)。
- Apache Parquet 官方说明 Parquet 是列式数据文件格式，适合高效存储和检索批量数据：[Apache Parquet Overview](https://parquet.apache.org/docs/overview/)。
- DuckDB 官方文档支持直接读取和查询 Parquet，并支持列裁剪和过滤下推：[DuckDB Parquet](https://duckdb.org/docs/lts/data/parquet/overview.html)。
- Polars 官方 `read_csv` 支持编码参数、schema 推断控制，并建议避免 `read_csv().lazy()` 这种已物化后再 lazy 的反模式：[Polars read_csv](https://docs.pola.rs/api/python/stable/reference/api/polars.read_csv.html)。
- FastAPI 官方文档支持 WebSocket endpoint，可收发文本、JSON 和二进制数据：[FastAPI WebSockets](https://fastapi.tiangolo.com/advanced/websockets/)。
- MDN 说明 `BroadcastChannel` 可在同源的不同窗口、标签页、frame 之间广播消息，适合浏览器多窗口状态同步：[MDN BroadcastChannel](https://developer.mozilla.org/en-US/docs/Web/API/BroadcastChannel)。
- Vite 官方支持 `react-ts` 模板，当前文档注明 Vite 需要 Node.js `20.19+` 或 `22.12+`：[Vite Guide](https://vite.dev/guide/)。
- SQLite 官方定位为 self-contained、serverless、zero-configuration 的事务型 SQL 引擎，适合本地保存布局、书签和回放记录：[SQLite About](https://sqlite.org/about.html)。

## 4. 产品范围

### 4.1 必须实现

- 导入多股票、多日期数据。
- 将原始 CSV 标准化为统一 schema，并缓存为 Parquet。
- 构建统一事件流：行情快照、委托新增、撤单、成交、交易阶段事件。
- 用逐笔委托和逐笔成交维护订单簿，行情 10 档作为校验锚点。
- 支持回放：播放、暂停、步进、倍速、跳转、拖拽时间轴。
- 支持两种核心图形模式：
  - Heatmap：时间 x 价格 x 历史挂单量。
  - Footprint：bar x 价格档 x 主动买卖成交量。
- 支持右侧 DOM 梯子、右侧 Volume Profile、POC。
- 支持基础技术指标：成交量、EMA、VWAP、Delta、CVD、可视区 POC。
- 支持多浏览器窗口打开同一 workspace；workspace 只保存布局和窗口状态，不提供共享播放时钟。
- 每个窗口拥有独立回放实例，可以单独播放、暂停、倍速、跳转和切换股票。
- 保存导入记录、回放历史、书签、窗口布局、最后打开状态。

### 4.2 明确不做

- 不连接实盘交易，不下单。
- 不伪造缺失订单，不用随机样例填补真实数据。
- 第一阶段不做复杂自动交易信号，不把吸收、冰山、诱单等做成硬编码结论。
- 不用 HTML DOM 大量节点绘制 Heatmap 或 Footprint 主图。
- 不在数据内核未通过校验前优先追求完整视觉复刻。

## 5. 总体架构

采用本地服务 + 浏览器前端架构：

```text
raw csv
  -> importer / normalizer
  -> standardized parquet
  -> event builder
  -> orderbook engine + validator
  -> replay engine + checkpoint
  -> FastAPI REST / WebSocket
  -> React workspace
  -> Canvas/WebGL Heatmap / Footprint / DOM / Profile
```

技术栈：

| 层 | 技术 | 职责 |
| --- | --- | --- |
| 数据导入 | Python + Polars | 编码探测、CSV 清洗、字段标准化、类型转换 |
| 分析查询 | DuckDB + Parquet | 多股票、多日期、时间段、价格档聚合查询 |
| 回放服务 | FastAPI + WebSocket | REST 查询、回放控制、状态推送 |
| 状态持久化 | SQLite | session、workspace、layout、bookmark、history |
| 前端 | React + TypeScript + Vite | 工作台、控制栏、路由、状态管理 |
| 图形渲染 | Canvas 2D / WebGL / PixiJS 备选 | Heatmap、Footprint、成交气泡、DOM 高亮 |
| 前端并行 | Web Worker / OffscreenCanvas 备选 | 大量网格计算和绘制隔离 |
| 多窗口协作 | WebSocket + BroadcastChannel | 每个窗口独立回放；仅广播布局、窗口注册、十字光标等非播放状态 |

核心原则：

- 后端逐笔处理所有事件，前端按帧批量渲染。
- 数据引擎与 UI 解耦，任何图形都必须能追溯到标准化事件和聚合结果。
- CSV 只作为导入源，回放读取 Parquet 和 checkpoint，不反复扫描原始 CSV。
- 所有价格计算使用整数 `price_int`，避免浮点价格档错位。
- 回放控制以窗口为边界，任何窗口的播放、暂停、seek、speed 不得影响其他窗口。

## 6. 数据目录设计

```text
atas回放系统/
├─ atas开发/
│  ├─ project.md
│  ├─ READ.ME.md
│  └─ 订单流分析系统设计.md
├─ 实例材料/
│  ├─ heatmap.png
│  ├─ 足迹图放大.png
│  ├─ 足迹图缩小，k线.png
│  └─ 个股数据/
│     └─ 600726.SH/
│        ├─ 行情.csv
│        ├─ 逐笔委托.csv
│        └─ 逐笔成交.csv
└─ stock_replay/
   ├─ backend/
   ├─ frontend/
   ├─ data/
   │  ├─ raw/
   │  │  └─ symbol=600726.SH/date=20260424/
   │  ├─ processed/
   │  │  └─ symbol=600726.SH/date=20260424/
   │  │     ├─ quotes.parquet
   │  │     ├─ orders.parquet
   │  │     ├─ trades.parquet
   │  │     ├─ events.parquet
   │  │     ├─ orderbook_checkpoints.parquet
   │  │     ├─ heatmap_segments.parquet
   │  │     ├─ footprint_1s.parquet
   │  │     ├─ validation_report.parquet
   │  │     └─ missing_order_report.parquet
   │  └─ app.db
   └─ logs/
      ├─ import/
      ├─ replay/
      └─ validation/
```

## 7. 标准化数据模型

### 7.1 统一字段规则

所有标准化表必须包含：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `symbol` | string | 证券代码，例如 `600726.SH` |
| `exchange_code` | string | 交易所代码，例如 `600726` |
| `trade_date` | int32 | 自然日，例如 `20260424` |
| `time_raw` | int32/int64 | 原始时间字段 |
| `ts_ms` | int64 | 当日 0 点起毫秒 |
| `session` | string | `preopen`、`auction`、`continuous_am`、`lunch`、`continuous_pm`、`close`、`unknown` |
| `seq` | int64 | 事件内稳定排序序号 |

时间转换：

```text
HHMMSSmmm -> hour * 3600000 + minute * 60000 + second * 1000 + millisecond
```

价格规则：

```text
内部：price_int = 原始整数价格
展示：display_price = price_int / price_scale
```

`price_scale` 不能硬编码为全市场固定值。导入时按样例先支持 `1000`，同时保留 symbol/date 级 metadata，未来可按数据源和品种扩展。

### 7.2 quotes.parquet

`行情.csv` 标准化结果：

| 字段 | 说明 |
| --- | --- |
| `last_price_int` | 成交价 |
| `last_qty` | 当前快照成交量 |
| `cum_qty` | 当日累计成交量 |
| `cum_amount` | 当日成交额 |
| `open_int`、`high_int`、`low_int`、`prev_close_int` | OHLC 参考 |
| `ask_price_1_int` ... `ask_price_10_int` | 卖 1-10 价格 |
| `ask_qty_1` ... `ask_qty_10` | 卖 1-10 数量 |
| `bid_price_1_int` ... `bid_price_10_int` | 买 1-10 价格 |
| `bid_qty_1` ... `bid_qty_10` | 买 1-10 数量 |

用途：

- 回放中的锚点快照。
- 订单簿重建校验。
- 初始行情区间、价格轴范围、成交量柱校准。

### 7.3 orders.parquet

`逐笔委托.csv` 标准化结果：

| 字段 | 说明 |
| --- | --- |
| `order_no` | 委托编号 |
| `exchange_order_id` | 交易所委托号，订单簿主键 |
| `order_type` | 原始委托类型；上交所样例含 `A/D/S`，深交所样例含 `0/1/U` |
| `side` | `B` 买、`S` 卖、`I/unknown` 状态或未知 |
| `price_int` | 委托价格 |
| `qty` | 委托数量 |

入簿规则：

- `A`、`0`：进入订单簿。
- `D`、`1`：按 `exchange_order_id` 从订单簿扣减或移除。
- `S`、`U`、其他无法识别类型：作为非入簿事件进入 event stream，不进入订单簿。
- 无法识别字段写入 `import_warning`，不中断全量导入。

### 7.4 trades.parquet

`逐笔成交.csv` 标准化结果：

| 字段 | 说明 |
| --- | --- |
| `trade_id` | 成交编号 |
| `aggressor_side` | `B` 主动买、`S` 主动卖、未知则 `unknown` |
| `price_int` | 成交价格 |
| `qty` | 成交数量 |
| `ask_order_id` | 叫卖序号 |
| `bid_order_id` | 叫买序号 |

清洗规则：

- 去除 `\0` 空字符。
- 空字符串、非法方向、非法价格写入 warning。
- 成交方向只用于主动买卖统计，不用于伪造盘口挂单。

### 7.5 events.parquet

统一事件流：

| 字段 | 说明 |
| --- | --- |
| `event_id` | 全局事件编号 |
| `event_type` | `quote`、`order_add`、`order_cancel`、`trade`、`session` |
| `ts_ms` | 事件时间 |
| `priority` | 同毫秒排序优先级 |
| `source_seq` | 源文件行号或源内序号 |
| `payload_ref` | 原始标准化表引用 |

同毫秒排序建议：

```text
session -> order_add/order_cancel -> trade -> quote
```

原因：

- 交易阶段先改变可交易状态。
- 委托事件先改变订单簿。
- 成交扣减订单。
- 快照最后作为校验锚点。

如果实际数据源存在更精确序号，应以交易所序号替代默认优先级。

## 8. 订单簿引擎

订单簿是系统核心。所有 DOM、Heatmap、校验、回放状态都来自订单簿引擎。

### 8.1 内存结构

```text
orders_by_id:
  exchange_order_id -> {
    side,
    price_int,
    original_qty,
    remaining_qty,
    first_ts_ms,
    last_ts_ms
  }

bid_levels:
  price_int -> total_qty

ask_levels:
  price_int -> total_qty
```

### 8.2 事件处理

新增委托：

```text
order_type = A / 0
1. 校验 exchange_order_id、side、price_int、qty。
2. 写入 orders_by_id。
3. 按 side 增加 bid_levels 或 ask_levels。
4. 生成 liquidity add delta。
```

撤单：

```text
order_type = D / 1
1. 按 exchange_order_id 查订单。
2. 找不到订单：记录 missing_cancel_order，不伪造订单。
3. 找到订单：扣减 remaining_qty，通常按撤单 qty 或剩余量取较小值。
4. 对应 price level 扣减，最小为 0。
5. 生成 liquidity cancel delta。
```

成交：

```text
event_type = trade
1. `aggressor_side = B` 时，ask_order_id 为被动侧卖单，必须扣减；bid_order_id 如果当前账本中存在则扣减，不存在不计为 missing order。
2. `aggressor_side = S` 时，bid_order_id 为被动侧买单，必须扣减；ask_order_id 如果当前账本中存在则扣减，不存在不计为 missing order。
3. 被动侧找不到订单：记录 missing_trade_order。
4. 扣减后 remaining_qty 不得小于 0。
5. level total_qty 不得小于 0。
6. 根据 aggressor_side 生成主动买/主动卖成交统计。
```

### 8.3 快照校验

`行情.csv` 的买卖 10 档不能替代逐笔重建，但必须作为校验锚点。

每个 quote 快照点执行：

```text
engine_bid10 / engine_ask10
  vs
quote_bid10 / quote_ask10
```

输出 `validation_report.parquet`：

| 字段 | 说明 |
| --- | --- |
| `ts_ms` | 快照时间 |
| `side` | bid/ask |
| `level` | 1-10 |
| `expected_price_int` | 快照价格 |
| `expected_qty` | 快照数量 |
| `actual_price_int` | 引擎价格 |
| `actual_qty` | 引擎数量 |
| `price_match` | 价格是否一致 |
| `qty_match` | 数量是否一致 |

空档位规则：

```text
quote price=0 且 qty=0
  等价于
engine 无该 level
```

另输出 `missing_order_report.parquet`：

| 字段 | 说明 |
| --- | --- |
| `reason` | missing_trade_order、missing_cancel_order、qty_shortfall、invalid_* |
| `event_id` | 对应事件编号 |
| `event_type` | 事件类型 |
| `ts_ms` | 事件时间 |
| `session` | 交易阶段 |
| `source_seq` | 源表序号 |
| `order_id` | 涉及订单号 |
| `ref_side` | trade 中引用的 ask/bid 侧 |

验收标准：

- 任何 level 数量不得为负。
- missing order 必须可统计、可导出、可定位。
- 校验报告必须能按时间段、side、level 聚合误差。
- 当误差超过阈值时 UI 显示数据可信度提示，不隐藏问题。

### 8.4 盘口复现口径

必须区分 RawBook 和 VisibleBook，避免用单一“匹配率”混淆数据质量与显示复现。

```text
RawBook:
  来源：逐笔委托、撤单、成交。
  职责：订单生命周期、成交扣减、missing order 诊断、订单流基础状态。
  约束：不得用 quote 覆盖，不得伪造 order_id。

VisibleBook:
  来源：quote top10 锚点 + quote 间逐笔事件推演。
  职责：DOM、Heatmap、回放 checkpoint 的可见盘口状态。
  约束：quote 锚定只作用于显示/回放层，不反向污染 RawBook。
```

匹配率口径：

| 指标 | 定义 | 用途 |
| --- | --- | --- |
| `raw_match_rate` | RawBook top10 vs quote top10 | 数据质量和残差诊断 |
| `quote_anchor_match_rate` | quote 锚定后的 VisibleBook vs quote top10 | quote 点可见盘口复现 |
| `inter_quote_drift` | 两个 quote 之间事件推演状态到下一个 quote 的偏差 | 衡量动画/回放连续性 |
| `correction_cost` | 每次重新锚定所需的价格层差异和数量差异 | 衡量 quote anchor 对盘口的修正成本 |

开发判断：

- 盘中 `raw_match_rate` 不作为 95%+ 验收目标。
- 盘中 95%+ 目标只适用于 VisibleBook 的 quote 锚定与 checkpoint 输出。
- Footprint、Delta、Volume Profile 的成交量基础来自 `trades.parquet`，RawBook 只提供盘口背景和订单状态辅助。
- 局部排序搜索、平滑修正窗口、复杂 correction 只能作为后续实验，不作为 P4.0 主线。

## 9. 回放引擎

Phase 4 回放引擎必须同时维护两类状态：

```text
RawBookState:
  纯逐笔重建状态，用于诊断、订单流、成交背景。

VisibleBookState:
  quote anchor 后的可见盘口状态，用于 DOM、Heatmap、checkpoint、WebSocket frame。
```

二者必须同源于标准化事件流，但边界不同：

- RawBook 处理 order/trade/cancel，不接受 quote 覆盖。
- VisibleBook 在 quote 事件处锚定到 quote top10，并记录 RawBook 与 quote 的残差。
- quote 间可用逐笔事件推动 VisibleBook 形成动画层，但到下一个 quote 必须重新锚定并记录 drift/correction。
- 任何 frame、checkpoint、DOM 或 Heatmap 数据必须标明来源是 raw、quote_anchor、event_delta 或 correction。

### 9.1 虚拟时钟

禁止用 `sleep` 累积推进回放时间。采用虚拟时钟：

```text
real_elapsed = now_monotonic - last_wall_clock
virtual_elapsed = real_elapsed * speed
current_ts_ms = min(current_ts_ms + virtual_elapsed, end_ts_ms)
```

状态模型：

| 字段 | 说明 |
| --- | --- |
| `workspace_id` | 工作区 |
| `window_id` | 窗口实例 |
| `replay_id` | 当前窗口的回放实例 |
| `clock_id` | 当前窗口的回放时钟 |
| `session_id` | 当前窗口正在回放的股票/日期 session |
| `status` | `playing`、`paused`、`seeking`、`ended` |
| `current_ts_ms` | 当前回放时间 |
| `start_ts_ms` / `end_ts_ms` | 回放范围 |
| `speed` | 倍速 |

倍速：

```text
0.1x, 0.5x, 1x, 2x, 5x, 10x, 20x, 50x, 100x
```

### 9.2 事件推进

每个 tick：

```text
1. 按 window_id / replay_id 找到当前窗口的虚拟时钟。
2. 推进该窗口的虚拟时钟。
3. 找到该窗口 current_ts_ms 之前尚未处理的事件。
4. 逐笔处理事件，更新该窗口的 orderbook。
5. 将多笔变化压缩成该窗口的 frame delta。
6. 只向当前窗口推送：clock、orderbook_top、trades、liquidity_delta、validation_status。
```

后端必须逐笔处理，前端可以 30-60 FPS 合批渲染。这样保证精度，同时避免浏览器被逐笔重绘拖慢。

多窗口隔离要求：

- `play`、`pause`、`seek`、`speed` API 必须包含 `window_id` 或 `replay_id`。
- 一个窗口暂停时，其他窗口继续按自己的状态运行。
- 一个窗口切换股票、日期、周期或图形模式时，其他窗口不重载、不跳转、不暂停。
- 后端可以复用同一 session 的只读 Parquet、checkpoint 和聚合缓存，但每个窗口的订单簿运行状态必须隔离。

### 9.3 Checkpoint

为了支持跳转和长时间多日回放，必须保存订单簿 checkpoint。

策略：

- 默认每 1 秒或 5 秒保存一个 checkpoint。
- checkpoint 至少包含 VisibleBook topN、quote anchor 信息、RawBook 残差指标和累计成交指标。
- RawBook 的 `orders_by_id` 压缩状态可以作为 seek 加速数据保存，但不得由 quote 锚定层伪造订单。
- seek 时加载目标时间之前最近 checkpoint，再重放差量事件。

验收标准：

- 跳转到任意时间不需要从开盘重新回放。
- 同一时间点重复 seek，VisibleBook top10、RawBook 残差指标和成交指标结果一致。
- checkpoint 文件可重建，不作为唯一不可恢复数据源。
- 盘中 `09:31-11:30`、`13:00-14:57` 的 quote anchor/checkpoint 可见盘口匹配率应达到 95%+。

## 10. Heatmap 设计

### 10.1 目标

Heatmap 表达：

```text
时间 x 价格 x 挂单量/流动性强度
```

必须显示：

- 历史挂单横向延续。
- 大挂单区域。
- 快速撤单区域。
- 成交冲击气泡。
- 当前价格线。
- 右侧当前 DOM。
- 右侧可视区 Volume Profile / POC。

### 10.2 数据结构

```text
LiquiditySegment:
  symbol
  trade_date
  side
  price_int
  start_ts_ms
  end_ts_ms
  qty
  add_qty
  cancel_qty
  trade_qty
  intensity
```

关键点：

- 不能只存 `time, price, qty`。
- 挂单数量在价格档不变时必须形成 `start_ts_ms -> end_ts_ms` 的横向段。
- 当该价格档数量变化时关闭旧段，开启新段。

### 10.3 颜色

强度计算：

```text
base = log1p(qty)
intensity = percentile_normalize(base, current_session_or_visible_range)
```

默认色阶：

| 分位区间 | 颜色语义 |
| --- | --- |
| 0-30% | 深蓝，低流动性 |
| 30-55% | 蓝色，中低流动性 |
| 55-75% | 青蓝，明显流动性 |
| 75-90% | 橙色，大挂单 |
| 90-97% | 黄色，强流动性 |
| 97-100% | 红色，极强流动性 |

叠加层：

- `add_qty`：轻微增亮。
- `cancel_qty`：短暂紫/灰边缘或透明度衰减。
- `trade_qty`：红/绿成交气泡。
- 当前价：横向高对比线。

### 10.4 渲染策略

主图使用 Canvas/WebGL，不使用普通 DOM 网格。

层级：

```text
1. background grid
2. historical liquidity segments
3. current active liquidity extension
4. trade bubbles
5. price line / crosshair
6. selected range overlay
7. visible range volume profile
8. DOM panel
```

性能要求：

- 可视区段裁剪，只渲染当前视口时间和价格范围。
- 历史段按 price bucket 和 time tile 分块。
- 缩放和平移不触发后端全量重算。
- 前端 worker 负责把 segment 转为绘制命令。

## 11. Footprint 设计

### 11.1 目标

Footprint 表达：

```text
每根 bar 内，每个价格档的主动买量、主动卖量、总量、Delta、POC、Imbalance。
```

参考 `足迹图放大.png`，Footprint 主体需要显示：

- 每根 bar 的价格档成交数字。
- Bid x Ask 双列或 Delta 模式。
- 每根 bar 内 POC 高亮。
- 低/高成交区背景。
- 右侧可视区成交量分布。
- 当前价、时间游标、bar 边界。

### 11.2 数据结构

```text
FootprintBar:
  symbol
  trade_date
  interval
  start_ts_ms
  end_ts_ms
  open_int
  high_int
  low_int
  close_int
  total_volume
  buy_volume
  sell_volume
  delta
  cumulative_delta
  poc_price_int
  vah_price_int
  val_price_int
  levels:
    price_int -> {
      buy_volume
      sell_volume
      total_volume
      delta
      imbalance
    }
```

主动方向：

```text
aggressor_side = B -> buy_volume += qty
aggressor_side = S -> sell_volume += qty
delta = buy_volume - sell_volume
```

### 11.3 周期切换

第一阶段支持：

```text
1s, 3s, 5s, 15s, 1min, 3min, 5min
```

扩展阶段支持：

```text
N 笔成交, N 手成交, N 成交额, range bar
```

实现原则：

- 先预聚合 `footprint_1s.parquet`。
- 时间周期由 1s 聚合快速合成。
- 切换周期不重新读取原始 CSV。
- 非时间 bar 单独用 trade stream 构建，不混入时间 bar 逻辑。

## 12. DOM 与 Time & Sales

### 12.1 DOM

DOM 来自当前回放订单簿：

```text
DomLevel:
  price_int
  bid_qty
  ask_qty
  recent_bid_add
  recent_ask_add
  recent_bid_cancel
  recent_ask_cancel
  recent_buy_trade
  recent_sell_trade
```

显示列：

```text
Ask Cancel | Ask Add | Ask Qty | Price | Bid Qty | Bid Add | Bid Cancel
```

首版可简化为：

```text
Ask Qty | Price | Bid Qty
```

并用背景条表达新增、撤单、成交冲击。

### 12.2 Time & Sales

字段：

| 字段 | 说明 |
| --- | --- |
| `ts_ms` | 成交时间 |
| `price_int` | 成交价格 |
| `qty` | 成交数量 |
| `aggressor_side` | 主动买/主动卖 |
| `trade_id` | 成交编号 |
| `ask_order_id` / `bid_order_id` | 对手订单引用 |

支持：

- 大单过滤。
- 主动买卖颜色。
- 跟随回放时间滚动。
- 点击成交定位 Heatmap/Footprint 上对应位置。

## 13. 指标系统

指标分三类。

### 13.1 价格与成交量指标

- K 线 OHLC。
- 成交量柱。
- EMA。
- SMA。
- VWAP。

### 13.2 订单流指标

- Buy Volume。
- Sell Volume。
- Delta。
- Cumulative Delta。
- 主动买卖比。
- 大单成交气泡。
- 每 bar 最大主动买/卖价格。

### 13.3 Profile 指标

- Session Volume Profile。
- Visible Range Volume Profile。
- Footprint bar 内 POC。
- 可视区 POC。
- VAH / VAL。

必须区分：

```text
bar_poc: 单根 Footprint bar 内最大成交价格
visible_poc: 当前可视区最大成交价格
session_poc: 当前交易日/连续区间最大成交价格
```

## 14. 多股票、多日期、多窗口

统一开发口径：

- 多窗口不是共享播放时间轴。
- Workspace 是布局容器，不是全局播放器。
- Window 是播放控制边界，每个 window 拥有自己的 `replay_id`、`clock_id`、`session_id`、`current_ts_ms`、`speed`、`status`。
- 不实现“一个窗口播放，其他窗口自动跟随同一时间”的默认行为。
- 允许多个窗口同时回放不同股票，也允许多个窗口回放同一股票的不同日期、不同周期、不同时间点。
- 多窗口之间只同步非破坏性 UI 辅助信息，例如窗口注册、布局变更、主题、十字光标广播、选区标注；播放状态不广播。

### 14.1 Session

```text
Session:
  session_id
  symbols[]
  trade_dates[]
  mode: continuous | aligned
  start_ts_ms
  end_ts_ms
```

连续回放：

```text
600726.SH 20260422 -> 20260423 -> 20260424
global_ts = day_index * trading_session_duration + ts_from_session_open
```

同时间对齐：

```text
600726.SH 20260424 09:30:00
600000.SH 20260424 09:30:00
000001.SZ 20260424 09:30:00
```

对齐键：

```text
trading_time_ms = ts_ms - session_open_ts_ms
```

### 14.2 Workspace

```text
Workspace:
  workspace_id
  name
  windows[]
  panels[]
  layout_json
  last_state
```

窗口状态：

```text
WorkspaceWindow:
  window_id
  workspace_id
  replay_id
  symbol
  trade_date
  mode
  interval
  current_ts_ms
  speed
  status
  viewport_json
  panel_state_json
```

窗口模式：

- `heatmap`
- `footprint`
- `dom`
- `kline`
- `workspace`

URL 示例：

```text
/replay?workspace=main&symbol=600726.SH&date=20260424&mode=heatmap
/replay?workspace=main&symbol=600726.SH&date=20260424&mode=footprint&interval=3s
/replay?workspace=main&symbol=600726.SH&date=20260424&mode=dom
```

多窗口策略：

- WebSocket 连接按 `window_id` 建立，服务端只向该窗口推送该窗口的回放 frame。
- BroadcastChannel 仅用于同源窗口间同步 UI 辅助状态，例如 workspace layout、窗口打开/关闭、主题、十字光标、选区。
- 播放控制命令不通过 BroadcastChannel 广播给其他窗口。
- 每个窗口的播放状态独立持久化，关闭重开只恢复该窗口自己的 `current_ts_ms`、`speed`、`status`、`symbol`、`trade_date`、`mode`、`interval`。

## 15. 后端模块

```text
backend/
├─ app.py
├─ config.py
├─ importer.py
├─ encoding.py
├─ normalizer.py
├─ event_builder.py
├─ orderbook_engine.py
├─ checkpoint_store.py
├─ validator.py
├─ replay_engine.py
├─ heatmap_builder.py
├─ footprint_builder.py
├─ profile_builder.py
├─ indicator_engine.py
├─ storage.py
├─ schemas.py
├─ api/
│  ├─ import_routes.py
│  ├─ session_routes.py
│  ├─ replay_routes.py
│  ├─ heatmap_routes.py
│  ├─ footprint_routes.py
│  └─ workspace_routes.py
└─ tests/
```

模块职责：

| 模块 | 职责 |
| --- | --- |
| `importer.py` | 接收文件、识别 symbol/date、落 raw data |
| `encoding.py` | 编码探测、BOM/空字符处理 |
| `normalizer.py` | 字段映射、类型转换、price/time 标准化 |
| `event_builder.py` | 合并 quote/order/trade/session 为稳定事件流 |
| `orderbook_engine.py` | 逐笔维护订单簿 |
| `validator.py` | 用 quote top10 校验订单簿 |
| `checkpoint_store.py` | checkpoint 写入、读取、压缩 |
| `replay_engine.py` | 按窗口隔离的虚拟时钟、倍速、seek、WebSocket 推送 |
| `heatmap_builder.py` | liquidity segment 生成和切片查询 |
| `footprint_builder.py` | 1s 聚合和周期合成 |
| `profile_builder.py` | volume profile、POC、VAH、VAL |
| `indicator_engine.py` | EMA、VWAP、Delta、CVD |
| `storage.py` | SQLite 元数据、历史、书签、布局 |

## 16. 前端模块

```text
frontend/
├─ src/
│  ├─ app/
│  ├─ api/
│  ├─ pages/
│  │  ├─ WorkspacePage.tsx
│  │  ├─ HeatmapPage.tsx
│  │  ├─ FootprintPage.tsx
│  │  └─ DomPage.tsx
│  ├─ components/
│  │  ├─ TopToolbar.tsx
│  │  ├─ ReplayControl.tsx
│  │  ├─ SymbolDatePicker.tsx
│  │  ├─ HeatmapCanvas.tsx
│  │  ├─ FootprintCanvas.tsx
│  │  ├─ DomLadder.tsx
│  │  ├─ VolumeProfile.tsx
│  │  ├─ TimeSales.tsx
│  │  └─ StatusBar.tsx
│  ├─ workers/
│  │  ├─ heatmap.worker.ts
│  │  └─ footprint.worker.ts
│  ├─ stores/
│  │  ├─ replayStore.ts
│  │  ├─ workspaceStore.ts
│  │  └─ chartStore.ts
│  ├─ render/
│  │  ├─ scales.ts
│  │  ├─ heatmapRenderer.ts
│  │  ├─ footprintRenderer.ts
│  │  └─ profileRenderer.ts
│  └─ types/
```

界面布局：

```text
顶部：当前窗口的股票/日期/session 选择、模式切换、周期切换、播放控制、倍速、数据状态
左侧：工具栏、光标、缩放、绘图辅助
中间：Heatmap / Footprint / Kline 主图区
右侧：DOM、当前价、Volume Profile、POC
底部：成交量、Delta、CVD、Time & Sales、时间轴
```

交互要求：

- 鼠标滚轮缩放价格轴和时间轴。
- 拖拽平移。
- 十字光标显示时间、价格、成交、挂单量。
- 点击成交气泡定位 Time & Sales。
- 切换当前窗口的 symbol/date/interval 不影响其他窗口，不丢失工作区布局。
- 数据校验异常在状态栏明确显示。

## 17. API 设计

### 17.1 Import

```text
POST /api/import/session
```

输入：

```json
{
  "symbol": "600726.SH",
  "trade_date": 20260424,
  "files": {
    "quotes": "行情.csv",
    "orders": "逐笔委托.csv",
    "trades": "逐笔成交.csv"
  }
}
```

输出：

```json
{
  "session_id": "600726.SH-20260424",
  "rows": {
    "quotes": 5005,
    "orders": 291702,
    "trades": 222530
  },
  "warnings": [],
  "status": "imported"
}
```

### 17.2 Session

```text
GET /api/sessions
GET /api/sessions/{session_id}/summary
GET /api/sessions/{session_id}/validation
```

### 17.3 Replay

```text
POST /api/replay/{workspace_id}/{window_id}/load
POST /api/replay/{workspace_id}/{window_id}/play
POST /api/replay/{workspace_id}/{window_id}/pause
POST /api/replay/{workspace_id}/{window_id}/seek
POST /api/replay/{workspace_id}/{window_id}/speed
WS   /api/replay/{workspace_id}/{window_id}/stream
```

WebSocket frame：

```json
{
  "type": "frame",
  "workspace_id": "main",
  "window_id": "heatmap-1",
  "replay_id": "replay-600726-20260424-heatmap-1",
  "session_id": "600726.SH-20260424",
  "current_ts_ms": 33900400,
  "speed": 1,
  "status": "playing",
  "orderbook_top": {
    "bids": [],
    "asks": []
  },
  "trades": [],
  "liquidity_delta": [],
  "validation_status": "ok"
}
```

### 17.4 Chart Data

```text
GET /api/heatmap?session_id=&start=&end=&price_min=&price_max=&bucket_ms=
GET /api/footprint?session_id=&start=&end=&interval=
GET /api/profile?session_id=&start=&end=&price_min=&price_max=
GET /api/dom?session_id=&ts_ms=&depth=
GET /api/time-sales?session_id=&start=&end=&min_qty=
```

### 17.5 Workspace

```text
GET  /api/workspaces
POST /api/workspaces
GET  /api/workspaces/{workspace_id}
PUT  /api/workspaces/{workspace_id}
POST /api/bookmarks
GET  /api/history
```

## 18. SQLite 元数据

表：

```text
symbols
sessions
imports
workspaces
workspace_windows
bookmarks
replay_history
validation_runs
app_settings
```

关键字段：

```text
sessions:
  session_id, symbol, trade_date, price_scale, raw_path, processed_path,
  imported_at, import_status, quote_rows, order_rows, trade_rows

workspaces:
  workspace_id, name, layout_json, last_state_json, updated_at

workspace_windows:
  window_id, workspace_id, replay_id, session_id, symbol, trade_date,
  mode, interval, current_ts_ms, speed, status, viewport_json,
  panel_state_json, updated_at

bookmarks:
  bookmark_id, workspace_id, window_id, session_id, ts_ms, note, viewport_json, created_at

validation_runs:
  run_id, session_id, generated_at, mismatch_count, missing_order_count, report_path
```

## 19. 开发路线

### Phase 1：项目骨架与数据导入

目标：

- 建立 backend/frontend/data 目录。
- 实现 CSV 编码探测、空字符清洗、字段映射。
- 输出 quotes/orders/trades 三类标准化 Parquet。

验收：

- 可导入 `实例材料/个股数据/600726.SH`。
- 输出行数与原始文件一致减表头。
- `time_raw`、`ts_ms`、`price_int`、`symbol`、`trade_date` 正确。
- 导入 warning 可查看。

### Phase 2：事件流与订单簿引擎

目标：

- 构建 `events.parquet`。
- 实现 `OrderBookEngine`。
- 支持新增、撤单、成交扣减。

验收：

- 任意事件处理后 bid/ask level 不为负。
- missing order 有日志。
- 可在指定时间输出 top10。

### Phase 3：行情快照校验

目标：

- 用 `行情.csv` 的买卖 10 档校验引擎 top10。
- 输出 validation report 和 missing order report。
- 拆分并固定 `raw_match_rate`、`quote_anchor_match_rate`、`inter_quote_drift`、`correction_cost` 等指标口径。
- 对盘中 `09:31-11:30`、`13:00-14:57` 单独统计 raw 残差，证明后续优化目标是否应进入 VisibleBook。

验收：

- 可统计 price mismatch、qty mismatch、missing order。
- 可定位具体 ts、side、level。
- missing order 可按 reason、session、source_seq、event_id 定位。
- UI 或 CLI 能展示校验摘要。
- 不把 raw book 强行调到 95% 作为 P3 验收。
- P3 结束时必须明确哪些问题属于 raw 数据残差，哪些问题进入 P4 的 visible replay/checkpoint。

### Phase 4：回放服务

目标：

- 新增 VisibleBook 层，quote 到来时锚定为可见盘口状态。
- 输出 visible/checkpoint 数据和 RawBook residual/correction 成本。
- 实现虚拟时钟、播放、暂停、倍速、seek。
- 实现 checkpoint。
- 实现 WebSocket frame 推送。
- 回放状态按 `window_id` 隔离。

验收：

- RawBook 不被 quote 覆盖，不伪造 order_id。
- 盘中 `09:31-11:30`、`13:00-14:57` 的 VisibleBook quote anchor/checkpoint 匹配率达到 95%+。
- 每个 checkpoint 可追溯来源：quote_anchor、event_delta、correction 或 raw diagnostic。
- 记录 `inter_quote_drift` 与 `correction_cost`，不把 quote 点 100% 对齐伪装成完整真实盘口。
- 同一 ts 重复 seek 输出一致。
- 100x 回放不阻塞 UI。
- seek 不从开盘全量重放。
- 窗口 A 播放、暂停、seek、调速、切换股票时，窗口 B 的状态不变化。

### Phase 5：Heatmap 与 DOM 首版

目标：

- 生成 liquidity segment。
- Canvas/WebGL 绘制 heatmap。
- DOM 显示当前订单簿。
- 成交气泡叠加。

验收：

- 挂单变化能横向延续。
- 大挂单颜色有分位强度。
- 撤单和成交冲击可区分。
- DOM 与当前回放时间一致。

### Phase 6：Footprint 首版

目标：

- 构建 1s footprint 聚合。
- 支持 1s、3s、5s、1min、3min。
- 显示 Bid x Ask、Delta、bar POC。

验收：

- 每根 bar 的 buy/sell/total/delta 可复算。
- 周期切换不重新读 CSV。
- 可视区 Volume Profile 与当前时间区间一致。

### Phase 7：工作台、多窗口与保存

目标：

- Workspace 页面。
- 多窗口打开。
- BroadcastChannel 同步非播放 UI 状态。
- 保存布局、书签、历史。

验收：

- 每个窗口可以选择不同股票、日期、模式和周期。
- 每个窗口可以单独播放、暂停、倍速、seek。
- 一个窗口播放或暂停时，其他窗口不跟随、不暂停、不跳转。
- 关闭重开后恢复 layout 和最后状态。

### Phase 8：指标与体验完善

目标：

- EMA、VWAP、成交量、CVD、visible/session POC。
- 完整交互：缩放、平移、十字光标、选区。
- 性能优化和错误提示。

验收：

- 长时间回放无明显内存增长。
- 切换股票/日期/周期有加载状态和错误提示。
- 指标结果有单元测试或可复算脚本。

## 20. 测试策略

### 20.1 单元测试

- 时间解析：`HHMMSSmmm -> ts_ms`。
- 价格格式：`price_int` 与展示价格。
- 编码和空字符清洗。
- 委托新增、撤单、成交扣减。
- Delta、POC、Volume Profile 计算。

### 20.2 数据回归测试

使用 `实例材料/600726.SH` 作为固定回归集：

- 导入行数。
- 标准化 schema。
- event 排序稳定性。
- top10 校验摘要。
- footprint 聚合量守恒。

### 20.3 回放一致性测试

- 从开盘播放到目标时间，与 checkpoint seek 到同一时间的订单簿一致。
- 1x、10x、100x 到同一时间输出一致。
- 当前窗口暂停后不推进该窗口虚拟时间，其他窗口不受影响。

### 20.4 前端视觉测试

- Heatmap 非空、价格轴/时间轴不重叠。
- Footprint 数字不溢出 cell。
- DOM 与主图价格线对齐。
- 多窗口独立播放时互不干扰；非播放 UI 状态同步延迟可接受。

## 21. 性能指标

首版性能目标：

- 导入 1 个交易日 50 万级事件可在本地可接受时间内完成，并生成 Parquet 缓存。
- 回放 100x 时后端不丢事件。
- 前端主图维持可交互，不因逐笔事件直接重绘卡死。
- seek 到任意秒级位置在 checkpoint 存在时快速完成。

工程约束：

- 查询只读取必要列和必要时间范围。
- 长历史 Heatmap 分 tile 加载。
- 主图渲染不创建大量 React 节点。
- WebSocket frame 有节流和合批。
- 后端日志和 warning 可控，不在高频回放路径同步写大量文本。

## 22. 风险与处理

| 风险 | 影响 | 处理 |
| --- | --- | --- |
| 逐笔委托/成交与行情快照无法完全对齐 | 订单簿误差 | 输出 validation report，使用快照作为锚点，不隐藏误差 |
| 部分成交找不到对应订单号 | 成交扣减不完整 | 记录 missing_trade_order，不伪造订单；指标仍可基于成交流计算 |
| 数据编码和空字符异常 | 导入失败或字段污染 | 编码探测、空字符清洗、保留 raw warning |
| 多日连续回放数据量大 | 内存和 seek 压力 | Parquet 分区、checkpoint、视口查询 |
| Heatmap 视觉数据过密 | 浏览器卡顿 | tile 裁剪、分位归一化、worker 合批、Canvas/WebGL |
| Footprint 缩放后文字溢出 | 可读性下降 | 根据 cell 尺寸切换数字/色块/摘要模式 |

## 23. 首个可交付 MVP

MVP 不做完整工作台，先证明数据内核和两种图形可用。

MVP 内容：

1. 导入 `600726.SH/20260424` 三个 CSV。
2. 输出标准化 Parquet。
3. 构建事件流。
4. 重建订单簿并生成校验报告。
5. 支持回放播放、暂停、倍速、seek。
6. Heatmap 显示历史流动性段、当前价格、成交气泡、右侧 DOM。
7. Footprint 显示 1s/3s/1min bar 的 Bid x Ask、Delta、POC。
8. 保存一次回放历史和书签。

MVP 通过后，再扩展多股票、多日期、完整多窗口 workspace；多窗口扩展必须坚持窗口独立播放口径。

## 24. 完成定义

系统完成不是指页面能显示几张图，而是满足以下条件：

- 任意可视元素都能追溯到标准化数据或订单簿状态。
- 原始 CSV 导入、标准化、事件排序、订单簿重建、校验报告全链路可重复。
- 单个窗口内的回放时钟、订单簿状态、Heatmap、Footprint、DOM 在该窗口同一 `current_ts_ms` 下语义一致。
- 多窗口可以显示不同股票、日期、模式、周期和时间点；窗口之间播放状态互不影响。
- 遇到缺失订单、快照不匹配、编码异常时系统明确报告，不静默吞掉。

开发时始终按以下顺序推进：

```text
数据标准化 -> 事件流 -> 订单簿 -> 校验 -> 回放 -> Heatmap -> Footprint -> 多窗口 -> 指标完善
```
