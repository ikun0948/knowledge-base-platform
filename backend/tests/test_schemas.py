import json

import pytest
from pydantic import ValidationError

from schemas.chat import ChatResponse, mode_of
from schemas.common import Reference


def _ref():
    return Reference(document_id=3, parent_id="a.txt_parent_0", filename="a.txt", snippet="中文片段")


def test_reference_json_round_trip_keeps_chinese_readable():
    ref = Reference(document_id=3, parent_id="a.txt_parent_0", filename="a.txt", snippet="中文片段")
    dumped = json.dumps([ref.model_dump()], ensure_ascii=False)
    assert "中文片段" in dumped
    assert [Reference(**item) for item in json.loads(dumped)] == [ref]


def test_empty_chunk_content_still_produces_a_reference():
    ref = Reference(document_id=1, parent_id="p", filename="f.txt", snippet="")
    assert ref.model_dump()["snippet"] == ""


@pytest.mark.parametrize("mode", ["rag", "normal"])
def test_chat_response_accepts_the_two_documented_modes(mode):
    assert ChatResponse(answer="a", references=[_ref()], mode=mode).mode == mode


@pytest.mark.parametrize("mode", ["RAG", "", "chat", None, 0])
def test_chat_response_rejects_any_other_mode(mode):
    """mode 是 spec 6.1 的两值枚举：脏值在 schema 边界就被拒，不靠端点断言兜。"""
    with pytest.raises(ValidationError):
        ChatResponse(answer="a", references=[], mode=mode)


def test_chat_response_mode_is_still_a_plain_json_string():
    assert json.loads(ChatResponse(answer="a", references=[], mode="rag").model_dump_json())["mode"] == "rag"


@pytest.mark.parametrize("document_ids,expected", [
    ([1], "rag"),
    ([1, 2, 3], "rag"),
    ("1,2", "rag"),      # 历史行的逗号字符串形状
    ([], "normal"),
    (None, "normal"),    # 历史行 document_ids 可为 NULL
    ("", "normal"),
])
def test_mode_of_derives_rag_only_from_non_empty_document_ids(document_ids, expected):
    """建议 4：mode 的唯一真相。三种入参形状（list/str/None）都按"有没有文档"判定。"""
    assert mode_of(document_ids) == expected


def test_mode_of_output_is_always_a_accepted_chat_response_mode():
    """派生值必须落在 ChatResponse 的 Literal 值域内，否则 helper 与枚举会各自漂移。"""
    for ids in ([1], [], None, "1,2"):
        assert ChatResponse(answer="a", references=[], mode=mode_of(ids)).mode in ("rag", "normal")
