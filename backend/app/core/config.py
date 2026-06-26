"""应用配置管理 —— 基于 pydantic-settings 从环境变量 / .env 加载

v3.3 新增配置:
- 查询分类路由
- 多轮对话摘要压缩
- 上下文 Token 预算管理
- 语义缓存 FAISS 向量预热
- 忠实度反馈闭环（重试）
- 检索去重增强
- LLM 降级保障
- 管线延迟监控
"""
from typing import Literal
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
    CHROMA_PERSIST_DIR: str = str(PROJECT_ROOT / "chroma_data")
    UPLOAD_DIR: str = str(PROJECT_ROOT / "uploads")

    # ── LLM ──
    DEEPSEEK_API_KEY: str = Field(default="")
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"
    DEEPSEEK_MODEL: str = "deepseek-chat"
    DEEPSEEK_MAX_TOKENS: int = 4096
    DEEPSEEK_TEMPERATURE: float = 0.7

    # ── v3.3: LLM 降级 ──
    LLM_FALLBACK_ENABLED: bool = True
    LLM_FALLBACK_MODEL: str = ""  # 备选模型，空则与主模型相同（不降级）

    # ── Embedding ──
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    EMBEDDING_DIM: int = 384
    EMBEDDING_PROVIDER: str = "chromadb_default"
    EMBEDDING_API_BASE: str = ""
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_MAX_RETRIES: int = 3
    EMBEDDING_BATCH_SIZE: int = 32

    # ── 文档解析 ──
    PARSER_TYPE: Literal["fallback", "mineru"] = "fallback"
    MINERU_URL: str = ""
    MINERU_EFFORT: Literal["low", "medium", "high"] = "medium"
    MINERU_OUTPUT_DIR: str = str(PROJECT_ROOT / "mineru_output")
    MINERU_COMMAND: str = ""
    MINERU_API_TIMEOUT: int = 1800
    MINERU_BACKEND: str = "hybrid-auto-engine"

    # ── 遗留兼容 ──
    ENABLE_BGE_M3: bool = False
    DOCUMENT_PARSER: str | None = None
    MINERU_API_URL: str | None = None
    MINERU_ENABLED: bool | None = None
    BGE_M3_ENABLED: bool | None = None
    QWEN_RERANKER_ENABLED: bool | None = None

    # ── Reranker ──
    RERANKER_TYPE: Literal["fallback", "qwen"] = "fallback"
    RERANKER_MODEL: str = "Qwen/Qwen3-Reranker-0.6B"
    RERANKER_API_URL: str = ""
    RERANKER_API_TIMEOUT: int = 30
    RERANKER_MAX_LENGTH: int = 2048
    PRELOAD_RERANKER: bool = False

    # ── 分块策略 ──
    CHUNK_SIZE: int = 512
    CHUNK_OVERLAP: int = 100
    MIN_CHUNK_CHARS: int = 80
    MAX_CHUNK_CHARS: int = 1024
    SEMANTIC_CHUNK_ENABLED: bool = True
    SEMANTIC_CHUNK_THRESHOLD: float = 0.5

    # ── 质量门禁 ──
    QG_ENABLED: bool = True
    QG_MIN_CHARS: int = 100
    QG_MIN_HEADINGS: int = 0
    QG_MIN_TABLES: int = 0
    QG_MIN_PAGES: int = 1

    # ── 检索 ──
    RETRIEVAL_TOP_K: int = 10
    RERANKER_TOP_K: int = 5
    RAG_FUSION_VARIANTS: int = 3
    RAG_MAX_HISTORY_MESSAGES: int = 6
    CHUNK_NEIGHBOR_EXPAND: int = 1
    RETRIEVAL_TIMEOUT_SECONDS: float = 5.0

    # ── v3.3: 检索去重 ──
    RETRIEVAL_DEDUP_ENABLED: bool = True
    RETRIEVAL_DEDUP_SIMILARITY: float = 0.85

    # ── CRAG ──
    CRAG_ENABLED: bool = True
    CRAG_CORRECT_THRESHOLD: float = 0.8
    CRAG_INCORRECT_THRESHOLD: float = 0.3
    CRAG_RETRY_INCORRECT_RATIO: float = 0.6

    # ── 语义缓存 ──
    SEMANTIC_CACHE_ENABLED: bool = True
    SEMANTIC_CACHE_TTL_SECONDS: int = 86400
    SEMANTIC_CACHE_THRESHOLD: float = 0.92

    # ── v3.3: 语义缓存 FAISS 向量预热 ──
    SEMANTIC_CACHE_WARM_VECTOR_THRESHOLD: float = 0.95

    # ── 上下文组装 ──
    CONTEXT_SANDWICH_ENABLED: bool = True
    CONTEXT_SANDWICH_TOP_K: int = 2

    # ── v3.3: Token 预算管理 ──
    CONTEXT_TOKEN_BUDGET_ENABLED: bool = True
    CONTEXT_MAX_TOKENS: int = 3000  # 总 token 预算

    # ── HyDE ──
    HYDE_ENABLED: bool = True
    HYDE_MAX_TOKENS: int = 200
    HYDE_PARALLEL: bool = True

    # ── 答案忠实度验证 ──
    FAITHFULNESS_CHECK_ENABLED: bool = True
    FAITHFULNESS_LLM_THRESHOLD: float = 0.7

    # ── v3.3: 忠实度反馈闭环 ──
    FAITHFULNESS_MAX_RETRIES: int = 1  # 最多重试 1 次二次生成

    # ── v3.3: 查询分类路由 ──
    QUERY_CLASSIFIER_ENABLED: bool = True

    # ── v3.3: 多轮对话摘要 ──
    CONVERSATION_SUMMARY_ENABLED: bool = True
    CONVERSATION_SUMMARY_MAX_TOKENS: int = 200

    # ── v3.3: 管线延迟监控 ──
    PIPELINE_PERF_LOG_ENABLED: bool = True

    # ── 并发控制 ──
    CHAT_MAX_CONCURRENT_LLM: int = 8
    INGESTION_MAX_CONCURRENT_JOBS: int = 2
    RATE_LIMIT_REQUESTS: int = 20
    RATE_LIMIT_WINDOW_SECONDS: int = 60
    AUTH_REQUIRED: bool = False
    JWT_SECRET: str = ""

    # ── v4.0: URL 摄取 ──
    WEB_INGEST_ENABLED: bool = True
    WEB_INGEST_MAX_PAGES: int = 200
    WEB_INGEST_MAX_DEPTH: int = 3
    WEB_INGEST_RESPECT_ROBOTS: bool = True

    # ── v4.0: 代码感知分块 ──
    CODE_AWARE_CHUNK_ENABLED: bool = True

    # ── v4.0: 多库命名空间 ──
    LIBRARY_FILTER_ENABLED: bool = True

    # ── v4.0: 可观测 ──
    METRICS_ENABLED: bool = True

    # ── v4.0: 用户反馈 ──
    FEEDBACK_ENABLED: bool = True

    # ── v4.0: 在线 Demo 防护 ──
    DEMO_API_KEY_REQUIRED: bool = False
    DEMO_API_KEY: str = ""
    REDIS_URL: str = ""

    # ── v4.1: 语义化查询分类 ──
    QUERY_CLASSIFIER_FEW_SHOT_ENABLED: bool = True
    QUERY_CLASSIFIER_CACHE_ENABLED: bool = True
    QUERY_CLASSIFIER_CACHE_SIZE: int = 200

    # ── v4.1: 代码子索引 ──
    CODE_EMBEDDING_MODEL: str = ""  # 空=用默认 embedding，非空=代码专用模型

    # ── v4.1: Agentic 多跳检索 ──
    MULTI_HOP_ENABLED: bool = True
    MULTI_HOP_MAX_SUB_QUERIES: int = 3

    # ── v4.3: 离线评估（RAGAS 风格 LLM-as-Judge）──
    EVALUATION_ENABLED: bool = True
    EVALUATION_DATASET_PATH: str = "tests/eval_dataset.json"
    EVALUATION_RESULTS_DIR: str = str(PROJECT_ROOT / "eval_results")

    # ── v4.4: L1 精确缓存 ──
    CACHE_L1_ENABLED: bool = True
    CACHE_L1_TTL_SECONDS: int = 3600

    # ── v4.4: 速率限制 ──
    RATE_LIMIT_ENABLED: bool = True

    # ── 服务 ──
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]
    LOG_LEVEL: str = "INFO"

    @model_validator(mode="after")
    def _migrate(self):
        if self.MINERU_API_URL and not self.MINERU_URL:
            object.__setattr__(self, "MINERU_URL", self.MINERU_API_URL)
        if self.PARSER_TYPE == "fallback":
            if self.MINERU_ENABLED is True:
                object.__setattr__(self, "PARSER_TYPE", "mineru")
            elif self.DOCUMENT_PARSER and str(self.DOCUMENT_PARSER) in ("mineru", "mineru_api"):
                object.__setattr__(self, "PARSER_TYPE", "mineru")
        if not self.ENABLE_BGE_M3 and self.BGE_M3_ENABLED is True:
            object.__setattr__(self, "ENABLE_BGE_M3", True)
        if self.ENABLE_BGE_M3:
            if self.EMBEDDING_DIM != 1024:
                object.__setattr__(self, "EMBEDDING_DIM", 1024)
            if not self.EMBEDDING_MODEL or self.EMBEDDING_MODEL == "all-MiniLM-L6-v2":
                object.__setattr__(self, "EMBEDDING_MODEL", "BAAI/bge-m3")
        if self.RERANKER_TYPE == "fallback" and self.QWEN_RERANKER_ENABLED is True:
            object.__setattr__(self, "RERANKER_TYPE", "qwen")
        return self

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "allow"}


settings = Settings()
