# Evals（评测先行 · Phase 0）

在对检索/索引架构做任何重构之前，先给现有系统打一份基线分。这套 evals 只做
**检索质量**评测（hit-rate / MRR），不评测生成质量（LLM 回答对不对），因为
Phase 0 的目标是搞清楚"现在的向量检索到底行不行"，这是后续重构最需要保护的
契约。

## 目录结构

```
evals/
├── README.md                  本文件
├── golden.seed.jsonl          人工编写、人工审核过的黄金评测集（可信）
├── golden.candidates.jsonl    generate_golden.py 产出的候选题（未审核，不可直接用于评分）
├── generate_golden.py         从现有索引批量生成 QA 候选
├── ingest_corpus.py           一次性导入：把仓库里的真实文档全量导入 campus-corpus collection
├── run_retrieval_eval.py      核心：跑检索评测，算 hit-rate / MRR
└── results/                   run_retrieval_eval.py 的输出报告（JSON，按时间戳命名）
```

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
  - `campus-corpus`（809 chunk）：由 `evals/ingest_corpus.py` 把
    `信息搜集汇总/` 和 `data/upload_files/` 下的全部可解析文档（按内容
    hash 去重后 119 个文件）导入生成，metadata 的 `file_name` 是**原始文件
    名**（没有线上上传路径加的 uuid 前缀）。这是评测用的正式语料，第二份
    基线在它上面是 hit_rate 100% / MRR 0.877（top_k=5）。重跑
    `ingest_corpus.py` 会先删掉重建该 collection，可安全重复执行。
- `golden.seed.jsonl` 按"知识库应该覆盖的真实主题"编写。评测应以
  `campus-corpus` 为准：
  `uv run python evals/run_retrieval_eval.py --collection campus-corpus --top-k 5`。
- 解析 docx/xlsx 需要 `docx2txt` / `openpyxl`（pyproject 的 `evals` 依赖组，
  `uv sync --group evals` 安装）。注意：线上 `insert_into_index` 走同一个
  `SimpleDirectoryReader`，这两个包不装的话线上传 docx/xlsx 同样会解析失败，
  而 `ALLOWED_EXTENSIONS` 却允许上传——这是侦察中发现的真实 bug，修复属于
  Phase 1 范畴（把这两个包提为主依赖或收紧允许的扩展名）。

## 怎么跑

### 1. 冒烟测试（不需要索引、不需要 LLM，CI 里跑这个）

```bash
uv run pytest tests/test_evals_smoke.py -v
```

只检查 `golden.seed.jsonl` 格式是否合法、评测脚本能否正常 import，不执行
真正的检索。

### 2. 导入评测语料（首次评测前或语料更新后跑一次）

```bash
uv sync --group evals   # docx/xlsx 解析依赖
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

### 4.（可选）批量生成候选题

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

## CI 说明

`.github/workflows/evals.yml` 只在 CI 里跑冒烟测试（`test_evals_smoke.py`），
并尝试跑一次 `run_retrieval_eval.py`——因为 CI runner 上没有 `data/chroma_db`
索引数据（`.gitignore` 排除了 `/data/`），`run_retrieval_eval.py` 检测到
索引缺失后会打印提示并 `exit 0`，不会导致 workflow 失败。**真正有意义的
基线评测要在本地或有索引数据的服务器上手动跑**，把 `evals/results/*.json`
的结果贴进 PR 描述或存档，作为重构前后的对比依据。
