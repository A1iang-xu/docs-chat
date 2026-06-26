"""DocsChat v3.1 端到端验证脚本"""
import http.client
import json
import time
import urllib.request

BASE = "http://127.0.0.1:8000"


def upload_pdf(filepath: str) -> str:
    """上传 PDF 并返回 job_id"""
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"

    with open(filepath, "rb") as f:
        file_content = f.read()

    filename = filepath.replace("\\", "/").split("/")[-1]

    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: application/pdf\r\n\r\n"
    ).encode() + file_content + f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(f"{BASE}/documents/upload", data=body)
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    resp = urllib.request.urlopen(req)
    data = json.loads(resp.read())
    return data["job_id"], data


def poll_job(job_id: str, max_wait: int = 30):
    """轮询任务状态直到完成"""
    start = time.time()
    while time.time() - start < max_wait:
        resp = urllib.request.urlopen(f"{BASE}/documents/jobs/{job_id}")
        data = json.loads(resp.read())
        status = data["status"]
        print(f"  [{status}] pages={data['page_count']} chunks={data['chunk_count']}")
        if status in ("ready", "failed"):
            return data
        time.sleep(1.5)
    return None


def test_health():
    """测试健康检查"""
    print("\n" + "=" * 60)
    print("Test 1: Health Check")
    resp = urllib.request.urlopen(f"{BASE}/health")
    data = json.loads(resp.read())
    print(f"  Status: {resp.status} {data}")


def test_services():
    """测试服务诊断"""
    print("\n" + "=" * 60)
    print("Test 2: Service Health")
    resp = urllib.request.urlopen(f"{BASE}/health/services")
    data = json.loads(resp.read())
    print(f"  all_healthy: {data['all_healthy']}")
    print(f"  chunk_count: {data['chunk_count']}")
    print(f"  mineru: {data['mineru']['mode']}")
    print(f"  embedding: {data['embedding']['provider']} ({data['embedding']['dim']}d)")
    print(f"  deepseek: configured={data['deepseek']['configured']}")
    print(f"  quality_gate: {data['quality_gate']}")


def test_upload():
    """测试文档上传"""
    print("\n" + "=" * 60)
    print("Test 3: Document Upload (Async)")
    filepath = "e:/docs-chat/backend/uploads/test_doc.pdf"
    job_id, job = upload_pdf(filepath)
    print(f"  Upload OK: job_id={job_id}")
    print(f"  Initial status: {job['status']}")

    print("  Polling for completion...")
    result = poll_job(job_id)
    if result and result["status"] == "ready":
        print(f"  Upload SUCCESS: {result['page_count']} pages, {result['chunk_count']} chunks")
    else:
        print(f"  Upload result: {result}")
    return job_id


def test_document_list():
    """测试文档列表"""
    print("\n" + "=" * 60)
    print("Test 4: Document List")
    resp = urllib.request.urlopen(f"{BASE}/documents/")
    data = json.loads(resp.read())
    print(f"  Documents: {len(data)}")
    for doc in data:
        print(f"    - {doc['filename']} ({doc['chunk_count']} chunks)")


def test_sse_chat():
    """测试 SSE 流式对话"""
    print("\n" + "=" * 60)
    print("Test 5: SSE Streaming Chat")

    body = json.dumps({"conversation_id": "e2e_test_001", "content": "What is DocsChat?"}).encode()
    req = urllib.request.Request(f"{BASE}/chat/stream?rag=true", data=body, method="POST")
    req.add_header("Content-Type", "application/json")

    try:
        resp = urllib.request.urlopen(req, timeout=30)
        events = {"source": 0, "token": 0, "cache": 0, "done": 0, "error": 0}
        tokens = []

        for line_b in resp:
            line = line_b.decode("utf-8", errors="replace").strip()
            if line.startswith("data: "):
                payload = line[6:]
                try:
                    event = json.loads(payload)
                    etype = event.get("event", "")
                    events[etype] = events.get(etype, 0) + 1
                    if etype == "token":
                        tokens.append(event.get("data", ""))
                    elif etype == "done":
                        print(f"  SSE events: {events}")
                        answer = "".join(tokens)
                        print(f"  Answer ({len(answer)} chars): {answer[:200]}...")
                        return
                    elif etype == "error":
                        print(f"  ERROR: {event.get('data', '')}")
                        return
                except json.JSONDecodeError:
                    pass
    except Exception as e:
        print(f"  SSE request failed: {e}")


def test_non_rag_chat():
    """测试非 RAG 模式对话（无知识库时）"""
    print("\n" + "=" * 60)
    print("Test 6: Non-RAG Chat (no knowledge base)")
    # 临时使用 rag=false 测试直连 LLM
    body = json.dumps({"conversation_id": "e2e_test_002", "content": "Say hello in one word."}).encode()
    req = urllib.request.Request(f"{BASE}/chat/stream?rag=false", data=body, method="POST")
    req.add_header("Content-Type", "application/json")

    try:
        resp = urllib.request.urlopen(req, timeout=30)
        tokens = []
        for line_b in resp:
            line = line_b.decode("utf-8", errors="replace").strip()
            if line.startswith("data: "):
                payload = line[6:]
                try:
                    event = json.loads(payload)
                    if event.get("event") == "token":
                        tokens.append(event.get("data", ""))
                    elif event.get("event") == "done":
                        answer = "".join(tokens)
                        print(f"  Answer: {answer}")
                        return
                    elif event.get("event") == "error":
                        print(f"  LLM Error: {event.get('data', '')}")
                        print("  (Expected if DEEPSEEK_API_KEY is not configured)")
                        return
                except json.JSONDecodeError:
                    pass
    except Exception as e:
        print(f"  Request failed: {e}")


def test_status():
    """测试状态端点"""
    print("\n" + "=" * 60)
    print("Test 7: System Status")
    resp = urllib.request.urlopen(f"{BASE}/documents/status")
    data = json.loads(resp.read())
    print(f"  chunk_count: {data['chunk_count']}")
    print(f"  has_bm25_index: {data['has_bm25_index']}")
    print(f"  jobs: {len(data['jobs'])}")


if __name__ == "__main__":
    print("=" * 60)
    print("DocsChat v3.1 End-to-End Verification")
    print("=" * 60)

    test_health()
    test_services()
    test_status()
    test_upload()
    test_document_list()
    test_sse_chat()
    test_non_rag_chat()

    print("\n" + "=" * 60)
    print("E2E Verification Complete!")
    print("=" * 60)