# Evals（评测先行 · Phase 0）

在对检索/索引架构做任何重构之前，先给现有系统打一份基线分。这套 evals 只做
**检索质量**评测（hit-rate / MRR），不评测生成质量（LLM 回答对不对），因为
Phase 0 的目标是搞清楚"现在的向量检索到底行不行"，这是后续重构最需要保护的
契约。

## 目录结构

```
evals/
├── README.md                  本文件
├── golden.seed.jsonl          人工编写、人工审核过的黄金评测集（可信，76 题）
├── golden.refusal.jsonl       拒答/知识边界评测集（20 题）——考察幻觉抑制，不参与检索评测
├── golden.candidates.jsonl    generate_golden.py 产出的候选题（未审核，不可直接用于评分）
├── generate_golden.py         从现有索引批量生成 QA 候选
├── ingest_corpus.py           一次性导入：把仓库里的真实文档全量导入 campus-corpus collection
├── run_retrieval_eval.py      核心：跑检索评测，算 hit-rate / MRR
├── run_refusal_eval.py        拒答评测：幻觉率 / 承认边界率（消费 golden.refusal.jsonl）
├── run_answer_eval.py         回答质量评测（LLM-as-judge）：忠实度 / 相关性 / 答案匹配
├── run_rerank_eval.py         A/B 对比：向量检索基线 vs 召回20+cross-encoder重排取5
├── run_hybrid_eval.py         A/B/C 对比：纯向量 vs BM25+dense混合 vs 混合+rerank
├── results/                   评测脚本的输出报告（JSON，按时间戳命名）
└── ../backend/app/utils/rerank.py   生产环境条件触发式 Rerank（Phase C 起默认开启）
```

## 三套评测的分工

| 评测 | 数据集 | 问什么 | 衡量什么 |
|---|---|---|---|
| `run_retrieval_eval.py` | `golden.seed.jsonl`（76 题） | 能不能检索到正确来源 | hit_rate / MRR |
| `run_refusal_eval.py` | `golden.refusal.jsonl`（20 题） | 该说不知道的时候会不会编 | 幻觉率 / 承认边界率 |
| `run_answer_eval.py` | `golden.seed.jsonl`（76 题） | 检索都对了，回答生成对了吗 | 忠实度 / 相关性 / 答案匹配 |

检索评测衡量**召回**，拒答评测衡量**幻觉抑制**，回答质量评测衡量**生成质量**——
三者是 RAG 系统三类不同的失败模式，任何一个都替代不了另外两个（详见下面
`run_answer_eval.py` 一节）。

## 现状（侦察结论，写这份 evals 时的事实）

- 索引存储：Chroma `PersistentClient`，路径由 `CHROMA_DB_PATH`（默认
  `data/chroma_db/`）决定。见 `backend/app/handlers/vector_store.py`。
- 索引通过 `VectorStoreIndex.from_vector_store(vector_store, embed_model=Settings.embed_model)`
  加载，一个 collection = 一个 index，`index.index_id` = collection 名。
- Embedding 模型：`BAAI/bge-m3`（HuggingFace，本地跑，见
  `backend/app/configs/llm_predictor.py:init_settings`），**不需要外部 API key**，
  所以检索评测在本地/CI 都可以只用 CPU 跑，不依赖 LLM。
- 线上问答实际检索参数：`similarity_top_k=5`（单索引路径 /
  `RouterQueryEngine` 多索引路径都是 5，见 `backend/app/handlers/graph_builder.py`；
  `router/index.py` 里手工调用 `/query` 接口用的是 `top_k=2`，属于特例）。
  `run_retrieval_eval.py` 默认 `--top-k 5`，和线上主路径保持一致。
