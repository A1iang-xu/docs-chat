"""应用配置管理 —— 基于 pydantic-settings 从环境变量 / .env 加载"""
from pydantic_settings import BaseSettings
from pydantic import Field
from pathlib import Path


class Settings(BaseSettings):
    # ── 项目路径 ──
    PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
    CHROMA_PERSIST_DIR: str = str(PROJECT_ROOT / "chroma_data")
    UPLOAD_DIR: str = str(PROJECT_ROOT / "uploads")

    # ── DeepSeek API ──
    DEEPSEEK_API_KEY: str = Field(default="", description="DeepSeek Open Platform API Key")
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"
    DEEPSEEK_MODEL: str = "deepseek-chat"
    DEEPSEEK_MAX_TOKENS: int = 4096
    DEEPSEEK_TEMPERATURE: float = 0.7

    # ── Embedding ──
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    EMBEDDING_DIM: int = 384

    # ── 分块策略 ──
    CHUNK_SIZE: int = 512
    CHUNK_OVERLAP: int = 100

    # ── 检索 ──
    RETRIEVAL_TOP_K: int = 10
    RERANKER_TOP_K: int = 5
    RERANKER_MODEL: str = "BAAI/bge-reranker-v2-m3"

    # ── 服务 ──
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # ── 日志 ──
    LOG_LEVEL: str = "INFO"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "allow"}


settings = Settings()