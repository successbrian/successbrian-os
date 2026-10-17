#!/usr/bin/env python3
"""Clone-test with F5-TTS: generate a test sentence in each separated voice.

Usage: ./venv/bin/python clone_test.py
Output: samples/test_a.mp3, samples/test_b.mp3

Brian listens and tells us which is Alex, which is Jordan.
"""
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
SMP = os.path.join(HERE, "samples")

TEXT = ("Hello! This is a voice cloning test for the Saturday podcast. "
        "If you can hear this clearly, the system can make my voice "
        "without any help from the outside.")


def main():
    from f5_tts.api import F5TTS
    tts = F5TTS()
    for v in ("a", "b"):
        ref = os.path.join(SMP, f"voice_{v}.wav")
        out = os.path.join(SMP, f"test_{v}.wav")
        print(f"generating voice {v}...", flush=True)
        tts.infer(ref_file=ref, ref_text="",
                   gen_text=TEXT, file_wave=out)
        mp3 = os.path.join(SMP, f"test_{v}.mp3")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", out,
                        "-codec:a", "libmp3lame", "-b:a", "128k", mp3],
                       check=True)
        print(f"done: {mp3}", flush=True)


if __name__ == "__main__":
    main()