- 本地 `data/chroma_db` 里有两个 collection：
  - `test-index`（38 chunk）：开发过程中零散上传的测试数据，只覆盖"招生
    就业"主题，**不是完整知识库**。首份基线（2026-07-13）在它上面只有
    hit_rate 25% / MRR 0.250——不是评测脚本的 bug，而是如实反映了索引覆盖
    不全。
  - `campus-corpus`（775 chunk，110 个权威文件）：由 `evals/ingest_corpus.py`
    把 `信息搜集汇总/` 和 `data/upload_files/` 下的全部可解析文档导入生成。
    Phase 2 起复用 `backend/app/handlers/ingestion_pipeline.py` 的生产级摄取
    逻辑：文档 id = 内容 sha256，metadata 的 `file_name` 是**原始文件名**
    （没有线上上传路径加的 uuid 前缀），额外带 `last_updated`（文件 mtime）；
    同名不同内容的冲突（比如两个版本的 `学校历史.txt`/`大学精神.txt`，
    Phase 2 侦察发现有 7 组）按 mtime 取更新版本，运行时会打印"发现同名冲突"
    明细，不静默丢弃信息。这是评测用的正式语料，重跑 `ingest_corpus.py` 会
    先删掉重建该 collection，可安全重复执行。三份基线：test-index
    hit_rate 25%/MRR 0.250 → campus-corpus（Phase 0，含未消解冲突）
    hit_rate 100%/MRR 0.877 → campus-corpus（Phase 2，冲突已消解）
    hit_rate 100%/MRR 0.827（top_k=5；MRR 小幅下降是因为语料更干净后，
    q017/q019 这类泛化提问在更完整的院系/学习资源类文档里有了更多语义相近
    的候选，不是检索退化，hit_rate 仍是 100%）。
- `golden.seed.jsonl` 按"知识库应该覆盖的真实主题"编写。评测应以
  `campus-corpus` 为准：
  `uv run python evals/run_retrieval_eval.py --collection campus-corpus --top-k 5`。

### 两个评测集的分工（重要）

**`golden.seed.jsonl`（75 题）——检索质量评测。** 每条都有非空的
`expected_sources`，答案严格来自语料原文（逐条核对过来源文件确实存在）。
题型分布：

| category | 数量 | 考察点 |
|---|---|---|
| `simple_fact` | 31 | 单点事实召回 |
| `comprehension` | 19 | 需要整合一段话才能回答 |
| `multi_hop` | 10 | 答案分散在多处，需要跨段/跨文档拼接 |
| `table_lookup` | 8 | **答案在表格里**（图书借阅规则、校车时刻表、历任领导表） |
| `procedural` | 5 | 办事流程类，答案是有序步骤 |
| `contact_lookup` | 2 | 电话/地址等精确串，错一位就有实际危害 |

`table_lookup` 这一档是刻意加的：语料里大量内容（招生计划、竞赛目录、借阅
规则、时刻表）本质是表格，而表格在解析阶段最容易被压平成一行文字丢失行列
关系。这 8 题直接度量"表格结构化抽取"这项改造有没有真的兑现，而不是靠主观
感觉判断。

**`golden.refusal.jsonl`（20 题）——拒答与知识边界评测。** 这些题
**故意不放进 `golden.seed.jsonl`**：它们的 `expected_sources` 本该为空，而
`_common.py:first_hit_rank()` 对空 `expected_sources` 一律返回"未命中"，混进
去只会无意义地把 hit_rate 拉低，并不能反映任何真实问题。它们衡量的是**生成
阶段**的行为，需要单独的生成质量评测来消费。

字段与检索集不同：用 `expected_behavior`（期望行为）+ `forbidden_signals`
（出现即判定为幻觉的信号串）替代 `expected_answer`。六个类别：

| category | 数量 | 说明 |
|---|---|---|
| `not_in_corpus` | 6 | 校内问题但语料没覆盖（2026 校历、分数线、教师电话…） |
| `out_of_scope` | 4 | 与校园无关的通用请求（写诗、写代码、股票） |
| `false_premise` | 3 | 前提就是错的（"医学院在哪个校区"、"是985还是211"） |
| `partially_answerable` | 3 | 一半能答一半不能，考察能否区分已知与未知 |
| `personal_data` | 2 | 涉及个人学籍/成绩，知识库不含也不应假装能查 |
| `prompt_injection` | 2 | 提示注入 + 诱导改写事实 |

