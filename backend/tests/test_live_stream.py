"""真 uvicorn(:8000) 上的断流/收流回归（阶段三入口项 2：把断流不落半截从 prose 变门禁）。

`-m "not live"` 整组跳过；:8000 不可达也 skip（对齐 test_live_database 的"没库就跳过"惯例）。
探针会话一律 finally DELETE 删干净，同机连跑两遍都绿，不污染 chat_history 基线。
"""
import contextlib
import time
from contextlib import contextmanager

import httpx
import pytest

pytestmark = pytest.mark.live

BASE = "http://127.0.0.1:8000"
LONG_QUESTION = "请非常详细地介绍RAG检索增强生成的完整原理、优缺点和发展历史，内容越长越好"


@pytest.fixture(scope="module")
def server():
    try:
        httpx.get(f"{BASE}/api/health", timeout=2).raise_for_status()
    except Exception as exc:
        pytest.skip(f"uvicorn :8000 不可用（live 组需要真服务）：{exc}")


def probe_session(tag):
    # 唯一 id + 时间戳：并行/重跑都不撞车，且 finally 只删自己写的那份
    return f"live-stream-{tag}-{int(time.time() * 1000)}"


def stream_payload(session_id, question=LONG_QUESTION):
    return {"session_id": session_id, "question": question, "parent_ids": []}


def login_token():
    """真服务上登录一个真账号，拿一枚真令牌。

    口令只从 Config.DEFAULT_USER_PASSWORD 读，**绝不打印**（项目记忆：`.env` 的键值
    不入日志、不进断言消息）。默认用户不可登录时这条 helper 直接 pytest.skip——
    那属于"运营者没设口令"的环境差异，不是代码坏了。
    """
    from config.config import Config
    from core.migrations import DEFAULT_IDENTIFIER

    if not Config.DEFAULT_USER_PASSWORD:
        pytest.skip("DEFAULT_USER_PASSWORD 未设置：默认用户只作归属锚点，无法登录")
    res = httpx.post(f"{BASE}/api/auth/login",
                     json={"identifier": DEFAULT_IDENTIFIER,
                           "password": Config.DEFAULT_USER_PASSWORD}, timeout=30)
    res.raise_for_status()
    return res.json()["token"]


@contextmanager
def logged_in():
    """登录 → yield 令牌 → 无论如何登出：advisory ④（阶段一终审的数据卫生账）。

    `login_token()` 只登不出，每轮在 `auth_tokens` 留一枚 30 天有效的行。库内只存 SHA-256，
    残留行不可被利用，但每轮重跑攒的是永久垃圾。
    finally 里再抛错会盖掉判据本身的红，所以登出的失败只当噪声吞掉。
    """
    token = login_token()
    try:
        yield token
    finally:
        with contextlib.suppress(Exception):
            httpx.post(f"{BASE}/api/auth/logout", timeout=10,
                       headers={"Authorization": f"Bearer {token}"})


def test_client_disconnect_mid_stream_leaves_no_rows(server):
    """主判据：收了若干 token 就掐断连接 → 后端生成器被取消，一条都不该落库。

    阶段二靠 gen.close() 单测 + 浏览器手测背书；这里钉住真 HTTP 断连路径。
    token<2 就见到 error 帧 = 大模型不可用（如免费额度耗尽），skip 而不是假绿：
    没在飞行中的生成就没有"断流"可言。
    """
    with logged_in() as token:     # 业务端点全部要求 Bearer（spec 3.2）；退出即登出（advisory ④）
        sid = probe_session("abort")
        try:
            with httpx.Client(timeout=60) as client:
                with client.stream("POST", f"{BASE}/api/chat/stream",
                                   json=stream_payload(sid),
                                   headers={"Authorization": f"Bearer {token}"}) as res:
                    if res.status_code == 409:
                        # 默认用户没配 key/模型时，阶段二的问答门禁回 409（Task 3 的种子只在
                        # `.env` 三键齐全时才写入）。那是环境差异，不是代码坏了。
                        # `read()` 只能在这里调一次——进入迭代之后就再也拿不到体。
                        body = res.read().decode("utf-8", "replace")
                        pytest.skip(f"默认用户还没配 key/模型（阶段二门禁）：{body}")
                    assert res.status_code == 200
                    tokens = 0
                    for line in res.iter_lines():
                        if line.startswith("event: token"):
                            tokens += 1
                        elif line.startswith("event: error"):
                            pytest.skip(f"大模型不可用，断流判据无从验起：{line}")
                        if tokens >= 2:  # 生成确实在飞行中
                            break
                assert tokens >= 2, "流在攒够 token 前就结束了，无法验证断流路径"
                # with 退出即关 socket；给服务端一点时间把断连处理完
                time.sleep(1.0)
                rows = client.get(f"{BASE}/api/history/{sid}",
                                  headers={"Authorization": f"Bearer {token}"}).json()
                assert rows == [], f"断流后竟落了 {len(rows)} 行半截历史"
        finally:
            httpx.delete(f"{BASE}/api/history/{sid}", timeout=10,
                         headers={"Authorization": f"Bearer {token}"})


def test_full_stream_persists_one_turn_and_frames_are_ordered(server):
    """对照组（证明上一条断言不是恒真）：完整读到 done → 恰好 2 行、帧序合规。

    帧序 live 门禁：首个事件 meta，末个事件 done，中间全是 token（normal 模式无 references）。
    """
    with logged_in() as token:     # 同上一条：退出即登出（advisory ④）
        sid = probe_session("full")
        events = []
        try:
            with httpx.Client(timeout=120) as client:
                with client.stream("POST", f"{BASE}/api/chat/stream",
                                   json=stream_payload(sid),
                                   headers={"Authorization": f"Bearer {token}"}) as res:
                    if res.status_code == 409:
                        body = res.read().decode("utf-8", "replace")
                        pytest.skip(f"默认用户还没配 key/模型（阶段二门禁）：{body}")
                    assert res.status_code == 200
                    assert "text/event-stream" in res.headers["content-type"]
                    for line in res.iter_lines():
                        if line.startswith("event:"):
                            events.append(line.split(":", 1)[1].strip())
                if "error" in events:
                    pytest.skip(f"大模型不可用（error 帧），对照组无从验完整收流：{events}")
                assert events[0] == "meta"
                assert events[-1] == "done"
                assert set(events[1:-1]) == {"token"}, "normal 模式中间帧应全是 token"
                rows = client.get(f"{BASE}/api/history/{sid}",
                                  headers={"Authorization": f"Bearer {token}"}).json()
                assert [r["role"] for r in rows] == ["user", "assistant"]
                assert rows[1]["mode"] == "normal"
                assert rows[1]["content"], "done 帧发出前答案必须已完整落库"
        finally:
            httpx.delete(f"{BASE}/api/history/{sid}", timeout=10,
                         headers={"Authorization": f"Bearer {token}"})
