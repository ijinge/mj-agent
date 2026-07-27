"""SSE 帧编码测试。"""
from app.gateway.sse import sse_done, sse_format, sse_keepalive


def test_sse_format_basic():
    frame = sse_format(event_id="1-0", event="token", data={"text": "hi"})
    assert "id: 1-0" in frame
    assert "event: token" in frame
    assert 'data: {"text": "hi"}' in frame
    assert frame.endswith("\n\n")


def test_sse_format_with_retry():
    frame = sse_format(event_id="2-0", event="message", data="ok", retry=3000)
    assert "retry: 3000" in frame
    assert "event: message" in frame


def test_sse_format_multiline_data():
    frame = sse_format(event_id="3", event="x", data="line1\nline2")
    assert "data: line1" in frame
    assert "data: line2" in frame


def test_sse_keepalive_starts_with_colon():
    ka = sse_keepalive()
    assert ka.startswith(":")
    assert ka.endswith("\n\n")


def test_sse_done_emits_done_event():
    d = sse_done()
    assert "event: done" in d
