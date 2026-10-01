import json
from schemas.common import Reference


def test_reference_json_round_trip_keeps_chinese_readable():
    ref = Reference(document_id=3, parent_id="a.txt_parent_0", filename="a.txt", snippet="中文片段")
    dumped = json.dumps([ref.model_dump()], ensure_ascii=False)
    assert "中文片段" in dumped
    assert [Reference(**item) for item in json.loads(dumped)] == [ref]


def test_empty_chunk_content_still_produces_a_reference():
    ref = Reference(document_id=1, parent_id="p", filename="f.txt", snippet="")
    assert ref.model_dump()["snippet"] == ""
