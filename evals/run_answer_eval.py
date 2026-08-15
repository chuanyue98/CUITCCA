#!/usr/bin/env python
"""回答质量评测（LLM-as-judge）：模型生成的回答到底答得怎么样。

``run_retrieval_eval.py`` 衡量"能不能检索到正确来源"（hit_rate/MRR），
``run_refusal_eval.py`` 衡量"该说不知道的时候会不会编"（幻觉率/承认边界率），
但这两个都回答不了同一个问题：**检索到的内容都对了，模型把答案生成对了吗？**

这个脚本补上最后一环：消费 ``golden.seed.jsonl``（每道题都有人工核对的
``expected_answer`` 和 ``expected_sources``），真实跑一遍问答链路拿到
``(answer, source_nodes)``，再用一个独立的 judge LLM 对回答打三个维度的分：

1. **忠实度（faithfulness）**：把回答拆成若干独立陈述，逐个判断"这个陈述是否
   被检索到的上下文支持"。分数 = 被支持的陈述数 / 总陈述数。这是 RAG 系统
   最重要的生成指标——回答了，但不能编，每个字都要有出处。
2. **回答相关性（answer relevance）**：回答是否切题地回答了问题（1-5 分）。
   跑题、答非所问、回避问题都会扣分，即使内容本身是事实。
3. **答案匹配（answer match）**：回答与 golden 集里人工核对的
   ``expected_answer`` 在语义上是否一致（1-5 分，>=4 算通过）。这是"答案
   对不对"的参考答案式判据——不是逐字匹配（那对开放式问题太苛刻），而是
   语义等价。

为什么要用 LLM-as-judge 而不是字符串匹配：
- ``expected_answer`` 是人工写的"标准答案"，模型回答措辞几乎不可能逐字一致，
  但语义上可以完全正确——需要 judge 判断语义等价。
- 忠实度必须理解"陈述 vs 上下文"之间的关系，字符串包含匹配会漏掉改写/概括。
- judge 用的是项目自己的 ``Settings.llm``（OpenAI-compatible），不依赖
  RAGAS 等外部评测框架，指标口径完全可控、prompt 可审计。

局限（如实记录）：LLM-as-judge 本身可能对某些题有偏差（比如 judge 认为
"差不多"但实际漏了关键数字）。本脚本对每道题都输出 judge 的完整理由
（``reason``），人工复核时可以直接看到 judge 为什么给这个分，而不是只看一个
数字。评估这类 judge 的可靠性（judge 自己的正确率）属于后续扩展，不在本脚本
范围。

用法:
    uv run python evals/run_answer_eval.py
    uv run python evals/run_answer_eval.py --limit 10        # 试跑前 10 题
    uv run python evals/run_answer_eval.py --endpoint agent  # 走 Agent 链路

没配置 LLM（``OPENAI_API_KEY`` 为空）时打印提示并以 exit code 0 优雅退出，
和 ``run_retrieval_eval.py``/``run_refusal_eval.py`` 的 CI 约定一致。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from evals._common import EVALS_DIR, bootstrap_backend_path, load_backend_env, load_jsonl  # noqa: E402

DEFAULT_GOLDEN = EVALS_DIR / "golden.seed.jsonl"
DEFAULT_RESULTS_DIR = EVALS_DIR / "results"

# 判定"通过"的相关性/匹配分下限：>=4 说明 judge 认为回答基本正确、只是措辞
# 有差异；3 分及以下意味着有明显错误或缺漏。
PASS_SCORE = 4


def _extract_json(text: str) -> dict:
    """从 judge LLM 的输出里抠出第一个 JSON 对象。

    judge 用的是 OpenAI-compatible chat 补全，输出经常带着 ```json 代码块
    围栏或前后废话。用正则先找 {...} 块，再 json.loads；实在解析不了就抛
    异常，由调用方把这题标记为 judge 失败而不是给一个编造的分。
    """
    if not text:
        raise ValueError("judge 返回了空文本")
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidates = [fenced.group(1) if fenced else None, text]
    for candidate in candidates:
        if not candidate:
            continue
        match = re.search(r"\{.*\}", candidate, re.DOTALL)
        if not match:
            continue
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, dict):
                return parsed
        except (TypeError, ValueError):
            continue
    raise ValueError(f"judge 输出无法解析为 JSON: {text[:200]!r}")


class AnswerJudge:
    """用项目自己的 LLM 当 judge，给回答打三个维度的分。

    复用 ``configs.llm_predictor.build_llm()`` 构造的同一个 OpenAI-compatible
    LLM（和问答链路用同一个模型、同一个 api_base），不额外引入评测框架依赖。
    judge 和生成用同一个模型可能带来"模型偏爱自己输出"的偏差——对这个问题
    的缓解是：每题都让 judge 输出具体理由（faithfulness 甚至逐陈述给出判断），
    人工复核时可以核对理由是否成立，而不是盲信一个数字。
    """

    def __init__(self):
        from configs.llm_predictor import build_llm

        self._llm = build_llm()

    async def _complete_json(self, prompt: str) -> dict:
        response = await self._llm.acomplete(prompt)
        return _extract_json(str(response))

    # ── 忠实度：回答的每个陈述是否被检索上下文支持 ──────────────────────
    async def faithfulness(self, question: str, context_text: str, answer: str) -> dict:
        prompt = (
            "你是严格的事实核查评估员。给定一个问题、一段参考上下文和一段回答，\n"
            "把回答拆解成若干**独立的事实陈述**（每句话里可能包含多个陈述，要拆开；\n"
            "纯粹的过渡语、客套话不算陈述），然后逐一判断每个陈述能否被参考上下文\n"
            "支持。判断标准：\n"
            "- supported=true：该陈述的信息能从参考上下文中直接找到，或由上下文\n"
            "  合理推出（不引入上下文之外的新事实）。\n"
            "- supported=false：该陈述包含上下文里没有的信息、与上下文矛盾，\n"
            "  或属于模型凭自身知识补出来的内容。\n"
            "请用 JSON 输出，格式：\n"
            '{"statements": [{"statement": "陈述文本", "supported": true}, ...], '
            '"note": "一句话说明整体判断"}。\n\n'
            f"问题：{question}\n\n"
            f"参考上下文：\n{context_text[:6000]}\n\n"
            f"回答：\n{answer}"
        )
        data = await self._complete_json(prompt)
        statements = data.get("statements") or []
        if not isinstance(statements, list) or not statements:
            raise ValueError("judge 没有返回任何陈述")
        supported = [s for s in statements if isinstance(s, dict) and s.get("supported") is True]
        return {
            "total_statements": len(statements),
            "supported_statements": len(supported),
            "faithfulness": len(supported) / len(statements),
            "note": str(data.get("note", ""))[:300],
        }

    # ── 回答相关性：回答是否切题 ────────────────────────────────────────
    async def relevance(self, question: str, answer: str) -> dict:
        prompt = (
            "你是严格的回答评估员。判断一段回答是否**切题**地回答了问题。评分标准（1-5 分）：\n"
            "5 = 完整、直接地回答了问题的所有要点；\n"
            "4 = 回答了问题，但漏了少量次要细节；\n"
            "3 = 部分切题，或答非所问与正面回答各占一半；\n"
            "2 = 基本跑题，只沾边；\n"
            "1 = 完全没有回答问题。\n"
            "注意：这个维度只评估'有没有回答该回答的'，不评估回答的事实准确性\n"
            "（那是忠实度管的事）。\n"
            "请用 JSON 输出：{\"score\": 1-5, \"reason\": \"打分理由\"}。\n\n"
            f"问题：{question}\n\n回答：\n{answer}"
        )
        data = await self._complete_json(prompt)
        raw_score = data.get("score")
        try:
            score = int(raw_score)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            raise ValueError(f"judge 返回的相关性分数不是整数: {raw_score!r}")
        return {"score": score, "reason": str(data.get("reason", ""))[:300]}

    # ── 答案匹配：与 golden 集人工核对的参考答案是否语义一致 ─────────────
    async def answer_match(self, question: str, expected_answer: str, answer: str) -> dict:
        prompt = (
            "你是严格的答案对照评估员。给定一个问题、一份参考答案（人工核对过的\n"
            "标准答案）和一份模型回答，判断模型回答在**语义上**是否与参考答案一致\n"
            "（即'该答对的关键事实都答对了吗'）。评分标准（1-5 分）：\n"
            "5 = 语义完全等价，关键事实全部正确；\n"
            "4 = 关键事实正确，只有措辞/详略差异；\n"
            "3 = 部分关键事实正确，有遗漏或错误；\n"
            "2 = 大部分错误，只碰对个别点；\n"
            "1 = 完全错误或答非所问。\n"
            "请用 JSON 输出：{\"score\": 1-5, \"reason\": \"打分理由\"}。\n\n"
            f"问题：{question}\n\n"
            f"参考答案：{expected_answer}\n\n"
            f"模型回答：\n{answer}"
        )
        data = await self._complete_json(prompt)
        raw_score = data.get("score")
        try:
            score = int(raw_score)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            raise ValueError(f"judge 返回的匹配分数不是整数: {raw_score!r}")
        return {"score": score, "reason": str(data.get("reason", ""))[:300]}


async def _answer_with_context(question: str, endpoint: str) -> tuple[str, list]:
    """跑一次问答链路，返回 (回答文本, source_nodes 列表)。

    source_nodes 是忠实度判据需要的"参考上下文"——faithfulness 判断的是
    "回答有没有基于检索到的内容"，所以必须把真实检索结果喂给 judge，而不是
    把 golden 集的 expected_sources 当上下文（那是作弊，而且测不出检索问题）。
    """
    if endpoint == "agent":
        from agents.agent_workflow import run_agent  # type: ignore[attr-defined]

        result = await run_agent(question)
        return result.response, result.source_nodes

    from handlers.qa_workflow import QAWorkflow

    workflow = QAWorkflow(timeout=90)
    result = await workflow.run(query=question, streaming=False)
    return str(result.response), result.source_nodes


def _context_text(source_nodes: list) -> str:
    """把检索到的 source_nodes 拼成 judge 用的参考上下文。"""
    if not source_nodes:
        return "（未检索到任何内容）"
    parts = []
    for i, nws in enumerate(source_nodes, start=1):
        text = (nws.node.get_content() if hasattr(nws.node, "get_content") else str(nws.node.text or "")) or ""
        parts.append(f"[片段{i}] {text}")
    return "\n\n".join(parts)


async def run_eval(golden_path: Path, endpoint: str, limit: int | None) -> dict:
    items = load_jsonl(golden_path)
    if limit:
        items = items[:limit]

    judge = AnswerJudge()
    details: list[dict] = []
    for i, item in enumerate(items, start=1):
        question = item["question"]
        print(f"  [{i}/{len(items)}] {item['id']} {question[:38]}...", flush=True)

        try:
            answer, source_nodes = await _answer_with_context(question, endpoint)
            answer_error = None
        except Exception as e:
            answer, source_nodes, answer_error = "", [], f"{type(e).__name__}: {e}"

        metrics: dict = {}
        judge_error = None
        if answer and answer_error is None:
            for name, coro in (
                ("faithfulness", judge.faithfulness(question, _context_text(source_nodes), answer)),
                ("relevance", judge.relevance(question, answer)),
                ("answer_match", judge.answer_match(question, item.get("expected_answer", ""), answer)),
            ):
                try:
                    metrics[name] = await coro
                except Exception as e:
                    judge_error = f"{name}: {type(e).__name__}: {e}"
                    break

        details.append({
            "id": item["id"],
            "question": question,
            "category": item.get("category", "uncategorized"),
            "expected_answer": item.get("expected_answer", ""),
            "answer": answer,
            "answer_error": answer_error,
            "metrics": metrics,
            "judge_error": judge_error,
            "retrieved_sources": [
                (nws.node.metadata or {}).get("file_name", "")
                for nws in source_nodes
            ],
        })

    scored = [d for d in details if d["answer"] and d["answer_error"] is None and d["metrics"] and not d["judge_error"]]

    # 聚合
    faithfulness_values = [d["metrics"]["faithfulness"]["faithfulness"] for d in scored]
    relevance_scores = [d["metrics"]["relevance"]["score"] for d in scored]
    match_scores = [d["metrics"]["answer_match"]["score"] for d in scored]

    by_category: dict[str, dict] = {}
    for d in scored:
        bucket = by_category.setdefault(d["category"], {
            "count": 0, "faithfulness": [], "relevance": [], "answer_match": [],
        })
        bucket["count"] += 1
        bucket["faithfulness"].append(d["metrics"]["faithfulness"]["faithfulness"])
        bucket["relevance"].append(d["metrics"]["relevance"]["score"])
        bucket["answer_match"].append(d["metrics"]["answer_match"]["score"])

    def _avg(values: list[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    def _pass_rate(scores: list[int]) -> float:
        return sum(1 for s in scores if s >= PASS_SCORE) / len(scores) if scores else 0.0

    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "golden": str(golden_path),
        "endpoint": endpoint,
        "questions": len(details),
        "scored": len(scored),
        "answer_errors": len([d for d in details if d["answer_error"]]),
        "judge_errors": len([d for d in details if d["judge_error"]]),
        "overall": {
            "faithfulness": _avg(faithfulness_values),
            "answer_relevance": _avg(relevance_scores),
            "answer_relevance_pass_rate": _pass_rate(relevance_scores),
            "answer_match": _avg(match_scores),
            "answer_match_pass_rate": _pass_rate(match_scores),
        },
        "by_category": {
            cat: {
                "count": b["count"],
                "faithfulness": _avg(b["faithfulness"]),
                "answer_relevance": _avg(b["relevance"]),
                "answer_match": _avg(b["answer_match"]),
                "answer_match_pass_rate": _pass_rate(b["answer_match"]),
            }
            for cat, b in sorted(by_category.items())
        },
        "details": details,
    }


def _print_summary(result: dict) -> None:
    o = result["overall"]
    print()
    print(f"回答质量评测 — endpoint={result['endpoint']} questions={result['questions']} "
          f"scored={result['scored']}")
    print("-" * 72)
    print(f"{'overall':24s} 忠实度={o['faithfulness']:7.2%}  "
          f"相关性={o['answer_relevance']:.2f}(pass {o['answer_relevance_pass_rate']:.0%})  "
          f"答案匹配={o['answer_match']:.2f}(pass {o['answer_match_pass_rate']:.0%})")
    print("-" * 72)
    for cat, s in result["by_category"].items():
        print(
            f"{cat:24s} 忠实度={s['faithfulness']:7.2%}  "
            f"相关性={s['answer_relevance']:.2f}  "
            f"答案匹配={s['answer_match']:.2f}(pass {s['answer_match_pass_rate']:.0%})  "
            f"(n={s['count']})"
        )
    print("-" * 72)

    # 把失败样例列出来，便于人工复核 judge 的理由是否成立
    bad = [
        d for d in result["details"]
        if d["metrics"] and d["metrics"].get("answer_match", {}).get("score", 5) < PASS_SCORE
    ]
    if bad:
        print(f"{len(bad)} 条答案匹配未通过（score < {PASS_SCORE}），judge 理由如下：")
        for d in bad[:10]:
            m = d["metrics"]["answer_match"]
            print(f"  [{d['id']}] {d['question'][:36]}  score={m['score']}")
            print(f"        理由: {m.get('reason', '')[:120]}")
    else:
        print("所有已评分题目的答案匹配都通过。")

    errs = [d for d in result["details"] if d["answer_error"] or d["judge_error"]]
    if errs:
        print(f"\n{len(errs)} 条存在问题（未计入评分）：")
        for d in errs:
            detail = d["answer_error"] or d["judge_error"]
            print(f"  [{d['id']}] {detail}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN, help="golden 数据集路径")
    parser.add_argument("--endpoint", choices=("workflow", "agent"), default="workflow", help="走哪条问答链路")
    parser.add_argument("--limit", type=int, default=None, help="只跑前 N 条（试跑用）")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_RESULTS_DIR, help="结果输出目录")
    args = parser.parse_args()

    if not args.golden.exists():
        print(f"[run_answer_eval] 数据集不存在: {args.golden}")
        return 1

    bootstrap_backend_path()
    load_backend_env()

    if not os.environ.get("OPENAI_API_KEY"):
        print(
            "[run_answer_eval] 没有配置 OPENAI_API_KEY，跳过。回答质量评测必须真的"
            "调用 LLM（生成回答 + judge 打分）才有意义。详见 evals/README.md。"
        )
        return 0

    try:
        result = asyncio.run(run_eval(args.golden, args.endpoint, args.limit))
    except Exception as e:
        print(f"[run_answer_eval] 评测过程中出错: {e!r}")
        return 1

    _print_summary(result)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    output_path = args.output_dir / f"answer_{timestamp}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"结果已写入 {output_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
