#!/bin/bash
# Pack vsr_out/Release the same way as upstream: a 7z volume set under GitHub's
# 2 GB asset limit. One volume is renamed back to a single .7z.
set -euo pipefail

VARIANT="${1:?variant name, for example windows-cpu}"
VERSION="${2:?version, for example 1.4.0}"
ROOT="${3:-vsr_out/Release}"

cd "$ROOT"
NAME="subtitle-extractor-v${VERSION}-${VARIANT}"

# Drop a previous archive so it is not packed into itself.
rm -f "${NAME}.7z" "${NAME}.7z".* "${NAME}.sha256"

7z a -t7z -mx=1 -m0=LZMA2 -ms=on -mmt=on -v2000m "${NAME}.7z" \
  * \
  -x!"${NAME}.7z" \
  -x!"${NAME}.7z.*" \
  -x!"${NAME}.sha256"

if [ -f "${NAME}.7z.001" ] && [ ! -f "${NAME}.7z.002" ]; then
  mv "${NAME}.7z.001" "${NAME}.7z"
fi

PYTHON=python
if ! command -v python >/dev/null 2>&1; then
  PYTHON=python3
fi

"$PYTHON" - "$NAME" <<'PY'
import hashlib
import glob
import os
import sys

name = sys.argv[1]
paths = sorted(glob.glob(name + ".7z*"))
if not paths:
    sys.exit("no archive was produced")
lines = []
for path in paths:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    size = os.path.getsize(path)
    lines.append(f"{digest.hexdigest()}  {os.path.basename(path)}  ({size} bytes)")
    print(lines[-1])
with open(name + ".sha256", "w", encoding="utf-8") as handle:
    handle.write("\n".join(lines) + "\n")
PY
