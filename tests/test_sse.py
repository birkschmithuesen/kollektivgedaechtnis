import json

from kg.sse import SSEDecoder


def test_decodes_one_data_block_per_blank_line():
    decoder = SSEDecoder()
    assert decoder.feed('data: {"type": "final", "text": "hallo"}') is None
    event = decoder.feed("")
    assert event == {"type": "final", "text": "hallo"}


def test_keep_alive_comments_and_blank_lines_are_ignored():
    decoder = SSEDecoder()
    assert decoder.feed(": keep-alive") is None
    assert decoder.feed("") is None
    assert decoder.feed("") is None


def test_multiline_data_is_joined_with_newline():
    decoder = SSEDecoder()
    payload = {"text": "a\nb"}
    line = json.dumps(payload)
    decoder.feed(f"data: {line}")
    assert decoder.feed("") == payload


def test_invalid_json_is_dropped_without_raising():
    decoder = SSEDecoder()
    decoder.feed("data: not json")
    assert decoder.feed("") is None
    # decoder stays usable
    decoder.feed('data: {"ok": true}')
    assert decoder.feed("") == {"ok": True}
