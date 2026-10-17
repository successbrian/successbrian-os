# tts — local voice cloning for the Saturday podcast

Alex and Jordan, generated on Brian's own iron. No Hatch, no Meta API,
no cost. F5-TTS zero-shot voice cloning, CPU inference on k11.

## Layout

- Runtime: `/home/successbrian/tts-clone/` (venv, model cache, samples)
- Code source of truth: this directory (`tools/tts/` in successbrian-os)
- Deploy: copy `*.py`, `voices.json`, `pronunciation.md` to the runtime dir

## Files

- `separate.py` — split a mixed dialogue MP3 into two speaker clusters
  (silence split -> spectral fingerprint -> k-means). No ML needed.
- `clone_test.py` — generate a test sentence per voice for Brian's QA.
- `make_episode.py` — dialogue script in, episode MP3 out.
  Format: `Alex: ...` / `Jordan: ...` lines. Concatenates turns with
  0.4s pauses.
- `voices.json` — alex/jordan -> reference wav mapping. Brian decides
  which cluster is which by ear.
- `pronunciation.md` — mispronunciation log; dialogue writer checks it
  before scripting.

## Reference voices

`samples/voice_a.wav`, `samples/voice_b.wav` — separated from the
2026-10-10 episode (live in the runtime dir, not in git).

## Speed (honest)

~20x real-time on k11 CPU. A 10-minute segment takes ~3 hours.
Run overnight Friday for Saturday 7:30 PM airtime. A GPU (incoming
GT103, Mantis builds) cuts this to minutes — the pipeline doesn't care
where it runs.

## Setup (done 2026-10-17)

```
python3 -m venv venv && ./venv/bin/pip install torch \
  --index-url https://download.pytorch.org/whl/cpu
./venv/bin/pip install f5-tts
./venv/bin/pip install --force-reinstall --no-deps torchaudio \
  --index-url https://download.pytorch.org/whl/cpu
./venv/bin/pip install torchcodec \
  --index-url https://download.pytorch.org/whl/cpu
```

Gotchas hit: coqui-TTS needs Python <3.12 (k11 has 3.12) -> used F5-TTS;
PyPI torchaudio is a CUDA build -> force from CPU index; torchcodec
native lib fails from PyPI -> CPU index build works.
