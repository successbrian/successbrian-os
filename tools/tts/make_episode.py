#!/usr/bin/env python3
"""make_episode.py — dialogue script in, episode MP3 out. All on k11.

Input: a text file with speaker-labeled lines:
    Alex: Welcome to the Saturday podcast.
    Jordan: Thanks, Alex. Big week in AI...

Usage:
    ./venv/bin/python make_episode.py script.txt episode.mp3

Voice mapping lives in voices.json (alex/jordan -> ref wav).
Speed: ~20x real-time on k11 CPU. A 10-min segment takes ~3 hours.
Run overnight Friday for Saturday airtime.
"""
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SMP = os.path.join(HERE, "samples")


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    if p.returncode != 0:
        raise RuntimeError(f"{cmd[0]} failed: {p.stderr[:300]}")
    return p


def parse_script(path):
    turns = []
    for line in open(path):
        line = line.strip()
        if not line:
            continue
        m = re.match(r"(?i)^(alex|jordan)\s*:\s*(.+)$", line)
        if not m:
            raise ValueError(f"bad line (need 'Alex: ...'): {line[:60]}")
        turns.append((m.group(1).lower(), m.group(2)))
    if not turns:
        raise ValueError("empty script")
    return turns


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        raise SystemExit(1)
    script_path, out_mp3 = sys.argv[1], sys.argv[2]
    voices = json.load(open(os.path.join(HERE, "voices.json")))
    turns = parse_script(script_path)
    print(f"{len(turns)} turns", flush=True)

    from f5_tts.api import F5TTS
    tts = F5TTS()

    tmp = tempfile.mkdtemp(prefix="ep_")
    wavs = []
    for i, (speaker, text) in enumerate(turns):
        ref = os.path.join(SMP, voices[speaker])
        out = os.path.join(tmp, f"turn_{i:03d}.wav")
        print(f"[{i+1}/{len(turns)}] {speaker}: {text[:50]}...",
              flush=True)
        tts.infer(ref_file=ref, ref_text="", gen_text=text,
                   file_wave=out)
        wavs.append(out)

    # concat with 0.4s silence between turns
    run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
         "anullsrc=r=24000:cl=mono:d=0.4", os.path.join(tmp, "sil.wav"),
         "-t", "0.4"])
    lst = os.path.join(tmp, "list.txt")
    with open(lst, "w") as f:
        for w in wavs:
            f.write(f"file '{w}'\n")
            f.write(f"file '{os.path.join(tmp, 'sil.wav')}'\n")
    mixed = os.path.join(tmp, "mixed.wav")
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
         "-i", lst, "-c:a", "pcm_s16le", mixed])
    run(["ffmpeg", "-y", "-v", "error", "-i", mixed,
         "-codec:a", "libmp3lame", "-b:a", "128k", out_mp3])
    print(f"done: {out_mp3}", flush=True)


if __name__ == "__main__":
    main()
