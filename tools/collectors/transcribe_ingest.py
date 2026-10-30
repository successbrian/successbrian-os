#!/usr/bin/env python3
"""transcribe_ingest — on-demand transcription -> intel (Tier 2, 2026-10-27).

PURPOSE: URL or audio/video file in -> audio via yt-dlp/ffmpeg ->
faster-whisper (CPU, small model default) -> timestamped transcript ->
filed as an Intel Bridge intel capture AND embedded into the owning
AnythingLLM workspace via allm_embed.py, routed by
allm_workspaces.determine() (fallback: successbrian-os workspace,
noted in the capture when the fallback is used).
CALLED BY: on demand only (no cron — transcription is CPU-heavy;
check tools/guardrails/capacity.py view before long jobs).
Runs under ~/collectors/venvs/transcribe; re-execs itself there.
Usage: transcribe_ingest.py <url-or-file> [--model small|medium]
       [--title T] [--no-embed] | selftest
Nothing sends/posts/publishes.
"""
import datetime
import os
import subprocess
import sys
import tempfile

VENV_PY = os.path.expanduser("~/collectors/venvs/transcribe/bin/python")
HERE = os.path.dirname(os.path.abspath(__file__))
ATLAS = os.path.join(HERE, "..", "atlas")
sys.path.insert(0, ATLAS)

try:
    from faster_whisper import WhisperModel
except ImportError:
    if os.path.exists(VENV_PY) and os.path.abspath(sys.executable) != os.path.abspath(VENV_PY):
        os.execv(VENV_PY, [VENV_PY, os.path.abspath(__file__)] + sys.argv[1:])
    raise

SELFTEST_URL = ("https://dn601302.us.archive.org/0/items/"
                "gettysburg_address_librivox/"
                "gettysburg_address_lincoln_64kb.mp3")
# LibriVox recording of Lincoln's Gettysburg Address (public domain
# text + LibriVox PD release), full file 2:41; selftest trims to the
# first 110 seconds to respect the <=2 min selftest-clip rule.


def get_audio(src, workdir):
    out = os.path.join(workdir, "audio.wav")
    if src.startswith("http"):
        raw = os.path.join(workdir, "raw.media")
        subprocess.run(["yt-dlp", "-x", "--audio-format", "mp3", "-o",
                        raw, src], check=True, capture_output=True)
        got = [f for f in os.listdir(workdir) if f.startswith("raw")]
        srcfile = os.path.join(workdir, got[0])
    else:
        srcfile = src
    subprocess.run(["ffmpeg", "-y", "-i", srcfile, "-ar", "16000", "-ac",
                    "1", out], check=True, capture_output=True)
    return out


def transcribe(wav, model_name):
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    segments, info = model.transcribe(wav)
    lines = []
    for s in segments:
        lines.append("[%02d:%02d] %s" % (int(s.start // 60),
                                         int(s.start % 60),
                                         s.text.strip()))
    return "\n".join(lines), info.language


def route_workspace(subject):
    """determine() routing; returns (slug, note)."""
    try:
        import allm_workspaces
        import scattered_brain
        conn = scattered_brain.pg()
        try:
            verdict = allm_workspaces.determine(conn, subject)
            slug = verdict.get("workspace")
            if slug:
                return slug, "determine() verdict=%s" % verdict.get("verdict")
        finally:
            conn.close()
    except Exception as e:  # routing is best-effort, never fatal
        return "successbrian-os", "determine() unavailable (%s); fallback" % e
    return "successbrian-os", "determine() gave no workspace; fallback"


def ingest(src, model_name="small", title=None, embed=True):
    today = datetime.date.today().isoformat()
    with tempfile.TemporaryDirectory() as wd:
        wav = get_audio(src, wd)
        transcript, lang = transcribe(wav, model_name)
    subject = title or src
    slug, note = route_workspace(subject)
    fname = "transcript-%s.md" % today
    doc = "# Transcript: %s\n\nSource: %s\nDate: %s\nModel: faster-whisper %s (language: %s)\n\n%s\n" % (
        subject, src, today, model_name, lang, transcript)
    path = os.path.join(tempfile.gettempdir(), fname)
    with open(path, "w") as f:
        f.write(doc)
    import scattered_brain
    conn = scattered_brain.pg()
    try:
        cid = scattered_brain.capture(
            conn,
            "Transcript: %s" % subject[:170],
            context="kind=intel; source=transcribe_ingest.py "
                    "(faster-whisper %s); source: %s; checked %s; "
                    "ALLM workspace: %s (%s)" % (model_name, src, today,
                                                 slug, note),
            raw=transcript[:20000])
    finally:
        conn.close()
    embedded = False
    if embed:
        r = subprocess.run([sys.executable,
                            os.path.join(ATLAS, "allm_embed.py"),
                            slug, fname, path],
                           capture_output=True, text=True)
        embedded = r.returncode == 0
        if not embedded:
            print("WARN allm_embed failed: %s" % (r.stderr or r.stdout)[:300],
                  file=sys.stderr)
    return cid, slug, embedded, transcript


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    if argv[1] == "selftest":
        raw = "/tmp/gettysburg_full.mp3"
        trim = "/tmp/gettysburg_trim110.mp3"
        subprocess.run(["curl", "-sL", "-o", raw, SELFTEST_URL], check=True)
        subprocess.run(["ffmpeg", "-y", "-i", raw, "-t", "110", trim],
                       check=True, capture_output=True)
        cid, slug, embedded, transcript = ingest(
            trim, "small",
            title="SELFTEST Gettysburg Address (LibriVox, first 110s)")
        print("selftest: capture #%d workspace=%s embedded=%s"
              % (cid, slug, embedded))
        print("transcript excerpt: %r" % transcript[:300])
        return 0
    src = argv[1]
    model = "small"
    if "--model" in argv:
        model = argv[argv.index("--model") + 1]
    title = None
    if "--title" in argv:
        title = argv[argv.index("--title") + 1]
    cid, slug, embedded, transcript = ingest(
        src, model, title, embed="--no-embed" not in argv)
    print(transcript)
    print("\n[capture #%d; workspace %s; embedded=%s]" % (cid, slug, embedded),
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
