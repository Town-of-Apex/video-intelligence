from faster_whisper import WhisperModel
import time


def transcribe(audio_path, model_size="large-v3-turbo"):
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, info = model.transcribe(audio_path, beam_size=5)
    return list(segments), info

def display_summary(segments, info):
    print(f"Detected language {info.language}")
    print(f"Total duration {info.duration:.2f} seconds")
    print(f"Total segments {len(segments)}")
    print(f"Average duration {info.duration / len(segments):.2f} seconds")

def display_transcript(segments):
    print("-"*80)
    for segment in segments:
        print("[%.2fs -> %.2fs] %.2f %s" % (segment.start, segment.end, segment.avg_logprob, segment.text))
    print("-"*80)


def main(model_size, audio_path):
    segments, info = transcribe(audio_path, model_size)
    display_summary(segments, info)
    display_transcript(segments)
    return info

if __name__ == "__main__":
    model_size = "tiny.en"
    audio_path = "emergency_contact_audio.mp3"

    start_time = time.perf_counter()
    info = main(model_size, audio_path)
    end_time = time.perf_counter()
    print(f"Time taken: {end_time - start_time:.2f} seconds")
    print(f"Speed: {info.duration / (end_time - start_time):.2f} file-seconds processed per second")