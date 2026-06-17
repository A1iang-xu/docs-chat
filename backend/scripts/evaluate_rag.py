"""
RAGAS 评估脚本 —— 量化 RAG 系统的检索和生成质量

运行方式:
    cd backend
    python scripts/evaluate_rag.py              # 自动模式：从文档生成问答对
    python scripts/evaluate_rag.py --manual     # 手动模式：使用预定义的 EVAL_DATASET
    python scripts/evaluate_rag.py --count 20   # 指定生成 20 组问答对
    python scripts/evaluate_rag.py --qa-file eval_qa_pairs.json  # 复用已有问答对

评估指标（RAGAS 标准 4 维核心参数）:
- Context Recall:     检索到的上下文覆盖了多少参考答案 (检索质量)
- Faithfulness:       生成的回答是否忠于检索到的上下文 (生成保真度)
- Answer Relevance:   生成的回答与问题的相关度 (答案相关性)

额外指标（如果 ragas 版本支持）:
- Context Precision:  检索到的上下文中相关片段的比例
- Answer Correctness: 生成的回答与参考答案的语义正确性对比

面试要点: 能解释为什么需要 RAGAS ——
没有量化评估就无法知道"改了一个参数后是好还是坏"，
面试官看到你有评估意识会觉得你有工程思维。
"""
import sys
import os