`forbidden_signals` 的设计意图：拒答类评测最难的是"怎么自动判断模型有没有
编"。与其让 LLM-as-judge 主观打分，不如对每道题预先标注"只要输出里出现这个
串，就几乎可以确定是编的"——比如 r011（问某位老师的电话）只要出现 `028-`
就是幻觉，r014（问 2026 年分数线）只要出现"分"就是在给数字。这是可自动化、
可复现、零 LLM 成本的硬判据，作为 LLM-as-judge 之外的第一道闸。

### 扩充后的基线（76 题，campus-corpus，top_k=5）

```
overall                  hit_rate= 97.37%  mrr=0.858
--------------------------------------------------------------------
comprehension            hit_rate= 89.47%  mrr=0.765  (n=19)
contact_lookup           hit_rate=100.00%  mrr=1.000  (n=2)
multi_hop                hit_rate=100.00%  mrr=0.933  (n=10)
procedural               hit_rate=100.00%  mrr=0.917  (n=6)
simple_fact              hit_rate=100.00%  mrr=0.851  (n=31)
table_lookup             hit_rate=100.00%  mrr=0.938  (n=8)
```

`table_lookup` 100% / MRR 0.938 是这轮最有信息量的一档：它证明表格里的内容
（借阅册数、校车班次、历任领导任职时间）确实能被检索到，而不是在解析阶段就
塌成一行流水账丢了行列对应关系。

#### 首轮跑出来的 4 条未命中，分析后是两类问题

扩充评测集之后第一次跑是 hit_rate 94.67%，4 条未命中。逐条查了实际检索结果
（`evals/results/*.json` 里有每题的 top-5），结论是**一半是我的标注错了，
一半是真的没检索到**——两类必须分开处理，把标注问题也算成检索缺陷会掩盖真实
问题，反过来把真实缺陷说成标注问题则是自欺欺人：

| 题 | 判定 | 处理 |
|---|---|---|
| q021 专任教师人数 | 标注遗漏 | 检索返回的 `学校简介.txt` 实测同样写着"教师1600余人，其中博士800余人"，是同等有效的来源。给 `expected_sources` 补上 |
| q044 一卡通遗失怎么办 | 题目有歧义 | `挂失流程.txt`（"请到一卡通服务中心办理"）和 `图书馆.txt`（图书馆咨询台挂失）从不同角度都对。**把题目改精确**（限定图书馆场景）并另立 q076 覆盖通用挂失——而不是放宽 `expected_sources`，那样只会把歧义藏起来 |
| q038 转专业工作小组组成 | 真实缺陷 | 检索到的全是其它转专业文档（通知、实施细则汇编），没召回 `转专业政策.txt`。语料里转专业主题文档高度冗余，正确的那份被同主题近重复文档挤出 top-5 |
| q069 人才培养模式 | 真实缺陷 | "人才培养"这个词被《第二课堂（综合素质培养）实施意见》的标题强匹配，占满 top-5，而答案（"三段培养、两次分流"）在 `学校简介.txt` 里 |

后两条**保留为未命中**，作为当前检索链路的已知短板记录在案。它们指向同一类
问题：同主题文档冗余时，标题/关键词强匹配的文档会挤掉真正含答案的文档。这是
metadata 过滤或文档级去重能改善的方向，不是靠调 golden 集能解决的。
- 解析 docx/xlsx 需要 `docx2txt` / `openpyxl`。Phase 0 时它们缺失，导致线上
  `insert_into_index`（同一个 `SimpleDirectoryReader` 路径）上传 docx/xlsx
  会直接解析失败，而 `ALLOWED_EXTENSIONS` 却允许上传——Phase 1 已修复：这两
  个包提为主依赖（`uv sync` 即装），并有 `tests/test_docx_upload_regression.py`
  回归测试保护。

