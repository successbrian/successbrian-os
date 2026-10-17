#!/usr/bin/env python3
"""Split a mixed dialogue MP3 into two speaker clusters.

No ML: split on silence -> fingerprint each utterance (spectral centroid
mean/std + energy) -> k-means k=2 -> longest clean utterance per cluster.

Output: samples/voice_a.wav, samples/voice_b.wav (16kHz mono).
Which is Alex vs Jordan gets resolved against the dialogue script.
"""
import os
import re
import subprocess
import sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SMP = os.path.join(HERE, "samples")


def run(cmd, binary=False):
    p = subprocess.run(cmd, capture_output=True, text=not binary,
                       timeout=300)
    if p.returncode != 0:
        err = p.stderr[:200] if not binary else p.stderr[:200]
        raise RuntimeError(f"{cmd[0]} failed: {err}")
    return p


def to_wav(src, dst):
    run(["ffmpeg", "-y", "-v", "error", "-i", src, "-ac", "1", "-ar",
         "16000", "-c:a", "pcm_s16le", dst])


def utterances(wav):
    p = run(["ffmpeg", "-v", "info", "-i", wav, "-af",
             "silencedetect=noise=-35dB:d=0.4", "-f", "null", "-"])
    starts, ends = [], []
    for line in p.stderr.split("\n"):
        m = re.search(r"silence_start: ([\d.]+)", line)
        if m:
            ends.append(float(m.group(1)))
        m = re.search(r"silence_end: ([\d.]+)", line)
        if m:
            starts.append(float(m.group(1)))
    # utterance i: starts[i] .. ends[i+1]; also handle leading/trailing
    bounds = []
    prev = 0.0
    for s, e in zip(starts, ends):
        if s - prev > 1.5:
            bounds.append((prev, s))
        prev = e
    return bounds


def fingerprint(wav, start, dur):
    raw = run(["ffmpeg", "-v", "error", "-ss", str(start), "-t", str(dur),
               "-i", wav, "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
              binary=True)
    a = np.frombuffer(raw.stdout, dtype=np.float32)
    if len(a) < 1600:
        return None
    # frame-level spectral centroids
    n_fft, hop = 1024, 512
    cents = []
    for i in range(0, len(a) - n_fft, hop):
        fr = a[i:i + n_fft] * np.hanning(n_fft)
        sp = np.abs(np.fft.rfft(fr))
        if sp.sum() < 1e-6:
            continue
        freqs = np.fft.rfftfreq(n_fft, 1 / 16000)
        cents.append((freqs * sp).sum() / sp.sum())
    if not cents:
        return None
    cents = np.array(cents)
    return np.array([cents.mean(), cents.std(), np.abs(a).mean()])


def kmeans(X, k=2, iters=50):
    rng = np.random.default_rng(7)
    C = X[rng.choice(len(X), k, replace=False)]
    for _ in range(iters):
        d = ((X[:, None, :] - C[None, :, :]) ** 2).sum(-1)
        lab = d.argmin(1)
        new = np.array([X[lab == i].mean(0) if (lab == i).any() else C[i]
                        for i in range(k)])
        if np.allclose(new, C):
            break
        C = new
    return lab


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(SMP, "seg1.mp3")
    wav = os.path.join(SMP, "work.wav")
    to_wav(src, wav)
    bounds = utterances(wav)
    print(f"{len(bounds)} utterances")
    feats, kept = [], []
    for s, e in bounds:
        d = e - s
        if d < 2.0 or d > 25:
            continue
        f = fingerprint(wav, s, d)
        if f is not None:
            feats.append(f)
            kept.append((s, e, d))
    X = np.array(feats)
    # normalize
    Xn = (X - X.mean(0)) / (X.std(0) + 1e-9)
    lab = kmeans(Xn)
    for i in range(2):
        idx = [j for j, l in enumerate(lab) if l == i]
        idx.sort(key=lambda j: -kept[j][2])
        s, e, d = kept[idx[0]]
        out = os.path.join(SMP, f"voice_{'a' if i == 0 else 'b'}.wav")
        run(["ffmpeg", "-y", "-v", "error", "-ss", str(s), "-t", str(d),
             "-i", wav, "-c:a", "pcm_s16le", out])
        n_i = len(idx)
        print(f"cluster {i}: {n_i} utterances, sample {d:.1f}s -> {out}")


if __name__ == "__main__":
    main()
