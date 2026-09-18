from transcript_exports import transcript_srt, transcript_text


PAYLOAD = {
    "segments": [
        {"start_time": 0.0, "end_time": 1.25, "text": " First line. "},
        {"start_time": 61.234, "end_time": 62.5, "text": "Second line."},
    ]
}


def test_transcript_text() -> None:
    assert transcript_text(PAYLOAD) == "First line.\n\nSecond line.\n"


def test_transcript_srt() -> None:
    assert transcript_srt(PAYLOAD) == (
        "1\n"
        "00:00:00,000 --> 00:00:01,250\n"
        "First line.\n\n"
        "2\n"
        "00:01:01,234 --> 00:01:02,500\n"
        "Second line.\n"
    )
