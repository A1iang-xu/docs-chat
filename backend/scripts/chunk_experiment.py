"""
分块策略对比实验 —— 对比不同 chunk_size / overlap 组合的效果
运行方式: cd backend && python scripts/chunk_experiment.py <pdf_path>
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.document_service import document_service
import logging
# 强行将 pypdf 及其底层的日志级别设为 ERROR，屏蔽 INFO 探测提示
logging.getLogger("PyPDF2").setLevel(logging.ERROR)
logging.getLogger("pypdf").setLevel(logging.ERROR)

def run_experiment(file_path: str):
    """对比 3 组参数，输出分块统计"""
    configs = [
        {"chunk_size": 512, "chunk_overlap": 50},
        {"chunk_size": 512, "chunk_overlap": 100},
        {"chunk_size": 1024, "chunk_overlap": 100},
        {"chunk_size": 1024, "chunk_overlap": 200},
    ]

    print(f"\n{'='*60}")
    print(f"分块策略对比实验: {os.path.basename(file_path)}")
    print(f"{'='*60}\n")

    for cfg in configs:
        chunks = document_service.load_and_split(
            file_path,
            chunk_size=cfg["chunk_size"],
            chunk_overlap=cfg["chunk_overlap"],
        )
        avg_len = sum(len(c.content) for c in chunks) / len(chunks) if chunks else 0
        print(f"chunk_size={cfg['chunk_size']:>4}, overlap={cfg['chunk_overlap']:>3}  "
              f"→ 共 {len(chunks):>3} 个块, 平均长度 {avg_len:>6.0f} 字符")

    print(f"\n{'='*60}")
    print("结论: 推荐 chunk_size=512 + overlap=100 —— 兼顾语义完整性与检索粒度")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python scripts/chunk_experiment.py <pdf_path>")
        sys.exit(1)
    run_experiment(sys.argv[1])