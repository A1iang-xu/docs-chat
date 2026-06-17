"""
独立测试集生成脚本 —— 基于本地文档自动生成 RAGAS 评估问答对

运行方式:
    cd backend
    python scripts/generate_testset.py                     # 默认生成 10 组
    python scripts/generate_testset.py --count 20          # 生成 20 组
    python scripts/generate_testset.py --output my_qa.json # 指定输出文件

生成的测试集包含 RAGAS 标准 4 维核心参数结构:
    - question:       用户问题
    - contexts:       检索到的原文切片列表（通过实际检索获得）
    - answer:         模型基于检索上下文生成的回答
    - ground_truth:   文档中的标准答案（由 LLM 从文档中提取）

输出文件:
    - eval_qa_pairs.json:    问答对 (question + ground_truth)
    - eval_testset_full.json: 完整测试集 (question + contexts + answer + ground_truth)
"""
import sys
import os

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

from app.services.retrieval_service import retrieval_service
from app.services.llm_service import llm_service
from app.services.vector_store import vector_store

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# QA 生成 Prompt
# ═══════════════════════════════════════════════════════════════

QA_GENERATION_PROMPT = """你是一个专业的测试数据生成器。请根据以下文档内容，生成 {count} 个高质量的问答对。

要求：
1. 问题应覆盖文档的不同方面（概念、细节、关系、结论等），不要重复
2. 问题应使用自然语言，像真实用户会问的问题
3. 参考答案应准确、完整，基于文档内容（不要编造）
4. 每个问题应有明确的答案，可以从文档中直接或间接推导
5. 参考答案应足够详细（至少 2-3 句话），包含具体信息

输出格式（严格 JSON 数组）：
```json
[
  {{"question": "问题1", "ground_truth": "答案1"}},
  {{"question": "问题2", "ground_truth": "答案2"}}
]
```

文档内容：
{document_text}

请严格按照上述 JSON 格式生成 {count} 个问答对："""


async def generate_qa_pairs(count: int = 10, max_chunks: int = 30) -> list[dict]:
    """从向量库文档中生成 QA 对"""
    seed_queries = [
        "概述", "简介", "什么是", "如何", "原因", "方法",
        "步骤", "特点", "区别", "优势", "应用", "总结",
        "关键", "重要", "原理", "流程", "核心", "结论",
    ]

    sampled_chunks: list[str] = []
    seen_ids: set[str] = set()

    for query in seed_queries:
        if len(sampled_chunks) >= max_chunks:
            break
        results = vector_store.search(query, top_k=3)
        for r in results:
            if r["chunk_id"] not in seen_ids and len(sampled_chunks) < max_chunks:
                seen_ids.add(r["chunk_id"])
                sampled_chunks.append(r["content"])

    if not sampled_chunks:
        logger.error("无法从向量库中采样文档块，请先上传文档")
        return []

    random.shuffle(sampled_chunks)
    document_text = "\n\n---\n\n".join(
        f"[片段 {i+1}] {chunk[:800]}" for i, chunk in enumerate(sampled_chunks)
    )
    prompt = QA_GENERATION_PROMPT.format(count=count, document_text=document_text)

    logger.info(f"使用 {len(sampled_chunks)} 个文档片段生成 {count} 个问答对...")

    try:
        response = await llm_service.chat(
            messages=[{"role": "user", "content": prompt}],
        )
        json_start = response.find("[")
        json_end = response.rfind("]") + 1
        if json_start == -1 or json_end == 0:
            logger.error("LLM 返回的内容中未找到 JSON 数组")
            return []
        qa_pairs = json.loads(response[json_start:json_end])
        return [
            {"question": p["question"], "ground_truth": p["ground_truth"]}
            for p in qa_pairs
            if isinstance(p, dict) and "question" in p and "ground_truth" in p
        ]
    except Exception as e:
        logger.error(f"生成失败: {e}")
        return []