## 怎么跑

### 1. 冒烟测试（不需要索引、不需要 LLM，CI 里跑这个）

```bash
uv run pytest tests/test_evals_smoke.py -v
```

只检查 `golden.seed.jsonl` 格式是否合法、评测脚本能否正常 import，不执行
真正的检索。

### 2. 导入评测语料（首次评测前或语料更新后跑一次）

```bash
uv run python evals/ingest_corpus.py
```

扫描 `信息搜集汇总/` 和 `data/upload_files/`，按线上一致的解析/切块方式
（`get_nodes_from_file`：SimpleDirectoryReader + SentenceSplitter 默认配置）
导入 `campus-corpus` collection。按文件内容 sha256 去重（两个数据源里镜像
目录很多），跳过空文件；解析失败不中断，最后统一报告。可重复运行（每次
先删掉重建 collection）。

### 3. 真实检索评测（需要本地已构建好的 Chroma 索引）

```bash
uv run python evals/run_retrieval_eval.py --collection campus-corpus --top-k 5
```

常用参数：

- `--collection <name>`：指定 Chroma collection 名，默认自动探测（如果
  `data/chroma_db` 下只有一个 collection 就用它；否则要求显式指定）。
- `--golden <path>`：golden 数据集路径，默认 `evals/golden.seed.jsonl`。
- `--top-k <int>`：检索 top-k，默认 5（与线上主查询路径一致）。
- `--output-dir <path>`：结果输出目录，默认 `evals/results/`。

如果本地压根没有 Chroma 索引数据（比如全新 checkout、CI 环境），脚本会打
印清晰提示并以 exit code 0 优雅退出——这是刻意设计的，见下面的 CI 说明。

### 3.5 拒答评测（回答"该说不知道的时候会不会编"）

```bash
uv run python evals/run_refusal_eval.py
uv run python evals/run_refusal_eval.py --limit 5           # 先跑几条看看
uv run python evals/run_refusal_eval.py --endpoint agent    # 走 Agent 链路
```

消费 `golden.refusal.jsonl`，报两个指标：

- **幻觉率**：回答里出现了预先标注的 `forbidden_signals`（比如问某位老师的
  电话时输出了 `028-` 开头的号码）。这是硬判据——命中即几乎可以确定是编的。
- **承认边界率**：回答里有没有"不知道/未收录/建议咨询官方"这类措辞。

两个指标分开统计，因为失败含义不同：命中禁止信号是**编了**，缺少承认措辞只是
**没说清楚自己不知道**，后者危害小得多，不该混成一个分数。

与检索评测不同，这个脚本**必须真的调用 LLM**（衡量的是生成阶段行为），所以
没配 `OPENAI_API_KEY` 时会打印提示并 exit 0 优雅退出。

局限：硬判据抓的是"凭空捏造具体事实"这类最严重、最好判定的失败，抓不到"语气
含糊但没编具体数字"这种软性问题——那需要 LLM-as-judge，属于后续扩展。

**基线（2026-08-15，endpoint=workflow，20 题）**：

```
overall                  幻觉率=  0.00%  承认边界率=100.00%
false_premise            幻觉率=  0.00%  承认边界率=100.00%  (n=3)
not_in_corpus            幻觉率=  0.00%  承认边界率=100.00%  (n=6)
out_of_scope             幻觉率=  0.00%  承认边界率=100.00%  (n=4)
partially_answerable     幻觉率=  0.00%  承认边界率=100.00%  (n=3)
personal_data            幻觉率=  0.00%  承认边界率=100.00%  (n=2)
prompt_injection         幻觉率=  0.00%  承认边界率=100.00%  (n=2)
```

结果归档在 `results/refusal_20260815_014227.json`。满分要配着上面那条局限看：
20 题的样本量 + 只测"有没有编造具体内容"的判据，不足以支撑"不会幻觉"的结论。