# ── Windows 终端 UTF-8 编码修复 ──
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ── 必须在导入 app 模块之前加载 .env（脚本从任意目录运行时也能找到）──
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.join(_SCRIPT_DIR, "..")
_ENV_PATH = os.path.join(_BACKEND_DIR, ".env")
if os.path.exists(_ENV_PATH):
    with open(_ENV_PATH, "r", encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _key, _val = _line.split("=", 1)
                _key = _key.strip()
                _val = _val.strip().strip('"').strip("'")
                if _key and _val and _key not in os.environ:
                    os.environ[_key] = _val

sys.path.insert(0, _BACKEND_DIR)

import argparse
import json
import logging
import asyncio
import random
from datasets import Dataset
from ragas import evaluate
from ragas.metrics import (
    context_recall,
    faithfulness,
    answer_relevancy,
)

# 尝试导入更多指标（不同版本可能不同）
try:
    from ragas.metrics import context_precision, answer_correctness
    _HAS_EXTRA_METRICS = True
except ImportError:
    _HAS_EXTRA_METRICS = False

from app.core.config import settings
from app.services.retrieval_service import retrieval_service
from app.services.llm_service import llm_service
from app.services.vector_store import vector_store

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# RAGAS 评估专用 LLM 配置（DeepSeek via LangChain）
# ═══════════════════════════════════════════════════════════════
# RAGAS 内部需要 LLM 来评判 faithfulness / answer_relevancy 等指标。
# 默认它查找 OPENAI_API_KEY 环境变量，但本项目使用 DeepSeek。
# 解决方案：通过 LangChain ChatOpenAI 连接 DeepSeek，并注入到 RAGAS。

_EVAL_LLM = None       # 延迟初始化
_EVAL_EMBEDDINGS = None  # 延迟初始化

def _get_eval_llm():
    """
    创建指向 DeepSeek 的 LangChain ChatOpenAI 实例，供 RAGAS 评估使用。
    仅在首次调用时初始化，后续复用。
    """
    global _EVAL_LLM
    if _EVAL_LLM is not None:
        return _EVAL_LLM

    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        logger.warning("langchain_openai 未安装，RAGAS 将回退到默认 LLM 配置")
        return None

    api_key = settings.DEEPSEEK_API_KEY
    if not api_key:
        logger.error(
            "DEEPSEEK_API_KEY 未设置！"
            "请在 backend/.env 中配置 DEEPSEEK_API_KEY=sk-xxx"
        )
        return None

    _EVAL_LLM = ChatOpenAI(
        model=settings.DEEPSEEK_MODEL,
        openai_api_key=api_key,
        openai_api_base=settings.DEEPSEEK_BASE_URL,
        temperature=0,  # 评估任务使用确定性输出
        max_tokens=512,
    )
    logger.info(
        f"RAGAS 评估 LLM 已配置: model={settings.DEEPSEEK_MODEL}, "
        f"base_url={settings.DEEPSEEK_BASE_URL}"
    )
    return _EVAL_LLM


def _get_eval_embeddings():
    """
    创建本地 Embedding 模型实例，供 RAGAS 评估使用。

    为什么不用 DeepSeek API：
    DeepSeek 不提供 /v1/embeddings 端点（返回 404），
    因此必须使用本地 sentence-transformers 模型。

    使用与项目 ChromaDB 一致的模型: all-MiniLM-L6-v2 (~80MB)。
    首次运行会自动下载模型到本地缓存。
    """
    global _EVAL_EMBEDDINGS
    if _EVAL_EMBEDDINGS is not None:
        return _EVAL_EMBEDDINGS

    try:
        from langchain_huggingface import HuggingFaceEmbeddings
        model_name = f"sentence-transformers/{settings.EMBEDDING_MODEL}"
        _EVAL_EMBEDDINGS = HuggingFaceEmbeddings(
            model_name=model_name,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
        logger.info(f"RAGAS 评估 Embeddings 已配置: model={model_name}")
        return _EVAL_EMBEDDINGS
    except ImportError:
        # langchain_huggingface 未安装，尝试 langchain_community
        try:
            from langchain_community.embeddings import HuggingFaceEmbeddings
            model_name = f"sentence-transformers/{settings.EMBEDDING_MODEL}"
            _EVAL_EMBEDDINGS = HuggingFaceEmbeddings(
                model_name=model_name,
                model_kwargs={"device": "cpu"},
                encode_kwargs={"normalize_embeddings": True},
            )
            logger.info(f"RAGAS 评估 Embeddings 已配置 (via langchain_community): model={model_name}")
            return _EVAL_EMBEDDINGS
        except ImportError:
            logger.warning(
                "langchain_huggingface / langchain_community 均未安装，"
                "无法提供本地 Embedding 模型。"
                "需要 Embedding 的指标（context_precision, answer_correctness）将不可用。"
            )
            return None


# ═══════════════════════════════════════════════════════════════
# 手动评估数据集（备用）
# ═══════════════════════════════════════════════════════════════

EVAL_DATASET = [
    # 格式: { "question": "问题", "ground_truth": "参考答案" }
    # 填写后可通过 --manual 模式使用
    #
    # 示例:
    # {"question": "什么是RAG系统？", "ground_truth": "RAG(检索增强生成)是一种结合信息检索和文本生成的技术..."},
]


# ═══════════════════════════════════════════════════════════════
# 自动化问答对生成
# ═══════════════════════════════════════════════════════════════

QA_GENERATION_PROMPT = """你是一个专业的测试数据生成器。请根据以下文档内容，生成 {count} 个高质量的问答对。

要求：
1. 问题应覆盖文档的不同方面（概念、细节、关系、结论等），不要重复
2. 问题应使用自然语言，像真实用户会问的问题
3. 参考答案应准确、完整，基于文档内容（不要编造）
4. 每个问题应有明确的答案，可以从文档中直接或间接推导
5. 参考答案应足够详细（至少 2-3 句话），包含具体信息而非笼统描述

输出格式（严格 JSON 数组，不要输出其他内容）：
```json
[
  {{"question": "问题1描述", "ground_truth": "答案1的完整内容，包含具体细节"}},
  {{"question": "问题2描述", "ground_truth": "答案2的完整内容，包含具体细节"}}
]
```

文档内容：
{document_text}

请严格按照上述 JSON 格式生成 {count} 个问答对："""


async def generate_qa_pairs(
    count: int = 10,
    sample_chunks: int = 30,
) -> list[dict]:
    """
    使用 LLM 从文档库中自动生成问答对。

    流程:
    1. 从向量库中采样覆盖不同主题的文档块
    2. 构建包含文档片段的 Prompt
    3. 调用 LLM 生成问答对
    4. 验证并返回 JSON 解析后的结果

    Args:
        count: 目标生成问答对数量
        sample_chunks: 采样的文档块数量（用于构建 prompt）

    Returns:
        [{"question": "...", "ground_truth": "..."}, ...]
    """
    # ── 1. 从向量库中采样文档块 ──
    seed_queries = [
        "概述", "简介", "什么是", "如何", "原因", "方法",
        "步骤", "特点", "区别", "优势", "应用", "总结",
        "关键", "重要", "原理", "流程", "核心", "结论",
    ]

    sampled_chunks: list[str] = []
    seen_ids: set[str] = set()

    for query in seed_queries:
        if len(sampled_chunks) >= sample_chunks:
            break
        results = vector_store.search(query, top_k=3)
        for r in results:
            if r["chunk_id"] not in seen_ids and len(sampled_chunks) < sample_chunks:
                seen_ids.add(r["chunk_id"])
                sampled_chunks.append(r["content"])

    if not sampled_chunks:
        logger.error("无法从向量库中采样文档块，请先上传文档")
        return []

    # 随机打乱以增加多样性
    random.shuffle(sampled_chunks)

    # ── 2. 构建文档文本 ──
    document_text = "\n\n---\n\n".join(
        f"[片段 {i+1}] {chunk[:800]}" for i, chunk in enumerate(sampled_chunks)
    )

    # ── 3. 调用 LLM 生成问答对 ──
    prompt = QA_GENERATION_PROMPT.format(
        count=count,
        document_text=document_text,
    )

    logger.info(f"使用 {len(sampled_chunks)} 个文档片段生成 {count} 个问答对...")

    try:
        response = await llm_service.chat(
            messages=[{"role": "user", "content": prompt}],
        )

        # 提取 JSON 部分（处理 LLM 可能输出额外文本的情况）
        json_start = response.find("[")
        json_end = response.rfind("]") + 1
        if json_start == -1 or json_end == 0:
            logger.error("LLM 返回的内容中未找到 JSON 数组")
            logger.debug(f"原始响应前500字符: {response[:500]}")
            return []

        json_str = response[json_start:json_end]
        qa_pairs = json.loads(json_str)

        if not isinstance(qa_pairs, list):
            logger.error("LLM 返回的 JSON 不是数组格式")
            return []

        # 验证每个问答对的格式
        valid_pairs = []
        for pair in qa_pairs:
            if isinstance(pair, dict) and "question" in pair and "ground_truth" in pair:
                valid_pairs.append({
                    "question": pair["question"],
                    "ground_truth": pair["ground_truth"],
                })
            else:
                logger.warning(f"跳过格式不正确的问答对: {pair}")

        logger.info(f"成功生成 {len(valid_pairs)} 个有效问答对")
        return valid_pairs

    except json.JSONDecodeError as e:
        logger.error(f"JSON 解析失败: {e}")
        return []
    except Exception as e:
        logger.error(f"问答对生成失败: {e}")
        return []


# ═══════════════════════════════════════════════════════════════
# 评估主流程
# ═══════════════════════════════════════════════════════════════

async def run_evaluation(qa_pairs: list[dict]):
    """
    运行 RAGAS 评估 —— 完整的 4 维核心参数结构:
    - question:      用户问题
    - contexts:      检索到的原文切片列表
    - answer:        模型生成的回答
    - ground_truth:  文档中的标准答案
    """

    if not qa_pairs:
        logger.error("没有可用的问答对，评估终止")
        return

    logger.info(f"开始 RAGAS 评估: {len(qa_pairs)} 组问答对")
    logger.info("评估流程: 问题 → 检索上下文 → 生成回答 → RAGAS 对比评分")

    questions = []
    answers = []
    contexts_list = []
    ground_truths = []

    for idx, item in enumerate(qa_pairs):
        question = item["question"]
        ground_truth = item["ground_truth"]

        logger.info(f"评估中 [{idx+1}/{len(qa_pairs)}]: {question[:60]}...")

        # ── 步骤 1: 检索上下文 (模拟真实 RAG 检索流程) ──
        retrieval_results = retrieval_service.search(question, top_k=5)
        contexts = [r["content"] for r in retrieval_results]

        if not contexts:
            logger.warning(f"  未检索到相关内容，跳过")
            continue

        # ── 步骤 2: 基于检索上下文生成回答 ──
        context_text = "\n\n".join(
            f"[来源 {i+1}] {ctx}" for i, ctx in enumerate(contexts)
        )

        generation_prompt = f"""基于以下参考文档回答问题。请确保回答忠实于参考文档的内容。

参考文档:
{context_text}

问题: {question}

回答:"""

        try:
            answer = await llm_service.chat(
                messages=[{"role": "user", "content": generation_prompt}],
            )
        except Exception as e:
            logger.error(f"  LLM 生成回答失败: {e}")
            continue

        # ── 步骤 3: 收集 RAGAS 4 维数据 ──
        questions.append(question)          # 维度 1: question
        answers.append(answer)              # 维度 2: answer
        contexts_list.append(contexts)      # 维度 3: contexts
        ground_truths.append(ground_truth)  # 维度 4: ground_truth

        logger.info(f"  回答长度: {len(answer)} 字符, 上下文数: {len(contexts)}")

    if not questions:
        logger.error("所有问答对均未检索到内容，无法评估")
        return

    # ── 构建 RAGAS Dataset ──
    dataset_dict = {
        "question": questions,
        "answer": answers,
        "contexts": contexts_list,
        "ground_truth": ground_truths,
    }

    dataset = Dataset.from_dict(dataset_dict)

    logger.info(f"数据集构建完成: {len(questions)} 条有效记录")

    # ── 选择评估指标 ──
    metrics = [context_recall, faithfulness, answer_relevancy]
    metric_names = ["context_recall", "faithfulness", "answer_relevancy"]

    # 额外指标需要 Embedding 支持 → 仅在本地 Embedding 模型可用时启用
    eval_embeddings = _get_eval_embeddings()
    if _HAS_EXTRA_METRICS and eval_embeddings is not None:
        metrics.append(context_precision)
        metric_names.append("context_precision")
        try:
            metrics.append(answer_correctness)
            metric_names.append("answer_correctness")
        except Exception:
            logger.warning("answer_correctness 指标不可用，跳过")
    elif _HAS_EXTRA_METRICS and eval_embeddings is None:
        logger.info(
            "本地 Embedding 模型不可用，跳过需要 Embedding 的指标 "
            "(context_precision, answer_correctness)"
        )

    logger.info(f"使用评估指标: {', '.join(metric_names)}")

    # ── 运行 RAGAS 评估 ──
    try:
        logger.info("运行 RAGAS 评估...")

        # 配置 RAGAS 使用 DeepSeek 作为评估 LLM
        eval_llm = _get_eval_llm()

        # 兼容性回退：设置环境变量以防 RAGAS 内部代码仍然通过
        # openai.OpenAI() 默认客户端访问 LLM（而非我们注入的实例）
        if eval_llm is not None:
            if "OPENAI_API_KEY" not in os.environ:
                os.environ["OPENAI_API_KEY"] = settings.DEEPSEEK_API_KEY
            if "OPENAI_API_BASE" not in os.environ:
                os.environ["OPENAI_API_BASE"] = settings.DEEPSEEK_BASE_URL
            if "OPENAI_BASE_URL" not in os.environ:
                os.environ["OPENAI_BASE_URL"] = settings.DEEPSEEK_BASE_URL

        # RAGAS >= 0.1.0: 通过 llm= + embeddings= 注入评估模型
        # RAGAS < 0.1.0: 回退到环境变量模式
        evaluate_kwargs: dict = {"metrics": metrics}
        if eval_llm is not None:
            evaluate_kwargs["llm"] = eval_llm
        if eval_embeddings is not None:
            evaluate_kwargs["embeddings"] = eval_embeddings

        try:
            result = evaluate(dataset, **evaluate_kwargs)
        except TypeError:
            # 旧版 RAGAS 不支持 llm=/embeddings= 参数
            logger.info("检测到旧版 RAGAS（不支持 llm/embeddings 参数），使用环境变量回退模式")
            result = evaluate(dataset, metrics=metrics)
    except Exception as e:
        logger.error(f"RAGAS 评估执行失败: {e}")
        return

    # ── 结果归一化：兼容新旧 RAGAS 返回类型 ──
    # RAGAS >= 0.1.x 返回 EvaluationResult，RAGAS < 0.1.0 返回 dict
    logger.info(f"RAGAS 返回类型: {type(result).__name__}")

    if isinstance(result, dict):
        # 旧版 RAGAS：直接是 dict
        result_dict = result

    elif hasattr(result, "_asdict"):
        # namedtuple 风格（某些中间版本）
        result_dict = result._asdict()

    elif hasattr(result, "scores"):
        # RAGAS >= 0.1.x EvaluationResult — scores 是 list[dict]
        # 每个 dict 包含所有指标对单条问答的评分，需按指标取均值
        result_dict = {}
        metric_accumulator: dict[str, list[float]] = {}

        for score_obj in result.scores:
            if isinstance(score_obj, dict):
                for key, val in score_obj.items():
                    metric_accumulator.setdefault(str(key), []).append(float(val))
            else:
                # 兼容 object 格式
                name = getattr(score_obj, "name", None) or getattr(score_obj, "metric", None) or str(score_obj)
                value = getattr(score_obj, "value", None) or getattr(score_obj, "score", None) or 0.0
                metric_accumulator.setdefault(str(name), []).append(float(value))

        # 按指标取平均
        for metric_name, values in metric_accumulator.items():
            result_dict[metric_name] = sum(values) / len(values) if values else 0.0

    elif hasattr(result, "__iter__"):
        # 可迭代对象（可能是 list of tuples 等）
        try:
            result_dict = dict(result)
        except (TypeError, ValueError) as e:
            logger.error(f"无法将结果转为 dict: {e}, 类型: {type(result)}")
            return

    else:
        # 最后兜底
        try:
            result_dict = dict(result)
        except (TypeError, ValueError) as e:
            logger.error(f"无法解析 RAGAS 返回结果类型: {type(result)}, 错误: {e}")
            return

    # ── 输出结果 ──
    print("\n" + "=" * 60)
    print("RAGAS 评估结果")
    print("=" * 60)
    eval_scores = {}
    for metric_name, value in result_dict.items():
        score = round(float(value), 4)
        eval_scores[metric_name] = score
        # 评分等级
        if score >= 0.8:
            grade = "✅ 优秀"
        elif score >= 0.6:
            grade = "⚠️ 良好"
        else:
            grade = "❌ 需改进"
        print(f"  {metric_name:.<32} {score:.4f}  {grade}")
    print("=" * 60)

    # ── 保存评估结果 ──
    output_path = os.path.join(os.path.dirname(__file__), "..", "evaluation_results.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(eval_scores, f, ensure_ascii=False, indent=2)
    print(f"\n评估结果已保存到: {os.path.abspath(output_path)}")

    # ── 保存问答对（供后续复用或调试） ──
    qa_path = os.path.join(os.path.dirname(__file__), "..", "eval_qa_pairs.json")
    with open(qa_path, "w", encoding="utf-8") as f:
        json.dump(qa_pairs, f, ensure_ascii=False, indent=2)
    print(f"问答对已保存到: {os.path.abspath(qa_path)}")

    # ── 保存详细评估数据（包含 4 维参数，供分析） ──
    detail_path = os.path.join(os.path.dirname(__file__), "..", "eval_details.json")
    details = []
    for i in range(len(questions)):
        details.append({
            "question": questions[i],
            "answer": answers[i][:500],
            "contexts": [c[:200] for c in contexts_list[i][:3]],
            "ground_truth": ground_truths[i],
        })
    with open(detail_path, "w", encoding="utf-8") as f:
        json.dump(details, f, ensure_ascii=False, indent=2)
    print(f"评估详情已保存到: {os.path.abspath(detail_path)}")

    # ── 简历金句 ──
    print("\n📋 简历金句（可直接引用）:")
    for name, score in eval_scores.items():
        print(f'  "通过 RAGAS 评估框架量化 {name}，达到 {score:.4f}"')

    return result


# ═══════════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════════

async def main():
    parser = argparse.ArgumentParser(
        description="RAGAS 评估脚本 —— 量化 RAG 系统检索与生成质量",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
    python scripts/evaluate_rag.py                    # 自动生成 10 组问答对
    python scripts/evaluate_rag.py --count 20         # 自动生成 20 组问答对
    python scripts/evaluate_rag.py --manual           # 使用预定义的 EVAL_DATASET
    python scripts/evaluate_rag.py --qa-file qa.json  # 复用已有问答对文件
        """,
    )
    parser.add_argument(
        "--manual", action="store_true",
        help="使用手动编写的 EVAL_DATASET（而非自动生成）",
    )
    parser.add_argument(
        "--count", type=int, default=10,
        help="自动生成的问答对数量（默认 10，建议 10-30）",
    )
    parser.add_argument(
        "--qa-file", type=str, default=None,
        help="从 JSON 文件加载已有的问答对（跳过自动生成步骤）",
    )
    args = parser.parse_args()

    # ── 前置检查 ──
    if vector_store.get_chunk_count() == 0:
        logger.error("向量库为空！请先上传 PDF 文档。")
        return

    logger.info(f"向量库状态: {vector_store.get_chunk_count()} 个文档块")
    logger.info(f"已有文档: {[d['filename'] for d in vector_store.get_unique_documents()]}")

    # ── 重建 BM25 索引（独立进程需要从 ChromaDB 加载数据）──
    if retrieval_service.bm25 is None:
        logger.info("正在从向量库重建 BM25 索引...")
        all_chunks = vector_store.get_all_chunks()
        if all_chunks:
            retrieval_service.build_bm25_index(all_chunks)
            logger.info(f"BM25 索引重建完成: {len(all_chunks)} 个文档块")
        else:
            logger.error("无法从向量库获取文档块，请先上传 PDF 文档。")
            return

    # ── 确定问答对来源 ──
    if args.qa_file:
        # 从文件加载
        with open(args.qa_file, "r", encoding="utf-8") as f:
            qa_pairs = json.load(f)
        logger.info(f"从文件加载 {len(qa_pairs)} 组问答对")
    elif args.manual:
        # 手动模式
        qa_pairs = EVAL_DATASET
        if not qa_pairs:
            logger.error("EVAL_DATASET 为空！请在脚本中填写问答对后重试。")
            logger.info("格式: EVAL_DATASET = [{'question': '...', 'ground_truth': '...'}]")
            return
        logger.info(f"使用手动数据集: {len(qa_pairs)} 组问答对")
    else:
        # 自动生成模式
        logger.info(f"自动生成模式：目标 {args.count} 个问答对")
        qa_pairs = await generate_qa_pairs(count=args.count)

    if not qa_pairs:
        logger.error("未获取到有效问答对，评估终止")
        return

    await run_evaluation(qa_pairs)


if __name__ == "__main__":
    asyncio.run(main())