async def build_full_testset(qa_pairs: list[dict]) -> list[dict]:
    """
    构建完整的 RAGAS 4 维测试集。

    对每个问答对:
    1. 通过混合检索获取 contexts
    2. 基于 contexts 生成 answer
    3. 组合 question + contexts + answer + ground_truth

    Returns:
        [{question, contexts, answer, ground_truth}, ...]
    """
    full_testset = []

    for idx, item in enumerate(qa_pairs):
        question = item["question"]
        ground_truth = item["ground_truth"]

        logger.info(f"构建测试集 [{idx+1}/{len(qa_pairs)}]: {question[:50]}...")

        # 检索上下文
        retrieval_results = retrieval_service.search(question, top_k=5)
        contexts = [r["content"] for r in retrieval_results]

        if not contexts:
            logger.warning("  未检索到相关内容，跳过")
            continue

        # 基于上下文生成回答
        context_text = "\n\n".join(
            f"[来源 {i+1}] {ctx}" for i, ctx in enumerate(contexts)
        )
        answer = await llm_service.chat(
            messages=[{
                "role": "user",
                "content": f"基于以下参考文档回答问题。\n参考文档:\n{context_text}\n\n问题: {question}\n\n回答:",
            }],
        )

        full_testset.append({
            "question": question,
            "contexts": contexts,
            "answer": answer,
            "ground_truth": ground_truth,
        })

        logger.info(f"  完成: contexts={len(contexts)}, answer_len={len(answer)}")

    return full_testset


async def main():
    parser = argparse.ArgumentParser(description="RAGAS 测试集生成工具")
    parser.add_argument("--count", type=int, default=10, help="生成问答对数量（默认 10）")
    parser.add_argument("--output", type=str, default=None, help="输出文件名（默认 eval_qa_pairs.json）")
    parser.add_argument("--full", action="store_true", help="构建完整 4 维测试集（包含 contexts + answer）")
    args = parser.parse_args()

    # 检查向量库
    if vector_store.get_chunk_count() == 0:
        logger.error("向量库为空！请先上传 PDF 文档。")
        return

    # 重建 BM25
    if retrieval_service.bm25 is None:
        logger.info("正在从向量库重建 BM25 索引...")
        all_chunks = vector_store.get_all_chunks()
        if all_chunks:
            retrieval_service.build_bm25_index(all_chunks)

    # 生成 QA 对
    qa_pairs = await generate_qa_pairs(count=args.count)
    if not qa_pairs:
        logger.error("未生成有效问答对")
        return

    output_dir = os.path.join(os.path.dirname(__file__), "..")

    # 保存问答对
    qa_filename = args.output or "eval_qa_pairs.json"
    qa_path = os.path.join(output_dir, qa_filename)
    with open(qa_path, "w", encoding="utf-8") as f:
        json.dump(qa_pairs, f, ensure_ascii=False, indent=2)
    logger.info(f"问答对已保存到: {os.path.abspath(qa_path)}")

    # 构建完整测试集（可选）
    if args.full:
        logger.info("构建完整 4 维测试集...")
        full_testset = await build_full_testset(qa_pairs)
        full_path = os.path.join(output_dir, "eval_testset_full.json")
        with open(full_path, "w", encoding="utf-8") as f:
            json.dump(full_testset, f, ensure_ascii=False, indent=2)
        logger.info(f"完整测试集已保存到: {os.path.abspath(full_path)}")

    # 打印摘要
    print("\n" + "=" * 60)
    print("测试集生成摘要")
    print("=" * 60)
    print(f"  问答对数量: {len(qa_pairs)}")
    print(f"  RAGAS 4 维结构:")
    print(f"    1. question      - 用户问题")
    print(f"    2. ground_truth  - 标准答案")
    if args.full:
        print(f"    3. contexts      - 检索上下文列表")
        print(f"    4. answer        - 模型生成回答")
    print(f"\n  使用方式:")
    print(f"    python scripts/evaluate_rag.py --qa-file {qa_filename}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