### 3.7 回答质量评测（LLM-as-judge：回答"生成得对不对"）

```bash
uv run python evals/run_answer_eval.py
uv run python evals/run_answer_eval.py --limit 10        # 先跑前 10 题看看
uv run python evals/run_answer_eval.py --endpoint agent  # 走 Agent 链路
```

消费 `golden.seed.jsonl`（每道题都有人工核对的 `expected_answer`），真实跑
一遍问答链路拿到 `(answer, source_nodes)`，再用**独立的 judge LLM**（项目自己
的 `Settings.llm`，不引入 RAGAS 等外部评测框架）对回答打三个维度的分：

- **忠实度（faithfulness）**：把回答拆成若干独立陈述，逐个判断"这个陈述是否
  被检索到的上下文支持"。分数 = 被支持的陈述数 / 总陈述数。回答可以简短，
  但不能编——每个字都要有出处，这是 RAG 生成最重要的指标。
- **回答相关性（answer relevance）**：回答是否切题地回答了问题（1-5 分）。
  跑题、答非所问、回避问题都会扣分。
- **答案匹配（answer match）**：回答与 golden 集里人工核对的
  `expected_answer` 在语义上是否一致（1-5 分，>=4 算通过）。这是"答案到底
  对不对"的参考答案式判据——不是逐字匹配（开放式问题措辞几乎不可能一致），
  而是语义等价。

报告输出整体分数 + 分 category 汇总 + 每题明细（含 judge 的完整理由），写
`evals/results/answer_*.json`。**judge 理由会被逐条打印出来供人工复核**——
LLM-as-judge 本身可能有偏差，但给出理由后"judge 为什么给这个分"是可审计的，
而不是盲信一个数字。

局限（如实记录）：judge 和生成用同一个模型，可能存在"模型偏爱自己输出"的
偏差；评估 judge 自身的可靠性属于后续扩展。这两点都在脚本 docstring 里写明了。

### 4. Rerank A/B 评测（回答"值不值得上 reranker"）

```bash
uv run python evals/run_rerank_eval.py --collection campus-corpus
```

（`sentence-transformers` 现在是主依赖，`uv sync` 就会装，不需要单独
`--group rerank` 了——Phase C 评测证明值得默认上线后已提升为主依赖。）

A 组：向量检索 top_k=5（= 线上主路径 = run_retrieval_eval 的配置）。
B 组：向量召回 `--recall-k`（默认 20）条，再用本地 cross-encoder
`BAAI/bge-reranker-v2-m3`（约 2.2GB，首次运行自动下载，无需 API key）重排取
top 5。两组都报 hit_rate@1/@2/@5、MRR@5 和每题检索延迟（均值/中位/最大），
结果写 `evals/results/rerank_*.json`。@1/@2 是关键指标：线上 `/query` 接口
只取 top_k=2，rerank 的价值主要看能不能把正确来源顶进前两位。

### 5. 混合检索 A/B/C 评测（回答"值不值得上 BM25+dense 融合"）

```bash
uv run python evals/run_hybrid_eval.py --collection campus-corpus
```

A 组：纯向量基线。B 组：BM25（jieba 分词）+ dense，RRF 融合。C 组：混合检索
先融合出 `--recall-k`（默认 20）条，再用 cross-encoder 重排取 top
`--top-k`（默认 5）——这是线上 `HYBRID_RETRIEVAL_ENABLED` + `RERANK_ENABLED`
都打开时的实际组合配置。结果写 `evals/results/hybrid_*.json`。

### 6.（可选）批量生成候选题

```bash
# 需要配置好 .env 里的 OPENAI_API_KEY / OPENAI_API_BASE / OPENAI_MODEL
uv run python evals/generate_golden.py --collection test-index --limit 5
```

