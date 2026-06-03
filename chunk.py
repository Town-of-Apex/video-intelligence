import json
from pathlib import Path

TARGET_WORDS = 400
OVERLAP_WORDS = 75

METADATA_KEYS = ("video_id", "title", "duration_seconds", "transcribed_at")


def count_words(segments):
    return sum(len(segment["text"].split()) for segment in segments)


def overlap_segments(segments, overlap_words):
    """Return trailing segments whose combined word count meets the overlap threshold."""
    if not segments or overlap_words <= 0:
        return []

    overlap = []
    words = 0
    for segment in reversed(segments):
        overlap.insert(0, segment)
        words += len(segment["text"].split())
        if words >= overlap_words:
            break
    return overlap


def _normalize_segment_id(segment_id):
    return int(segment_id) if isinstance(segment_id, str) else segment_id


def create_chunk(segments, chunk_id):
    """Build a chunk dict from a list of transcript segments."""
    text = " ".join(segment["text"].strip() for segment in segments)
    return {
        "chunk_id": chunk_id,
        "start_time": segments[0]["start_time"],
        "end_time": segments[-1]["end_time"],
        "segment_ids": [_normalize_segment_id(segment["segment_id"]) for segment in segments],
        "text": text,
        "word_count": len(text.split()),
    }


def save_chunks(chunks, output_path, metadata):
    """Write chunks and video metadata to a JSON file."""
    payload = {
        **metadata,
        "chunk_count": len(chunks),
        "chunks": chunks,
    }
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
    return path


def extract_metadata(transcript):
    return {key: transcript[key] for key in METADATA_KEYS if key in transcript}


def load_transcript(path):
    with Path(path).open(encoding="utf-8") as handle:
        return json.load(handle)


def chunkify_segments(segments):
    """Split transcript segments into overlapping word-bounded chunks."""
    if not segments:
        return []

    chunks = []
    current_segments = []
    chunk_id = 1

    for segment in segments:
        current_segments.append(segment)

        if count_words(current_segments) >= TARGET_WORDS:
            chunks.append(create_chunk(current_segments, chunk_id))
            chunk_id += 1
            current_segments = overlap_segments(current_segments, OVERLAP_WORDS)

    if current_segments:
        if chunks:
            last_segment_ids = set(chunks[-1]["segment_ids"])
            current_segment_ids = {
                _normalize_segment_id(segment["segment_id"]) for segment in current_segments
            }
            if current_segment_ids.issubset(last_segment_ids):
                return chunks
        chunks.append(create_chunk(current_segments, chunk_id))

    return chunks


def chunkify_transcript(transcript):
    metadata = extract_metadata(transcript)
    chunks = chunkify_segments(transcript.get("segments", []))
    return chunks, metadata


def main(segments_json):
    output_suffix = "chunks"
    output_json = f"{segments_json.replace('_transcript.json', '')}_{output_suffix}.json"
    transcript = load_transcript(segments_json)
    chunks, metadata = chunkify_transcript(transcript)
    print(f"Output JSON will go to: {output_json}")
    save_chunks(chunks, output_json, metadata)

    print(f"Created {len(chunks)} chunks -> {output_json}")
    for chunk in chunks:
        print(
            f"  chunk {chunk['chunk_id']}: "
            f"{chunk['start_time']:.1f}s-{chunk['end_time']:.1f}s, "
            f"{chunk['word_count']} words, "
            f"segments {chunk['segment_ids']}"
        )


if __name__ == "__main__":
    segments_json = "emergency_contact_audio_transcript.json"
    main(segments_json)
