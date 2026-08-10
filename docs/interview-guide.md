# 面试讲稿指南（Interview Guide）

> 这份文档是你用 **CUITCCA** 作为 AI 工程师面试 demo 项目的完整讲解脚本：怎么在
> 30 秒 / 3 分钟 / 10 分钟三档时间内讲清楚项目，面试官每个追问该怎么答。
> 建议面试前把本文件读三遍，把「架构决策问答」一节的内容内化成自己的话。

---

## 目录

- [1. 电梯演讲（30 秒）](#1-电梯演讲30-秒)
- [2. 项目演示脚本（3 分钟）](#2-项目演示脚本3-分钟)
- [3. 深度讲解路线（10 分钟）](#3-深度讲解路线10-分钟)
- [4. 架构决策问答（面试官最常追问）](#4-架构决策问答面试官最常追问)
- [5. 评测与数据速查表](#5-评测与数据速查表)
- [6. 演示环境准备清单](#6-演示环境准备清单)
- [7. 常见坑与怎么应对](#7-常见坑与怎么应对)

---

## 1. 电梯演讲（30 秒）

> 面试官让你"简单介绍一下这个项目"时背这一段，不要展开。

**中文版：**

> 这是一个面向成都信息工程大学的校园智能问答系统，核心是一个生产级 RAG 架构。
> 我做的最重要的事情有三件：第一，把检索质量做成可评测、可迭代的——用 76 道
> 人工核对的 golden 题集做 hit_rate/MRR 评测，用评测数据驱动了混合检索（BM25 +
> Dense RRF 融合）和条件触发式重排两个改造，命中率从 75% 提到 90%；第二，解决
> 幻觉问题——专门建了一套 20 题的拒答评测集，用预标注的禁止信号自动检测模型
> 编造，并设计了双链路架构（低延迟的 QAWorkflow + 可多轮工具调用的 Agent）来
> 在延迟和推理能力之间做权衡；第三，把工程化做扎实——14 种文档格式的解析注册表、
> 表格感知分块、增量摄取去重、可观测性埋点、530+ 测试和完整 CI，整个项目从文档
> 摄取到回答生成再到评测是一条完整的链路。

**英文版（备用）：**

> It's a production-grade RAG system for campus QA. Three things I'm most proud
> of: (1) I made retrieval quality measurable and iterated on data — a 76-question
> human-verified golden set drove hybrid retrieval (BM25 + dense with RRF) and
> conditional reranking, lifting hit@1 from 75% to 90%; (2) I built a dedicated
> hallucination evaluation — 20 questions with pre-annotated forbidden signals to
> auto-detect fabrication, plus a dual-path architecture trading off latency vs
> multi-hop reasoning; (3) solid engineering — a 14-format parser registry,
> table-aware chunking, deduped incremental ingestion, observability, 450+ tests
> and full CI. It's a complete pipeline from ingestion to generation to evaluation.

**一句话总结（如果面试官只让你说一句）：**

> 一个用评测数据驱动架构决策的校园 RAG 系统——混合检索、条件重排、双链路问答、
> 幻觉评测，全链路工程化。

---

## 2. 项目演示脚本（3 分钟）

> 面试官给你 3 分钟现场演示。按下面的顺序来，每步 30 秒，**边说边操作**。

### Step 1：展示知识库管理（30 秒）

打开 `http://localhost:8522/web/manage.html`：

- "这是知识库管理页，我支持 14 种格式的文档摄取，包括旧版 Office 格式和图片 OCR。"
- 点开一个索引，展示节点列表："这是分块结果，表格会被当成原子单位不被切断。"

### Step 2：展示标准问答（60 秒）

切回聊天页，问一个事实类问题，例如：

- **"图书馆本科生能借几本书？"**（表格检索）
- **"学校校训是什么？"**（简单事实）
- **"学校转专业工作应遵循什么原则？"**（可触发条件查询改写——低置信度时
  模型会先改写问题再检索，这是 2026 年 RAG 的热门技术）

- "这是标准问答链路：condense → retrieve → synthesize 三步，单轮问答零额外
  LLM 调用，首字延迟最低。"
- 回答完成后，点击"参考来源"："这里能看到检索到的原文片段，方便用户核实。"

### Step 3：展示 Agent 模式（60 秒）

切换到 **Agent 模式**，问一个需要多跳的问题，例如：

- **"学校国家奖学金和国家励志奖学金的区别是什么？"**（需要跨文档拼接）
- **"就业签约造假举报电话是多少？"**（精确事实）

> 注意：演示问题要选**评测里已验证能命中**的，不要选 golden 集里的已知未命中
> （q038 转专业工作小组组成、q069 人才培养模式）——那两条是当前检索链路的
> 真实短板，Agent 模式也无法保证答对，面试现场翻车不值得。q038/q069 的正确
> 用法是在"深度讲解"里当"已知短板"讲（见第 4 节 Q13）。

- "这是 Agent 链路，模型可以自己决定调用哪些工具、调几次。你看界面上会实时
  显示工具调用过程——它先列知识库、检索、发现不够再换个角度查一次。"
- "Agent 模式用 NDJSON 流式把工具调用过程暴露给前端，而不是只吐 token，这样
  用户可以看见'中间发生了什么'，而不是黑盒。"

### Step 4：展示评测（30 秒）

打开 `evals/results/` 下的报告或直接跑：

```bash
uv run python evals/run_retrieval_eval.py --collection campus-corpus --top-k 5
```

- "这套 golden 评测集是我人工逐条核对的，hit_rate 97.4%、MRR 0.858。"
- "我所有的架构决策都有评测数据支撑——比如混合检索是 A/B/C 对比测出来的，
  不是拍脑袋。"

---

## 3. 深度讲解路线（10 分钟）

> 面试官让你"详细讲讲"。按下面 4 段讲，每段都有明确的"讲什么"和"为什么值得讲"。

### 3.1 整体架构（2 分钟）

- 讲清楚分层：客户端 → FastAPI 中间件（会话/限流/统计/CORS）→ 路由层 → 处理层
  （QAWorkflow / Agent / IngestionPipeline / HybridRetriever）→ LlamaIndex
  抽象层 → 存储层（ChromaDB + SQLite + Docstore）。
- 画出（或口述）你脑中的架构图，让面试官知道你有全局观。
- 关键词：**分层、关注点分离、可替换性**（存储层换掉不影响上层逻辑）。

### 3.2 检索链路（3 分钟）

这是 RAG 系统的核心，重点讲**决策过程**而不是罗列功能：

1. **为什么混合检索**：纯向量检索对中文专有名词（教务处、奖学金）的精确匹配弱，
   评测数据：hit@1 75% → 85%，延迟只 +2ms。BM25 用 jieba 分词喂给 bm25s，
   RRF 融合。
2. **为什么条件触发重排**：cross-encoder 每次 ~660ms，全量重排延迟不可接受。
   策略是 top1 分数 >= 0.75 跳过、低于才触发。评测：hit@1 75% → 90%。
3. **为什么加查询改写**：rerank 只能在"已召回的内容"里排序，如果正确文档因为
   措辞不匹配压根没进召回（评测里 q038/q069 就是这类），rerank 帮不上忙。
   低置信度时用 LLM 改写查询再查一次。
4. **检索迭代上限**：诚实说明当前只做 1 轮检索，参数为未来 multi-hop 留了钩子，
   不做假支持。

**面试官如果问"你的评测是怎么做的"**，见第 5 节速查表。

### 3.3 双链路问答架构（3 分钟）

这是本项目最有区分度的设计，**一定要重点讲**：

- 同时存在 `QAWorkflow` 和 Agent 两条链路是**刻意的**，不是历史遗留。
- QAWorkflow：开发者写死 condense → retrieve → synthesize，单轮零额外 LLM
  调用，适合事实类问题（占绝大多数流量）。
- Agent：模型自己决定调工具、调几次，至少多一次决策 LLM 往返，适合多跳问题。
- 结论：**把所有查询都塞给 Agent = 让简单问题为复杂问题买单**。所以 Agent 是
  新增端点而不是替换，调用方按问题复杂度选链路。

Agent 的护栏（面试必问"你怎么防止 Agent 失控"）：

- 最大工具轮数：`FunctionAgent.run(max_iterations=6, early_stopping_method="generate")`
  ——撞上限时用已有信息生成收尾回答并标记 truncated，而不是抛异常炸穿请求。
- 超时：Workflow 原生 timeout，超时降级到与 QAWorkflow 同一个兜底文案。
- 检索为空不编造：工具描述里显式写明"results 为空表示没查到，不要编造"。
- 不造假工具：日期工具明确声明它不知道校历，防止模型拿日期推断开学第几周。

### 3.4 幻觉抑制与评测（2 分钟）

- 三套评测体系：检索（76 题 hit_rate/MRR）、拒答（20 题幻觉率）、回答质量
  （LLM-as-judge 忠实度/相关性/答案匹配）。
- 拒答评测用**预标注禁止信号**（如问老师电话时输出 `028-` 即幻觉）——零 LLM
  成本、可复现，适合每次 CI 跑。
- 回答质量评测用 LLM-as-judge，每题输出 judge 的完整理由供人工复核。

---

## 4. 架构决策问答（面试官最常追问）

> 这是全文档最重要的部分。每条都是"为什么这么设计"，背熟并用自己的话讲。

### Q1: 为什么用 LlamaIndex 而不是自己写 RAG？

- 用框架不等于没做工作：我在框架之上做了三件框架不给你的事——(1) 用评测数据
  驱动选型（混合检索、重排都是先测后上）；(2) 自己实现 JiebaBM25Retriever，
  因为 LlamaIndex 官方 BM25 的 tokenizer 钩子是死代码（中文会被当成一个 token）；
  (3) 自建三套评测体系。框架负责抽象，我负责做对。

### Q2: 为什么不用官方 BM25Retriever？

- 它的 `tokenizer` 参数在当前版本是废弃且不生效的桩代码，中文一整句会被当成
  一个 token，BM25 词频匹配失效。所以我用 bm25s + jieba 自实现了一个轻量
  retriever，分词、建索引、查询全程 jieba。**这个细节很能体现你读过源码。**

### Q3: 为什么混合检索收益这么明显？

- 中文场景的典型问题：dense 对术语模糊、关键词精确匹配弱。BM25 对专有名词
  （教务处、奖学金、转专业）的精确匹配弥补了这一点。RRF 融合不需要调权重，
  对两路分数尺度不一致天然鲁棒。

### Q4: 为什么重排要"条件触发"而不是全量？

- cross-encoder（bge-reranker-v2-m3）在 CPU 上每次约 660ms。如果每次查询都
  触发，延迟不可接受。策略：top1 分数 >= 0.75 说明已经很自信，跳过；低于才
  触发。评测：hit@1 从 75% 到 90%，但只有低置信度才付延迟。

### Q5: 为什么用 Workflow 而不是 ChatEngine？

- 三点：(1) Workflow 用显式 Event 在 step 间传数据，链路可读、可测试；(2)
  流式实现直接调 `llm.astream_chat()` 拿 token 级异步生成器，避免 ChatEngine
  同步/异步生成器分裂的坑；(3) `max_retrieval_iterations` 参数为未来
  multi-hop 检索留了钩子。

### Q6: 怎么防止模型编造（幻觉）？

- 三层：(1) prompt 约束（系统提示明确"没检索到就如实说不知道"）；(2) 兜底
  文案统一（检索为空时返回固定的"我还不知道"而不是让模型自由发挥）；(3)
  评测防线——20 题拒答评测集 + 禁止信号自动检测 + LLM-as-judge 忠实度。
- 关键话术："我不能保证模型 100% 不编，但我能保证**编了会被发现**——评测体系
  就是干这个的。"

### Q7: 为什么用 FunctionAgent 而不是 ReActAgent？

- ReAct 是靠 prompt 模拟 Thought/Action/Observation 格式，容易被自由格式输出
  带偏；项目配置的 LLM 支持原生 function calling，用 FunctionAgent 更可靠，
  不需要那套格式解析兜底。AgentWorkflow 是给多 agent handoff 场景用的，这里
  只有一个角色，不需要。

### Q8: 单轮问答为什么零额外 LLM 调用？

- condense step 在 `chat_history` 为空时直接透传原始 query，不为压缩多付一次
  LLM 往返。这是性能敏感主路径的刻意优化。

### Q9: 会话历史怎么管理？

- session cookie（session_id）标识会话，TTLCache（200 条、1 小时）存
  ChatMessage 列表。服务端存、前端 localStorage 只做展示层持久化。

### Q10: 增量摄取怎么去重？

- 文档 id = 内容 sha256（不用文件名/uuid，因为那些会变）；配合
  `TextNode.hash`（sha256(text + str(metadata))）让重复运行天然幂等：内容相同
  → 跳过；内容变化 → 删除旧 node 重新嵌入；全新 → 新增。metadata 的
  last_updated 用文件 mtime 而不是摄取时间（否则每次重跑 hash 都变，抵消去重）。

### Q11: 速率限制 / 安全怎么做的？

- 限流只对会触发 LLM 调用的端点（按路径形状判断，不是硬编码列表，新增端点
  不容易漏）；认证用 `require_api_key_if_configured`（未配置时跳过便于本地，
  配置后强制 Bearer）；API Key 比较用 `secrets.compare_digest` 防时序侧信道；
  只信任 `request.client.host`，不信可伪造的 X-Forwarded-For。

### Q12: 前端怎么做流式？

- 标准问答：`StreamingResponse` media_type=text/plain，token 级流式，前端
  `ReadableStream` + rAF 节流渲染 Markdown。
- Agent 模式：NDJSON（每行一个 JSON 事件），把 token 和工具调用过程都暴露出来
  ——因为 Agent 要经过不确定次数的工具调用，只吐 token 看不到"中间发生了什么"。

### Q13: 评测里的两条未命中（q038/q069）你为什么不修？

- 诚实回答 + 展示思考：这两条是"同主题文档冗余时，标题强匹配的文档挤掉正确
  文档"。保留在案不修饰，是因为**改 golden 集等于掩盖问题**。改进方向是
  metadata 过滤或文档级去重，目前查询改写是缓解手段。
- 这个回答展示的是：**你区分"标注问题"和"真实缺陷"，并且不粉饰指标**——这是
  面试官最看重的工程素养。

### Q14: 如果给你两周，你会做什么？

- 说 3 个具体的：(1) 文档级去重或 metadata 过滤解决 q038/q069 类问题；(2)
  父子分块（small-to-big）——检索命中小 chunk、喂大上下文给 LLM；(3) 把拒答
  评测接入 CI 每天跑，防止回归。
- 不要说"重构"这种空话，要说到具体模块和预期收益。

---

## 5. 评测与数据速查表

> 面试前背熟这些数字。数字 = 可信度。

### 检索质量（campus-corpus，76 题，top_k=5）

```
overall                  hit_rate= 97.37%  mrr=0.858
comprehension            hit_rate= 89.47%  mrr=0.765  (n=19)
contact_lookup           hit_rate=100.00%  mrr=1.000  (n=2)
multi_hop                hit_rate=100.00%  mrr=0.933  (n=10)
procedural               hit_rate=100.00%  mrr=0.917  (n=6)
simple_fact              hit_rate=100.00%  mrr=0.851  (n=31)
table_lookup             hit_rate=100.00%  mrr=0.938  (n=8)
```

### 架构选型 A/B/C 对比（campus-corpus，20 题）

| 指标 | 纯向量基线 | + 混合检索 | + 混合 + rerank |
|------|-----------|-----------|----------------|
| hit_rate@1 | 75% | 85% | **90%** |
| MRR@5 | 0.852 | 0.896 | **0.910** |
| 平均延迟 | 13ms | +2ms | +660ms（仅低置信度触发） |

> 讲法：混合检索几乎零延迟成本（+2ms）却实打实提升；rerank 收益大但延迟高，
> 所以做成条件触发——**这是用数据做权衡的范例**。

### 回答质量评测（LLM-as-judge，golden.seed.jsonl）

三个指标：忠实度（faithfulness）、回答相关性（1-5）、答案匹配（1-5，>=4 通过）。
跑法：

```bash
uv run python evals/run_answer_eval.py --limit 10
```

### 评测文件位置

- `evals/golden.seed.jsonl` — 76 题检索 golden（人工核对，expected_answer + expected_sources）
- `evals/golden.refusal.jsonl` — 20 题拒答集（六类，forbidden_signals 预标注）
- `evals/run_retrieval_eval.py` — 检索 hit_rate/MRR
- `evals/run_refusal_eval.py` — 幻觉率/承认边界率
- `evals/run_answer_eval.py` — 回答质量 LLM-as-judge
- `evals/results/*.json` — 历史评测报告

---

## 6. 演示环境准备清单

> 面试前一天晚上按这个清单过一遍，**每个步骤都要真的跑过**。

- [ ] `uv sync` 依赖装好，`uv run python -m pytest tests/ -q` 全绿（530+ 用例，覆盖率 93%+）
- [ ] `backend/.env` 配好 OPENAI_API_KEY（LLM 可调用），CUITCCA_API_KEY 留空便于演示
- [ ] `make dev` 能启动，`http://localhost:8522` 可访问
- [ ] 知识库索引已导入：`uv run python evals/ingest_corpus.py`
- [ ] 聊天页能正常回答一个事实类问题（测试 LLM 链路）
- [ ] Agent 模式能正常回答一个多跳问题，工具调用过程可见
- [ ] 检索评测能跑：`uv run python evals/run_retrieval_eval.py --collection campus-corpus --top-k 5`
- [ ] 拒答评测能跑：`uv run python evals/run_refusal_eval.py --limit 3`
- [ ] 前端构建产物存在：`backend/app/static/` 里有 index.html（`make frontend-build`）
- [ ] 准备 3 个演示问题（1 个表格检索 + 1 个多轮 + 1 个 Agent 多跳），提前试过

### 演示常用问题（都验证过有答案）

| 类型 | 问题 | 期望 |
|------|------|------|
| 简单事实 | 学校校训是什么？ | 成于大气 信达天下 |
| 表格检索 | 图书馆本科生能借几本书？ | 表格里的册数/借期 |
| 多轮 | 先问校训，再问"这个校训的含义是什么？" | condense 生效 |
| 查询改写 | 学校转专业工作应遵循什么原则？ | 低置信度时改写后二次检索 |
| Agent 多跳 | 国家奖学金和国家励志奖学金的区别？ | 跨文档拼接，触发多次检索 |
| 拒答 | 2026 年录取分数线是多少？ | 如实说不知道 |

---

## 7. 常见坑与怎么应对

### 坑 1：面试官问"这是你的项目吗？代码都是你写的？"

- 如实回答：核心架构、检索链路、评测体系、双链路问答是你主导的；数据采集和
  部分文档解析是历史积累。**面试官最反感的是把别人的活说成自己的**，坦率反而
  加分。能讲清楚每行关键代码的设计理由，就是"你的"。

### 坑 2：演示时 LLM 调用失败 / 网络抖动

- 提前准备好兜底：所有问答端点都有统一的兜底文案（"我还不知道，请反馈给我
  吧" / "出错了，请稍后再试"）。真失败了就大方说"这是 LLM 依赖，网络波动，
  我重试一下"，然后展示检索评测（不需要 LLM）作为替代。

### 坑 3：面试官追问"这个数字是怎么来的"

- 所有评测数字都能在 `evals/results/*.json` 里找到原始数据。面试前把
  `retrieval_20260808_064333.json`（76 题那次的报告）看一遍，知道每个
  category 的实际命中和未命中。

### 坑 4：被问"你最大的失败 / 教训"

- 好的素材：q038/q069 两条未命中——"我一开始想改 golden 集把分数修上去，
  后来意识到这是自欺欺人，正确做法是保留未命中、分析根因（同主题文档冗余）、
  把改进方向记下来"。**承认问题 + 分析根因 + 说明改进路径**，这是标准答案结构。

### 坑 5：被问"RAG 和 Fine-tuning 的区别 / 什么时候用哪个"

- RAG：知识频繁更新、需要引用溯源、成本低、可解释。Fine-tuning：行为风格
  对齐、领域语言学习。这个项目选 RAG 是因为校园政策经常变、答案必须可溯源。

---

## 附录：一句话记忆卡

- 项目是什么：**校园 RAG 问答系统，全链路工程化**
- 核心卖点 1：**评测数据驱动架构决策**（混合检索/重排/查询改写都是测出来的）
- 核心卖点 2：**双链路问答**（低延迟 QAWorkflow + 多跳 Agent，按需选择）
- 核心卖点 3：**三套评测体系**（检索/拒答/回答质量，覆盖三类失败模式）
- 最骄傲的工程细节：**自己实现 JiebaBM25Retriever**（官方 tokenizer 钩子是死的）
- 最大的诚实体现在：**两条未命中保留在案不修饰**