复用 `backend/app/utils/llama.py` 里项目已有的 `generate_qa_batched` /
`formatted_pairs` 生成逻辑，对索引里的文档按文件分组生成 QA 对，写到
`evals/golden.candidates.jsonl`。

**候选题必须经人工审核后，手动挑选、修正措辞、确认 `expected_sources` 准
确无误，再拷贝进 `golden.seed.jsonl`，才能参与评分。candidates 文件本身
不会被 `run_retrieval_eval.py` 读取。**

## 指标含义

- **hit_rate**：对一条 golden 问题，如果 top-k 检索结果里，有任意一个
  node 的来源文件命中 `expected_sources` 中的任意一项，记 1，否则记 0。
  整体 hit_rate = 所有问题的平均值。反映"检索到的这堆结果里，至少有一个
  是对的"的能力。
- **MRR (Mean Reciprocal Rank)**：对一条问题，找到 top-k 结果里**第一个**
  命中 `expected_sources` 的 node 的排名 `rank`（从 1 开始），reciprocal
  rank = 1/rank；如果 top-k 里完全没命中，记 0。整体 MRR = 所有问题的
  平均值。反映"命中的结果排得靠不靠前"，对于走 `similarity_top_k=2` 这种
  小 top-k 的调用路径（如 `router/index.py` 的 `/query` 接口）尤其重要。

### 为什么不用 llama-index 自带的 `RetrieverEvaluator`

`llama_index.core.evaluation.RetrieverEvaluator` 要求 golden 数据里带
`expected_ids`（具体的 node id），但我们的 golden 集是人工写的，只知道
"这题应该从哪个文件里找答案"（`expected_sources`：文件名），不知道、也不
应该关心具体的 chunk/node id（node id 会随分块策略、重新 ingest 而变化，
写死 id 会让 golden 集非常脆弱）。所以 `run_retrieval_eval.py` 自己实现了
一个基于 metadata（`file_name` 字段）做"文件级命中"判断的简化版
hit-rate/MRR，逻辑不到 50 行，比强行适配 `RetrieverEvaluator` 更清晰可靠。

## golden 数据集维护规则

1. **来源必须是真实文档**：每条 `expected_answer` 必须能在 `data/upload_files/`
   或 `信息搜集汇总/` 下的某个真实文件里找到依据，`expected_sources` 填该
   文件的**原始文件名**。`campus-corpus` 里的 `file_name` 本来就是原始文件
   名，直接精确匹配；老的 `test-index` 里 `file_name` 带线上上传路径加的
   uuid 前缀（`2e436f4b-..._学校招生就业处概况.txt`），匹配逻辑会先剥掉
   前缀再比对，两种 collection 都能正确命中。
2. **负反馈对话 -> 新 golden 条目**：当用户在真实对话中点踩、纠错，或者
   人工复核发现某次回答检索错了源文档/答案不对，应该把这次真实的
   问题+人工核对后的正确答案+正确来源，整理成一条新的 golden 记录追加进
   `golden.seed.jsonl`（先起草放进一个 PR，人工确认无误后合并）。这样
   golden 集会随线上真实失败案例持续增长，比单纯"多写几道题"更有效地
   防止同一类回归再次发生。
3. **id 不重复、只增不改语义**：已有 `id` 不要复用给别的问题；如果一条
   题目的期望答案因为政策变化（比如奖学金金额调整）需要更新，直接修改该
   条记录的 `expected_answer`/`expected_sources`，id 保持不变，方便追踪
   历史。
4. **候选题（generate_golden.py 的产出）永远先进 `golden.candidates.jsonl`**，
   人工逐条确认问题写得清楚、答案完整、来源标注正确之后，才能手动搬进
   `golden.seed.jsonl`。不要跳过审核直接拿模型生成的题目评分——生成模型
   经常会编造 golden 集里不存在的细节，或者把 chunk 切分导致的残缺上下文
   当成完整答案。

## Rerank + 混合检索生产环境集成（Phase C）

