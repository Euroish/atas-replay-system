**You:**

盘中匹配率优化分析.md
文件
To https://github.com/Euroish/atas-replay-system.git
   03f4314..b9f4ecc  main -> main，根据当前状态，给出codex指导意见

* * *

**ChatGPT:**

我先按这次 `03f4314..b9f4ecc` 的变更和仓库当前代码来判断，不只给泛泛建议；重点会落到 Codex 下一轮应该怎么继续改、哪些方向先不要碰。

* * *

**ChatGPT:**

当前提交只新增了“残差诊断”相关能力：一个新诊断模块、对应测试，以及 findings/progress/task_plan 文档更新。下一步 Codex 不应直接冲 UI，而应先把诊断结果转成 P4 的可见盘口内核。

* * *

**ChatGPT:**

当前 `b9f4ecc` 的状态判断：**P3/P3.6 已经完成“残差可测量、可定位、可复现”，但还没有进入真正提升盘中匹配率的 P4 内核。** 这次提交主要新增 `residual_diagnostics.py`、测试和文档更新；结果仍然明确写着没有实现 continuous quote-overwrite anchoring、replay clock、UI 或 Phase 4 工作。[](https://github.com/Euroish/atas-replay-system/commit/b9f4ecc397347a1cd5bb255359eee29111276e3b)

[update phase 3](https://github.com/Euroish/atas-replay-system/commit/b9f4ecc397347a1cd5bb255359eee29111276e3b)

现在 Codex 下一轮不要继续在 `OrderBookEngine` 里硬修 raw book。当前 `event_builder.py` 仍然按 `session -> order_add/order_cancel -> trade -> quote` 排序，`validator.py` 仍是在每个 quote 点用 RawBook top10 对比快照，`orderbook_engine.py` 也只维护订单级 RawBook，没有可见盘口锚定层。[](https://github.com/Euroish/atas-replay-system/blob/main/stock_replay/backend/stock_replay_backend/event_builder.py)

[event_builder](https://github.com/Euroish/atas-replay-system/blob/main/stock_replay/backend/stock_replay_backend/event_builder.py)

[

validator

](https://github.com/Euroish/atas-replay-system/blob/main/stock_replay/backend/stock_replay_backend/validator.py)[

orderbook_engine

](https://github.com/Euroish/atas-replay-system/blob/main/stock_replay/backend/stock_replay_backend/orderbook_engine.py)

你上传的分析结论也一致：**真正到盘中 95%+，应转向 VisibleBook / quote anchor，而不是强行要求 raw_match_rate 到 95%。**

盘中匹配率优化分析

## 给 Codex 的直接指导意见

复制下面这段给 Codex：

```
当前 main 已到 b9f4ecc，Phase 3.6 residual diagnostics 已完成。下一步不要继续把 raw OrderBookEngine 硬调到 95%，也不要做 UI / heatmap / DOM 前端。目标进入 Phase 4.0：VisibleBook 快照锚定与盘口 checkpoint。

核心原则：
1. RawBook 继续保持纯逐笔委托/撤单/成交重建，不要用 quote 覆盖 RawBook，不要伪造 order_id。
2. 新增 VisibleBookEngine，专门用于盘中盘口显示、DOM、heatmap、回放 checkpoint。
3. 在每个 quote 事件处，用 quote 的 ask1-ask10 / bid1-bid10 锚定 VisibleBook。
4. RawBook vs Quote 继续作为 raw_match_rate 诊断指标保留。
5. VisibleBook vs Quote 新增 visible_match_rate，目标盘中 09:31-11:30、13:00-14:57 >= 95%。
6. 集合竞价暂时不要作为优化重点，只要不破坏现有 opening_alignment_report 即可。

需要实现：
- 新增 stock_replay/backend/stock_replay_backend/visible_book_engine.py
- 新增 visible/checkpoint 生成逻辑，可以先命名为 visible_book_builder.py 或 replay_checkpoint_builder.py
- 输出 orderbook_checkpoints.parquet 或 visible_book_checkpoints.parquet
- 新增 visible_validation_report.parquet
- 新增 summary 字段：
  raw_match_rate
  visible_match_rate
  raw_mismatch_count
  visible_mismatch_count
  anchor_count
  correction_count
  correction_qty_abs
  continuous_am_visible_match_rate
  continuous_pm_visible_match_rate

VisibleBookEngine 最小能力：
- anchor_from_quote(quote_row): 直接从 quote top10 建立 bid_levels / ask_levels
- snapshot_top_levels(depth=10): 返回当前可见盘口
- compare_to_quote(quote_row): 校验 visible book 和 quote 是否一致
- record_correction(raw_snapshot, quote_snapshot): 记录 RawBook 与 quote 的差异，但不要修改 RawBook

Phase 4.0 第一版不要做复杂平滑，不要做局部排序搜索，不要做 UI。
第一版只做“quote 点可见盘口准确复现”：
- 每个 quote 到来时：
  1. RawBook 正常 apply 非 quote 事件
  2. 计算 RawBook vs Quote 的 raw mismatch
  3. VisibleBook anchor_from_quote
  4. 计算 VisibleBook vs Quote 的 visible mismatch
  5. 写 checkpoint

验收：
- 保持现有 tests 全通过
- 新增 VisibleBookEngine 单元测试
- 新增 checkpoint/visible validation 测试
- 运行：
  cd stock_replay/backend
  ..\.venv\Scripts\python.exe -m pytest
- 运行全样本 import / diagnostics 后确认：
  09:31-11:30 visible_match_rate >= 95%
  13:00-14:57 visible_match_rate >= 95%
  raw_match_rate 可继续保持当前 80%+，不要把 raw_match_rate 当成 Phase 4 成败指标
- findings.md / progress.md / task_plan.md 必须更新，明确 Phase 4.0 已开始，且 RawBook 未被 quote 覆盖。
```

## 下一轮优先级

最高优先级是：

```
P4.0 = VisibleBook + quote anchor + visible_match_rate
```

不是：

```
继续修 raw_match_rate
局部排序搜索
heatmap 颜色
DOM 速度
前端复刻 ATAS
```

原因很简单：当前文档已经明确 P3.6 只做诊断，不做 replay clock、checkpoint、quote-overwrite anchoring。[](https://github.com/Euroish/atas-replay-system/blob/main/task_plan.md)

[task_plan](https://github.com/Euroish/atas-replay-system/blob/main/task_plan.md)

而 findings 也写明 Phase 3.5 / 3.6 后 mismatch 仍为 `188276`，missing_order 为 `87841`，且当前任务没有实现 quote-overwrite anchoring，只建议未来 visible-book layer 使用 quote 作为显示锚点。[

findings

](https://github.com/Euroish/atas-replay-system/blob/main/findings.md)

## Codex 不要做的事

不要让 Codex 做这些：

```
1. 不要直接把 quote 覆盖进 OrderBookEngine
2. 不要给 RawBook 生成假 order_id
3. 不要为了匹配率删除 missing_order_report
4. 不要把 visible_match_rate 冒充 raw_match_rate
5. 不要现在做 heatmap UI
6. 不要现在做局部排序搜索作为主线
7. 不要回头重构 Phase 3.6 diagnostics
```

## 最终判断

现在的正确路线是：

```
Phase 3.6：残差诊断完成
Phase 4.0：VisibleBook 快照锚定
Phase 4.1：checkpoint 输出
Phase 4.2：quote 间盘口连续推进
Phase 5：heatmap / DOM / footprint 前端
```

所以给 Codex 的核心话术就是：

```
从 b9f4ecc 开始，不再把 95% 目标压给 RawBook。
新建 VisibleBook 层，用 quote anchor 做盘中可见盘口复现。
RawBook 保持诊断和成交/footprint 基础。
验收指标改为 visible_match_rate >= 95%，raw_match_rate 继续保留为数据质量指标。
```

* * *

**You:**

保持客观中立，我给你的md里面是否存在偏离或者影响开发的设计，有无更好更优路径，分析查询有关资料

* * *

**ChatGPT:**

我会按“是否会影响后续开发正确性”来评估这份 md，而不是只判断它写得对不对。重点看三类：目标口径、架构边界、算法优先级。

* * *

**ChatGPT:**

初步判断：md 的大方向没有明显跑偏，但里面有几处如果直接交给 Codex 实现，会把“指标达标”误当成“回放真实”。我会把这些点拆成“正确、风险、替代方案”。

* * *

**ChatGPT:**

客观结论：**你给的 md 大方向是对的，但有几处表述如果直接让 Codex 执行，确实可能影响开发路线。**  
它最大的问题不是“错”，而是容易把 **quote 点对齐** 误认为 **完整盘口真实复现**。

---

## 1. md 中正确的部分

### 正确点 1：不要继续强行追 raw_match_rate 95%

这个判断基本正确。

你当前代码里，`event_builder.py` 是按：

```Python
ts_ms -> priority -> source_seq
```

排序，其中 quote 优先级最后，也就是同毫秒内默认：

```
order / cancel -> trade -> quote
```

[](https://github.com/Euroish/atas-replay-system/blob/main/stock_replay/backend/stock_replay_backend/event_builder.py)

[event_builder](https://github.com/Euroish/atas-replay-system/blob/main/stock_replay/backend/stock_replay_backend/event_builder.py)

`OrderBookEngine` 当前维护的是订单级别的：

```Python
orders
bid_levels
ask_levels
```

它不会用 quote 修复盘口。[](https://github.com/Euroish/atas-replay-system/blob/main/stock_replay/backend/stock_replay_backend/orderbook_engine.py)

[orderbook_engine](https://github.com/Euroish/atas-replay-system/blob/main/stock_replay/backend/stock_replay_backend/orderbook_engine.py)

`validator.py` 又是在每个 quote 点拿 RawBook top10 和 quote top10 比较。[](https://github.com/Euroish/atas-replay-system/blob/main/stock_replay/backend/stock_replay_backend/validator.py)

[validator](https://github.com/Euroish/atas-replay-system/blob/main/stock_replay/backend/stock_replay_backend/validator.py)

所以现在的 raw 匹配率本质是：

```
纯逐笔事件重建盘口 vs 十档快照
```

在数据源不是完整 L3、时间戳不是严格撮合顺序、存在非展示订单/主动单缺失时，raw book 很难稳定 95%。md 里说“raw_match_rate 不应强行追 95%”，这个判断合理。

盘中匹配率优化分析

---

### 正确点 2：RawBook 和 VisibleBook 分层是必要的

md 里建议：

```
RawBook：负责逐笔成交、footprint、delta、volume profile
VisibleBook：负责十档盘口、DOM、heatmap、quote 对齐
```

这个方向是合理的。

盘中匹配率优化分析

市场数据重建里，完整 L3/MBO 通常需要完整订单生命周期、order_id、add/cancel/modify/fill 等事件。Databento 对 MBO 的定义就是“每个订单簿事件 across every price level，keyed by order ID”，用于最高粒度的订单簿重建。[Databento](https://databento.com/docs/schemas-and-data-formats/mbo?utm_source=chatgpt.com)

但你的数据现在更像：

```
逐笔委托 / 逐笔成交 / 十档快照 混合源
```

不是严格完整、严格排序、无缺失的 MBO 流。所以引入 quote anchor 作为显示层锚点是合理路线。

---

## 2. md 中可能偏离开发的地方

### 风险点 1：“VisibleBook quote anchor 后匹配率 99%”这个说法容易误导

md 里说：

```
这一步做完，盘中 quote 点匹配率理论上可以到 99% 左右，因为 display book 直接对齐 quote。
```

这个说法技术上没错，但**指标意义偏弱**。因为如果每个 quote 点都直接用 quote 覆盖 VisibleBook，那么 quote 点匹配率接近 100% 是必然结果，不代表回放过程真实。

真正要区分两个指标：

```
quote_point_match_rate：quote 点本身是否对齐
between_quote_replay_quality：两个 quote 之间的盘口变化是否合理
```

更好的目标不是简单写：

```
visible_match_rate >= 95%
```

而是写成：

```
quote_anchor_match_rate >= 99%
inter_quote_drift 可测量
anchor_correction_qty 可解释
correction 不反向污染 RawBook
```

否则 Codex 可能做出一个“每个 quote 点强行覆盖”的系统，指标很好看，但 heatmap 中间过程不可信。

---

### 风险点 2：correction layer 用 `raw_qty + correction_qty` 可能不稳

md 里提出：

```
raw_level_qty + correction_qty = visible_level_qty
```

这个思路可以作为诊断，但不建议作为核心数据结构。

原因是盘口不是固定 level 的线性修正。比如 raw 的 bid1 价格和 quote 的 bid1 价格都不同，问题不只是数量差，而是：

```
价格层级错位
level 顺序变化
某个价位缺失
某个价位多出
top10 被错误价位挤占
```

这时候用：

```
raw level 1 + correction = quote level 1
```

容易制造假连续性。

更稳的结构应该是：

```
VisibleBook = QuoteAnchorState + EventDeltaTape + ResidualCorrectionLog
```

也就是：

```
quote 点：直接锚定成官方十档状态
quote 之间：用逐笔事件生成动画变化
到下一个 quote：记录偏差并重新锚定
```

不要把 correction 当成长期挂在 raw level 上的补丁。

---

### 风险点 3：“局部排序搜索”不应该太早进入主线

md 里建议局部排序搜索：

```
quote.ts_ms ± 200ms
多种事件顺序模拟
选择 mismatch 最小的顺序
```

这个方向可以做研究，但不建议作为 P4 主线。

原因是它有数据拟合风险：你是用 quote 结果反推事件顺序，容易把系统变成“为了匹配 quote 而重排历史”。如果没有交易所 sequence、channel sequence、撮合引擎 timestamp 级别证据，局部排序搜索只能作为：

```
diagnostic experiment
offline sensitivity test
raw improvement experiment
```

不能作为生产回放的默认逻辑。

dxFeed 的订单簿重建文档也强调要根据 snapshot、transaction flags、pending queue 等协议语义来处理更新，而不是单纯凭结果选择排序。[kb.dxfeed.com](https://kb.dxfeed.com/en/data-model/market-events/dxfeed-order-book/order-book-reconstruction.html?utm_source=chatgpt.com)

---

### 风险点 4：“last-200ms correction”目前依据不足

md 说：

```
last-200ms correction 最适合盘口回放
```

这个判断目前证据不足。

更客观的做法应该先统计：

```
quote 间隔分布
同毫秒事件数量分布
mismatch 发生在 quote 前还是 quote 后
高活跃股票的 drift 曲线
不同修正窗口 50ms / 100ms / 200ms / 500ms 的效果
```

然后再决定 correction window。

否则 200ms 会变成经验参数，后面很难解释为什么这样做。

---

### 风险点 5：footprint 不应该说“主要靠 RawBook”

md 里说 RawBook 负责 footprint、delta、volume profile，这个方向大体对，但需要更精确：

```
footprint / delta / volume profile 主要来自 trade tape
RawBook 只辅助判断被动价位、盘口背景、挂撤状态
```

如果把 footprint 绑定到 RawBook，RawBook 的缺失订单会影响成交统计。成交本身应该以 trades 为准。

Nasdaq 对 ITCH 的解释也说明，执行消息通常只减少已在簿上的可见订单，而主动单/非展示订单不一定作为 book order 出现。[help.data.nasdaq.com](https://help.data.nasdaq.com/article/999-in-nasdaq-totalview-itch-5-0-i-thought-there-should-be-two-order-execute-messages-for-a-match-number-however-there-is-only-one-order-execute-message-isnt-the-deal-supposed-to-go-both-buy-and-sell-ways?utm_source=chatgpt.com) 这说明成交流和订单簿流在语义上不能简单等同。

---

## 3. 更优路径

我建议不要直接按 md 的 P0/P1/P2/P3 执行，而是改成下面这个路线。

### Phase 3.7：先锁定指标口径

只做统计，不改盘口逻辑。

目标：

```
raw_match_rate
quote_anchor_match_rate
inter_quote_drift
missing_order_rate
correction_qty_abs
correction_price_level_count
```

重点是把“匹配率”拆清楚：

```
raw_match_rate = RawBook vs Quote
anchor_match_rate = QuoteAnchorBook vs Quote
replay_quality = quote 之间盘口变化质量
```

当前 `task_plan.md` 已经明确 Phase 3.5/3.6 不做 replay clock、checkpoint、quote-overwrite anchoring。[](https://github.com/Euroish/atas-replay-system/blob/main/task_plan.md)

[task_plan](https://github.com/Euroish/atas-replay-system/blob/main/task_plan.md)

所以下一步应该是从 P3.7 过渡到 P4，而不是继续把所有东西塞进 P3。

---

### Phase 4.0：建立 VisibleBook，但不要先做复杂 correction

第一版只做：

```
quote 到来 -> VisibleBook = quote top10
写 checkpoint
记录 RawBook 与 quote 差异
```

不要做：

```
局部排序搜索
200ms 平滑
复杂 correction
heatmap UI
DOM UI
```

第一版目标是把系统分层跑通。

---

### Phase 4.1：生成 checkpoint 数据

建议输出：

```
visible_book_checkpoints.parquet
raw_vs_quote_residual.parquet
anchor_events.parquet
```

字段建议：

```
symbol
trade_date
ts_ms
quote_seq
side
level
price_int
qty
source = quote_anchor / raw_event_delta / correction
raw_price_int
raw_qty
price_diff
qty_diff
```

这样后面 heatmap、DOM、回放速度都可以基于 checkpoint，而不是每次从头重放。

---

### Phase 4.2：quote 之间用事件推进，但只作为动画层

也就是：

```
quote_t0：锚定
t0 到 t1：用 order / cancel / trade 生成盘口变化轨迹
quote_t1：重新锚定
```

这里要注意：中间动画是“可视化推演”，不是绝对真实盘口。应该记录：

```
drift_before_next_anchor
correction_at_next_anchor
```

这样既能显示连续 heatmap，又不会假装每一毫秒都是真实完整盘口。

---

### Phase 4.3：再考虑局部排序搜索

局部排序搜索应作为增强模块：

```
raw_ordering_experiment.py
```

而不是默认引擎。

它的验收不是“让匹配率变高”，而是：

```
是否在多数 symbol / 多数 session 上稳定降低 raw mismatch
是否没有增加 missing_order
是否没有破坏成交统计
是否有可解释的排序规则
```

如果只在少数股票上提升，不能进主线。

---

## 4. 对 md 的最终评价

| 内容 | 客观评价 | 是否影响开发 |
| --- | --- | --- |
| RawBook / VisibleBook 分层 | 正确 | 正向 |
| 不强求 raw_match_rate 95% | 正确 | 正向 |
| quote anchor | 正确，但要限定为显示层 | 正向 |
| visible_match_rate 99% 表述 | 容易造成指标幻觉 | 有风险 |
| correction layer | 思路可用，但结构要改 | 有风险 |
| last-200ms correction | 证据不足 | 有风险 |
| 局部排序搜索 | 可研究，不宜主线 | 有风险 |
| 集合竞价暂放 | 可以，但 opening checkpoint 不能删 | 基本可行 |
| footprint 归 RawBook | 表述不够精确 | 小风险 |

---

## 5. 最客观的结论

你的 md **没有明显方向性错误**，但它把“工程目标”说得有点太快了。

更准确的说法应该是：

```
当前 raw book 80% 多不是单纯 bug，而是数据语义和事件完整性导致的残差。
下一步不应继续硬修 RawBook。
应进入 P4，新增 VisibleBook / quote anchor / checkpoint。
但 visible_match_rate 不能单独作为真实复现指标，必须同时记录 quote 间 drift 和 correction 成本。
局部排序搜索、平滑 correction、heatmap UI 都应后置。
```

给 Codex 的更优指令可以压缩成一句：

```
从 b9f4ecc 开始，先实现 Phase 4.0 的 VisibleBook quote-anchor checkpoint；RawBook 不覆盖、不伪造 order_id；新增 quote_anchor_match_rate、inter_quote_drift、correction_cost 三类指标；不要先做局部排序搜索、200ms 平滑或 UI。
```