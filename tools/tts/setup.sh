#!/bin/bash
# setup.sh — rebuild the tts-clone runtime from this repo on any machine.
# Usage: ./setup.sh /home/successbrian/tts-clone
# Then: copy samples/voice_*.wav refs into <runtime>/samples/
set -e
RUNTIME="${1:-/home/successbrian/tts-clone}"
echo "runtime: $RUNTIME"
mkdir -p "$RUNTIME/samples"
cd "$RUNTIME"

if [ ! -d venv ]; then
  python3 -m venv venv
fi
./venv/bin/pip -q install --upgrade pip
# torch CPU first (PyPI torchcodec/torchaudio are CUDA builds and break)
./venv/bin/pip install torch --index-url https://download.pytorch.org/whl/cpu
./venv/bin/pip install f5-tts numpy
./venv/bin/pip install --force-reinstall --no-deps torchaudio \
  --index-url https://download.pytorch.org/whl/cpu
./venv/bin/pip install torchcodec \
  --index-url https://download.pytorch.org/whl/cpu

# deploy the code from the repo
HERE="$(cd "$(dirname "$0")" && pwd)"
cp "$HERE"/separate.py "$HERE"/clone_test.py "$HERE"/make_episode.py \
   "$HERE"/voices.json "$HERE"/pronunciation.md "$RUNTIME"/

./venv/bin/python -c "from f5_tts.api import F5TTS; print('F5TTS OK')"
echo "done. next: place voice ref wavs in $RUNTIME/samples/ and run:"
echo "  ./venv/bin/python clone_test.py"