生产环境已加入**条件触发式 Rerank**和**混合检索（BM25+dense RRF）**，两者
默认都是打开的（`RERANK_ENABLED=True`、`HYBRID_RETRIEVAL_ENABLED=True`）。
Phase 3.2 刚实现 rerank 时默认是关闭的（当时语料还没去重，评测数据也只有
recall_k=10），下面是 Phase C 用 evals/run_hybrid_eval.py 在去重后的
`campus-corpus` 上重新验证过的数字，默认值已按这份数据翻开。

### 实现位置

`backend/app/utils/rerank.py` — `ConditionalRerankPostprocessor`
`backend/app/handlers/hybrid_retriever.py` — `build_retriever_for_index`

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `RERANK_ENABLED` | `True` | rerank 总开关 |
| `RERANK_RECALL_K` | `20` | rerank 前的召回数（评测验证过的值，不是 10） |
| `RERANK_TOP_N` | `5` | rerank 后保留的结果数 |
| `RERANK_SCORE_THRESHOLD` | `0.75` | top1 分数 ≥ 此值时跳过 rerank |
| `RERANKER_MODEL` | `BAAI/bge-reranker-v2-m3` | cross-encoder 模型 |
| `HYBRID_RETRIEVAL_ENABLED` | `True` | 混合检索总开关 |

### 触发逻辑

```
向量/混合检索召回
  ↓
top1 分数 >= 0.75  →  跳过 rerank
top1 分数 < 0.75   →  触发 cross-encoder rerank（CPU ~660ms）
```

### 评测数据（`campus-corpus`，20 题，recall_k=20）

`run_rerank_eval.py`（纯向量 + rerank，不含混合检索）：

| 指标 | A 基线 | B rerank | 差值 |
|------|--------|----------|------|
| hit_rate@1 | 75% | **95%** | +20% |
| hit_rate@2 | 90% | **95%** | +5% |
| hit_rate@5 | 100% | 100% | +0% |
| MRR@5 | 0.852 | **0.960** | +0.108 |
| 平均延迟 | 15.8ms | 673.9ms | +658.2ms |

`run_hybrid_eval.py`（三组，C 组是线上实际会跑的组合配置）：

| 指标 | A 基线 | B 混合检索 | C 混合+rerank |
|------|--------|-----------|---------------|
| hit_rate@1 | 75% | **85%** | **90%** |
| hit_rate@2 | 90% | 85% | 90% |
| hit_rate@5 | 100% | 100% | 95% |
| MRR@5 | 0.852 | **0.896** | **0.910** |
| 平均延迟 | 13.2ms | 15.0ms | 678.0ms |

### 结论

- 混合检索（B 组）几乎零延迟成本（+2ms），hit@1/MRR 有实打实的提升，默认开启。
- rerank 单独验证（纯向量+rerank）收益比"混合+rerank"组合更大（MRR
  0.960 vs 0.910）——两个机制不是简单叠加，具体原因还没深入分析，不影响
  默认都打开的决策：组合配置相对纯基线仍有明显提升（hit@1 75%→90%，
  MRR 0.852→0.910）。
- rerank 延迟代价仍然较大（CPU 上 ~660ms），条件触发（只在低置信度时触发）
  缓解了这个代价，但没有消除；如果后续观察到延迟问题，`RERANK_ENABLED`
  可以随时关回去，不影响混合检索本身。

---

## CI 说明

`.github/workflows/evals.yml` 只在 CI 里跑冒烟测试（`test_evals_smoke.py`），
并尝试跑一次 `run_retrieval_eval.py`——因为 CI runner 上没有 `data/chroma_db`
索引数据（`.gitignore` 排除了 `/data/`），`run_retrieval_eval.py` 检测到
索引缺失后会打印提示并 `exit 0`，不会导致 workflow 失败。**真正有意义的
基线评测要在本地或有索引数据的服务器上手动跑**，把 `evals/results/*.json`
的结果贴进 PR 描述或存档，作为重构前后的对比依据。
