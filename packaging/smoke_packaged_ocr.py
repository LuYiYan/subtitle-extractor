# -*- coding: utf-8 -*-
"""Run inside the packaged QPT Python after first-run setup.

This checks the modules 「硬字幕转繁体」 actually imports, then runs detection,
recognition, and OpenCC s2twp on a Chinese image path. It is the regression
test for v1.4.3's ``No module named 'paddleocr'``.
"""

import importlib
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REQUIRED_MODULES = (
    "paddle",
    "paddleocr",
    "paddlex",
    "opencc",
    "cv2",
    "PIL",
    "torch",
    "torchvision",
    "av",
    "numpy",
    "yaml",
    "requests",
    "shapely",
    "pyclipper",
    "pypdfium2",
    "imagesize",
    "bidi",
    "PySide6",
    "qfluentwidgets",
    "einops",
    "skimage",
    "scipy",
    "tqdm",
    "darkdetect",
    "fsplit",
    "showinfm",
)


def _require_modules():
    missing = []
    for name in REQUIRED_MODULES:
        try:
            importlib.import_module(name)
        except Exception as exc:
            missing.append("%s: %s" % (name, exc))
    if missing:
        raise SystemExit("missing runtime modules:\n" + "\n".join(missing))
    from paddleocr import TextDetection, TextRecognition
    if TextDetection is None or TextRecognition is None:
        raise SystemExit("paddleocr did not export TextDetection/TextRecognition")


def _model_bytes(path):
    if not os.path.isfile(path):
        return 0
    return os.path.getsize(path)


def main():
    _require_modules()
    import cv2
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont

    from backend.tools.common_tools import get_readable_path, read_image
    from backend.tools.model_config import ModelConfig
    from backend.tools.subtitle_detect import SubtitleDetect
    from backend.tools.traditional_subtitle import (
        TextRecognizer,
        bundled_font_path,
        convert_han,
        default_rec_model_dir,
    )

    det_dir = ModelConfig().DET_MODEL_DIR
    det_params = os.path.join(det_dir, "inference.pdiparams")
    recognizer = TextRecognizer()
    rec_params = os.path.join(recognizer.model_dir or default_rec_model_dir(), "inference.pdiparams")
    for label, path in (("detection", det_params), ("recognition", rec_params)):
        size = _model_bytes(path)
        print("%s model: %s (%s bytes)" % (label, path, size))
        if size < 1000000:
            raise SystemExit("%s model is missing or still a Git LFS pointer: %s" % (label, path))

    font_path = bundled_font_path()
    if not os.path.isfile(font_path) or os.path.getsize(font_path) < 1000:
        raise SystemExit("bundled font is missing: %s" % font_path)

    image = Image.new("RGB", (960, 180), "white")
    draw = ImageDraw.Draw(image)
    draw.text((48, 36), "软件", fill="black", font=ImageFont.truetype(font_path, 96))
    rgb = np.array(image)
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

    directory = tempfile.mkdtemp(prefix="ocr-smoke-")
    folder = os.path.join(directory, "免抽气压缩收纳袋")
    os.makedirs(folder)
    image_path = os.path.join(folder, "sample.jpg")
    ok, encoded = cv2.imencode(".jpg", bgr)
    if not ok:
        raise SystemExit("failed to encode the smoke image")
    encoded.tofile(image_path)

    frame = read_image(image_path)
    if frame is None:
        raise SystemExit("read_image failed for Chinese path: %s" % image_path)
    readable = get_readable_path(image_path)
    if not readable:
        raise SystemExit("get_readable_path returned an empty path for %s" % image_path)
    if readable != image_path and read_image(readable) is None:
        raise SystemExit("short path could not be read: %s" % readable)

    saved = os.path.join(folder, "结果.jpg")
    encoded.tofile(saved)
    if read_image(saved) is None:
        raise SystemExit("saving the image to a Chinese path failed: %s" % saved)

    detector = SubtitleDetect(image_path, [])
    boxes = detector.detect_subtitle(frame)
    print("detected boxes: %s" % (boxes,))
    crops = []
    if boxes:
        height, width = frame.shape[:2]
        for xmin, xmax, ymin, ymax in boxes:
            x1 = max(0, int(xmin))
            x2 = min(width, int(xmax))
            y1 = max(0, int(ymin))
            y2 = min(height, int(ymax))
            if x2 - x1 >= 4 and y2 - y1 >= 4:
                crops.append(frame[y1:y2, x1:x2])
    if not crops:
        crops.append(frame)

    texts = []
    for crop in crops:
        text, score = recognizer.recognize(crop)
        converted = convert_han(text)
        texts.append((text, score, converted))
        print("ocr: %r score=%s converted=%r" % (text, score, converted))
    joined = "".join(converted for _text, _score, converted in texts)
    raw = "".join(text for text, _score, _converted in texts)
    compact = "".join(joined.split())
    raw_compact = "".join(raw.split())
    if "軟體" not in compact and "软件" not in raw_compact:
        raise SystemExit("OCR did not read 软件 from the packaged models: %s" % (texts,))
    if "軟體" not in compact:
        raise SystemExit("OpenCC s2twp did not convert the OCR text to 軟體: %s" % (texts,))
    print("packaged OCR smoke passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
