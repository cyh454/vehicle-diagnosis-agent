"""集成测试：需先启动服务与数据库。
运行: API_BASE=http://localhost:8000 pytest tests/ -v"""
import os

import httpx
import pytest

BASE = os.getenv("API_BASE", "http://localhost:8000")


def test_health():
    r = httpx.get(f"{BASE}/health", timeout=10)
    assert r.status_code == 200
    assert r.json()["status"] in ("healthy", "degraded")


def test_metrics():
    r = httpx.get(f"{BASE}/metrics", timeout=10)
    assert r.status_code == 200
    assert "latency_ms" in r.json()


def test_chat_and_session_memory():
    r = httpx.post(
        f"{BASE}/api/v1/diagnosis/chat",
        json={"message": "比亚迪汉EV报P0562怎么排查？", "user_id": "tester"},
        timeout=300,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["session_id"]
    assert data["reply"]
    assert data["vehicle"] is not None      # 车型自动识别

    # 第二轮：同一会话，验证记忆（车辆已绑定，可直接问配件）
    r2 = httpx.post(
        f"{BASE}/api/v1/diagnosis/chat",
        json={"session_id": data["session_id"], "message": "要换DC-DC的话有货吗？多少钱？"},
        timeout=300,
    )
    assert r2.status_code == 200
    body = r2.json()
    assert body["vehicle"] is not None
    assert body["tool_calls"]               # 应触发配件查询工具

    # 会话历史可查
    r3 = httpx.get(f"{BASE}/api/v1/diagnosis/sessions/{data['session_id']}", timeout=10)
    assert r3.status_code == 200
    assert r3.json()["message_count"] >= 4
