# -*- coding: utf-8 -*-
"""Download the PP-OCRv5 recognition weights used by Traditional conversion.

Detection weights already live in this repo. The recognition weights are not
part of the upstream tree. The Windows portable package runs this before
QPT copies the project, so a downloaded app can convert text without a second
download. A source checkout that skips this step still lets PaddleOCR fetch
``PP-OCRv5_server_rec`` the first time Traditional conversion runs.
"""

import os
import shutil
import sys
import tarfile
import urllib.request

REC_MODEL_URL = (
    "https://paddle-model-ecology.bj.bcebos.com/paddlex/official_inference_model/"
    "paddle3.0.0/PP-OCRv5_server_rec_infer.tar"
)
_MIN_PARAMS_BYTES = 1_000_000


def rec_model_dir():
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(backend_dir, "models", "V5", "ch_rec")


def _is_real_params(path):
    if not os.path.isfile(path) or os.path.getsize(path) < _MIN_PARAMS_BYTES:
        return False
    with open(path, "rb") as handle:
        head = handle.read(48)
    return not head.startswith(b"version https://git-lfs.github.com/spec/v1")


def ensure_recognition_model(dest=None, url=REC_MODEL_URL):
    """Place inference.pdiparams into ``dest``. Return that directory."""
    dest = dest or rec_model_dir()
    params = os.path.join(dest, "inference.pdiparams")
    if _is_real_params(params):
        print(f"recognition model already present: {params}")
        return dest

    os.makedirs(dest, exist_ok=True)
    archive_path = os.path.join(dest, "PP-OCRv5_server_rec_infer.tar")
    print(f"downloading {url}")
    urllib.request.urlretrieve(url, archive_path)
    with tarfile.open(archive_path) as archive:
        archive.extractall(dest, filter="data")
    nested = os.path.join(dest, "PP-OCRv5_server_rec_infer")
    if os.path.isdir(nested):
        for name in os.listdir(nested):
            src = os.path.join(nested, name)
            target = os.path.join(dest, name)
            if os.path.exists(target):
                os.remove(target)
            shutil.move(src, target)
        os.rmdir(nested)
    os.remove(archive_path)
    if not _is_real_params(params):
        raise RuntimeError(f"recognition model was not extracted to {params}")
    print(f"recognition model ready: {params} ({os.path.getsize(params)} bytes)")
    return dest


def main():
    try:
        ensure_recognition_model()
    except Exception as exc:
        print(f"failed to download the recognition model: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
