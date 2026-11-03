"""Create small sample recordings for testing the voice-note flow.

These are silent WAV files — the mock transcriber does not listen to the
audio, it picks a realistic transcript based on the file's contents. The
filenames say which transcript each one will produce.

Run:  python -m seed.make_sample_audio
Makes: sample_data/voice/*.wav
"""

from __future__ import annotations

import struct
import wave

from app.config import PROJECT_ROOT
from app.services.speech import MOCK_CALLS, MockSpeechToText

OUT_DIR = PROJECT_ROOT / "sample_data" / "voice"

# A short, readable name for each mock transcript.
SHORT_NAMES = [
    "college-fees",
    "phone-and-address-changed",
    "medical-costs",
    "application-stuck",
    "all-is-well",
    "anita-kumar-phone-changed",
    "santosh-sangwan-moved",
    "NEW-FAMILY-report",
]


def write_silent_wav(path, marker: int) -> bytes:
    """One second of silence, with a marker so each file differs."""
    frames = b"".join(struct.pack("<h", 0) for _ in range(8000))
    # A few non-zero samples at the start make each file's bytes unique.
    frames = struct.pack("<h", marker % 1000) + frames[2:]

    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(frames)
    return path.read_bytes()


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    engine = MockSpeechToText()

    # Find a marker value that makes each file produce the transcript we want,
    # so the filenames are honest about what the file will do.
    wanted = list(range(len(MOCK_CALLS)))
    found: dict[int, int] = {}
    marker = 0
    while len(found) < len(wanted) and marker < 20000:
        temp = OUT_DIR / "_probe.wav"
        data = write_silent_wav(temp, marker)
        text = engine.transcribe(data, "probe.wav").text_english
        index = next(i for i, c in enumerate(MOCK_CALLS) if c["text"] == text)
        if index not in found:
            found[index] = marker
        marker += 1

    probe = OUT_DIR / "_probe.wav"
    if probe.exists():
        probe.unlink()

    print(f"Wrote sample recordings to {OUT_DIR}")
    for index in sorted(found):
        name = SHORT_NAMES[index] if index < len(SHORT_NAMES) else f"call-{index}"
        path = OUT_DIR / f"{name}.wav"
        write_silent_wav(path, found[index])
        summary = MOCK_CALLS[index]["summary"]
        print(f"  {path.name:34} -> {summary[:70]}")

    missing = [i for i in wanted if i not in found]
    if missing:
        print(f"  (could not produce transcripts {missing})")


if __name__ == "__main__":
    main()
