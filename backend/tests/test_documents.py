"""文档上传 API 测试"""
import pytest
import os
import tempfile
from pathlib import Path
from httpx import AsyncClient
from unittest.mock import patch, MagicMock


@pytest.mark.asyncio
async def test_upload_non_pdf_rejected(client: AsyncClient):
    """验证非 PDF 文件被拒绝"""
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        f.write(b"not a pdf")
        temp_path = f.name

    try:
        with open(temp_path, "rb") as f:
            response = await client.post(
                "/documents/upload",
                files={"file": ("test.txt", f, "text/plain")},
            )

        assert response.status_code in [400, 422]
    finally:
        os.unlink(temp_path)


@pytest.mark.asyncio
async def test_upload_without_file_rejected(client: AsyncClient):
    """验证未上传文件时返回错误"""
    response = await client.post("/documents/upload")

    assert response.status_code == 422