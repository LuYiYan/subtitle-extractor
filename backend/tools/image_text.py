# -*- coding: utf-8 -*-
"""Convert text inside a still image and save a new image.

Default target is Traditional Chinese (OpenCC s2twp, Taiwan wording), the same
conversion used for hardcoded video subtitles. Other targets translate Han
text and leave Latin text, numbers, and the rest of the picture alone.
"""

import os
from dataclasses import dataclass, field

import cv2
import numpy as np

from backend.tools.ocr import get_coordinates
from backend.tools.traditional_subtitle import (
    TextLine,
    _HAN_RUN,
    _meaningful,
    convert_han,
    draw_text_line,
    estimate_text_color,
    get_converter,
    recognize_frame,
    resolve_font_path,
)

# First entry is the default. zh-Hant matches the video feature.
TARGET_LANGUAGES = (
    ("zh-Hant", "繁体中文（台湾）"),
    ("en", "English"),
    ("ja", "日本語"),
    ("ko", "한국어"),
    ("es", "Español"),
    ("vi", "Tiếng Việt"),
    ("zh-Hans", "简体中文"),
)
DEFAULT_TARGET = "zh-Hant"

_TARGET_ALIASES = {
    "zh-hant": "zh-Hant",
    "zh-tw": "zh-Hant",
    "zh_tw": "zh-Hant",
    "traditional": "zh-Hant",
    "cht": "zh-Hant",
    "繁体": "zh-Hant",
    "繁體": "zh-Hant",
    "zh-hans": "zh-Hans",
    "zh-cn": "zh-Hans",
    "zh_cn": "zh-Hans",
    "simplified": "zh-Hans",
    "简体": "zh-Hans",
    "簡體": "zh-Hans",
    "en": "en",
    "en-us": "en",
    "english": "en",
    "ja": "ja",
    "jp": "ja",
    "japanese": "ja",
    "ko": "ko",
    "korean": "ko",
    "es": "es",
    "spanish": "es",
    "vi": "vi",
    "vietnamese": "vi",
}

_OPENCC_CONFIG = {
    "zh-Hant": "s2twp",
    "zh-Hans": "tw2sp",
}
_TRANSLATE_CODE = {
    "en": "en",
    "ja": "ja",
    "ko": "ko",
    "es": "es",
    "vi": "vi",
}
_OPENCC_BY_CONFIG = {}


@dataclass
class ImageTextChange:
    original: str
    translated: str
    bbox: tuple
    color_bgr: tuple = (255, 255, 255)
    align: str = "center"


@dataclass
class ImageTextResult:
    image: np.ndarray
    changes: list = field(default_factory=list)
    skipped: list = field(default_factory=list)


def normalize_target(target):
    if target is None or str(target).strip() == "":
        return DEFAULT_TARGET
    key = str(target).strip()
    resolved = _TARGET_ALIASES.get(key.lower(), _TARGET_ALIASES.get(key))
    if resolved is None and key in dict(TARGET_LANGUAGES):
        resolved = key
    if resolved is None:
        known = ", ".join(code for code, _label in TARGET_LANGUAGES)
        raise ValueError(f"Unknown target language {target!r}. Choose one of: {known}")
    return resolved


def target_label(target):
    code = normalize_target(target)
    return dict(TARGET_LANGUAGES)[code]


def _opencc(config_name):
    converter = _OPENCC_BY_CONFIG.get(config_name)
    if converter is None:
        from opencc import OpenCC
        converter = OpenCC(config_name)
        _OPENCC_BY_CONFIG[config_name] = converter
    return converter


def translate_text(text, target=DEFAULT_TARGET, translator=None):
    """Translate Han text. Latin, digits, and punctuation stay in place."""
    if text is None:
        return text
    code = normalize_target(target)
    if not _HAN_RUN.search(text):
        return text
    if code in _OPENCC_CONFIG:
        config_name = _OPENCC_CONFIG[code]
        converter = get_converter() if config_name == "s2twp" else _opencc(config_name)
        return convert_han(text, converter)
    lang = _TRANSLATE_CODE[code]

    def replace(match):
        source = match.group(0)
        converted = _translate_han(source, lang, translator)
        if not converted or not str(converted).strip():
            raise RuntimeError(f"Translation to {code} returned empty text for {source!r}")
        return str(converted).strip()

    return _HAN_RUN.sub(replace, text)


def _translate_han(text, lang, translator):
    if translator is not None:
        return translator(text, lang)
    try:
        from deep_translator import GoogleTranslator
    except ImportError as exc:
        raise ImportError(
            "Translating to a language other than Traditional or Simplified Chinese "
            "needs deep-translator. Install it with: pip install deep-translator"
        ) from exc
    return GoogleTranslator(source="zh-CN", target=lang).translate(text)


def guess_alignment(crop):
    """Left, right, or center from where the ink sits inside the text crop."""
    if crop is None or crop.size == 0:
        return "center"
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    if float(gray.mean()) > 127:
        ink = gray < np.percentile(gray, 45)
    else:
        ink = gray > np.percentile(gray, 55)
    xs = np.where(ink)[1]
    if xs.size < 8:
        return "center"
    center = float(xs.mean()) / max(1, crop.shape[1])
    if center < 0.42:
        return "left"
    if center > 0.58:
        return "right"
    return "center"


class ImageTextDetector:
    """Full-image text detection using the same PP-OCRv5 weights as video mode."""

    def __init__(self, areas=None):
        self.areas = areas or []
        self._detector = None

    def _model_dir(self):
        return os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "models", "V5", "ch_det",
        )

    def _load(self):
        if self._detector is not None:
            return self._detector
        import paddle
        paddle.disable_signal_handler()
        from paddleocr import TextDetection
        model_dir = self._model_dir()
        kwargs = {"model_name": "PP-OCRv5_server_det", "device": "cpu"}
        if os.path.isfile(os.path.join(model_dir, "inference.pdiparams")):
            kwargs["model_dir"] = model_dir
        self._detector = TextDetection(**kwargs)
        return self._detector

    def detect_subtitle(self, img):
        results = self._load().predict(img)
        boxes = []
        for result in results:
            polys = result["dt_polys"] if isinstance(result, dict) else None
            if polys is None or len(polys) == 0:
                continue
            coords = get_coordinates(polys.tolist())
            if not self.areas:
                boxes.extend(coords)
                continue
            for xmin, xmax, ymin, ymax in coords:
                for ymin_s, ymax_s, xmin_s, xmax_s in self.areas:
                    if xmin_s <= xmin and xmax <= xmax_s and ymin_s <= ymin and ymax <= ymax_s:
                        boxes.append((xmin, xmax, ymin, ymax))
                        break
        return boxes


def ocr_image_lines(image, areas=None, detector=None, recognizer=None):
    from backend.tools.traditional_subtitle import TextRecognizer
    if detector is None:
        detector = ImageTextDetector(areas)
    if recognizer is None:
        recognizer = TextRecognizer()
    lines = recognize_frame(detector, recognizer, image)
    height, width = image.shape[:2]
    annotated = []
    for line in lines:
        xmin, xmax, ymin, ymax = line.bbox
        x1, x2 = max(0, xmin), min(width, xmax)
        y1, y2 = max(0, ymin), min(height, ymax)
        crop = image[y1:y2, x1:x2]
        line.align = guess_alignment(crop)
        annotated.append(line)
    return annotated


def _mask_for_boxes(shape, boxes, pad):
    mask = np.zeros(shape[:2], dtype=np.uint8)
    height, width = shape[:2]
    for xmin, xmax, ymin, ymax in boxes:
        x1 = max(0, int(xmin) - pad)
        y1 = max(0, int(ymin) - pad)
        x2 = min(width, int(xmax) + pad)
        y2 = min(height, int(ymax) + pad)
        if x2 > x1 and y2 > y1:
            cv2.rectangle(mask, (x1, y1), (x2, y2), 255, thickness=-1)
    return mask


def _inpaint(image, mask, mode):
    if mask is None or not np.any(mask):
        return image.copy()
    mode = (mode or "opencv").lower()
    if mode == "opencv":
        return cv2.inpaint(image, mask, 3, cv2.INPAINT_TELEA)
    if mode == "lama":
        return _lama_inpaint(image, mask)
    raise ValueError(f"Unknown inpaint mode {mode!r}. Use opencv or lama.")


def _lama_inpaint(image, mask):
    import torch
    from backend.inpaint.lama_inpaint import LamaInpaint
    from backend.tools.common_tools import merge_big_file_if_not_exists
    model_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "models", "big-lama",
    )
    merge_big_file_if_not_exists(model_dir, "big-lama.pt")
    model_path = os.path.join(model_dir, "big-lama.pt")
    if not os.path.isfile(model_path):
        raise FileNotFoundError(model_path)
    device = torch.device("cpu")
    engine = LamaInpaint(device, model_path)
    repaired = engine.inpaint(image, mask)
    if repaired.ndim == 2:
        repaired = cv2.cvtColor(repaired, cv2.COLOR_GRAY2BGR)
    return repaired


def convert_image_array(image, target=DEFAULT_TARGET, font_path=None, areas=None,
                        inpaint_mode="opencv", translator=None, lines=None, pad=6):
    """OCR, erase changed text, and draw the translation. Other pixels stay put."""
    if image is None or image.size == 0:
        raise ValueError("Empty image")
    if image.ndim == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    if image.shape[-1] == 4:
        image = cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
    font_path = resolve_font_path(font_path)
    if lines is None:
        lines = ocr_image_lines(image, areas)
    changes = []
    skipped = []
    for line in lines:
        if not line.text or not _meaningful(line.text) or not line.bbox:
            continue
        translated = translate_text(line.text, target, translator=translator)
        if translated == line.text:
            skipped.append(line.text)
            continue
        changes.append(ImageTextChange(
            original=line.text,
            translated=translated,
            bbox=tuple(int(value) for value in line.bbox),
            color_bgr=tuple(int(value) for value in (line.color_bgr or estimate_text_color(image))),
            align=getattr(line, "align", None) or "center",
        ))
    output = image.copy()
    if changes:
        mask = _mask_for_boxes(image.shape, [change.bbox for change in changes], pad)
        output = _inpaint(output, mask, inpaint_mode)
        for change in changes:
            draw_text_line(output, TextLine(
                change.translated, change.bbox, change.color_bgr, change.align,
            ), font_path)
    return ImageTextResult(output, changes, skipped)


def default_output_path(input_path, target=DEFAULT_TARGET):
    code = normalize_target(target)
    directory, name = os.path.split(input_path)
    stem, ext = os.path.splitext(name)
    if ext.lower() not in {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}:
        ext = ".png"
    return os.path.join(directory, f"{stem}_{code}{ext}")


def save_image(path, image):
    directory = os.path.dirname(os.path.abspath(path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    ext = os.path.splitext(path)[1].lower() or ".png"
    if ext not in {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}:
        raise ValueError(f"Unsupported image extension: {ext}")
    ok, encoded = cv2.imencode(ext, image)
    if not ok:
        raise RuntimeError(f"Failed to encode {path}")
    encoded.tofile(path)
    return path


def load_image(path):
    from backend.tools.common_tools import read_image
    image = read_image(path)
    if image is None:
        raise FileNotFoundError(path) if not os.path.isfile(path) else ValueError(f"Cannot read image {path}")
    return image


def stack_comparison(before, after, gap=8):
    """Place the original and converted images side by side."""
    if before.shape[0] != after.shape[0] or before.shape[1] != after.shape[1]:
        after = cv2.resize(after, (before.shape[1], before.shape[0]))
    if before.ndim == 2:
        before = cv2.cvtColor(before, cv2.COLOR_GRAY2BGR)
    if after.ndim == 2:
        after = cv2.cvtColor(after, cv2.COLOR_GRAY2BGR)
    divider = np.full((before.shape[0], gap, 3), 255, dtype=np.uint8)
    return np.hstack([before, divider, after])


def convert_image_file(input_path, output_path=None, target=DEFAULT_TARGET, font_path=None,
                       areas=None, inpaint_mode="opencv", translator=None, comparison_path=None):
    image = load_image(input_path)
    result = convert_image_array(
        image,
        target=target,
        font_path=font_path,
        areas=areas,
        inpaint_mode=inpaint_mode,
        translator=translator,
    )
    destination = output_path or default_output_path(input_path, target)
    save_image(destination, result.image)
    if comparison_path:
        save_image(comparison_path, stack_comparison(image, result.image))
    result.output_path = destination
    return result


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(
        description="把图片中的文字换成目标语言，其余画面保持不变，并保存成新图片"
    )
    parser.add_argument("-i", "--input", default=None, help="输入图片，支持 jpg、png、webp 等")
    parser.add_argument("-o", "--output", default=None, help="输出图片。省略时在原名后加上目标语言")
    parser.add_argument(
        "--target-lang", "--target", dest="target_lang", default=DEFAULT_TARGET,
        help="目标语言。默认 zh-Hant（OpenCC s2twp，台湾用语）。"
             "还可选 en、ja、ko、es、vi、zh-Hans",
    )
    parser.add_argument("--font", default=None, help="绘制字体。默认内置 Noto Sans CJK TC")
    parser.add_argument(
        "--inpaint", default="opencv", choices=["opencv", "lama"],
        help="擦除原文的方式。opencv 不需要显卡；lama 使用仓库里的 LAMA 权重",
    )
    parser.add_argument(
        "-c", "--area", action="append", nargs=4, type=int,
        metavar=("YMIN", "YMAX", "XMIN", "XMAX"),
        help="只处理这个区域内的文字，可重复。不传则处理整张图",
    )
    parser.add_argument(
        "--comparison", default=None,
        help="另外保存一张原图与结果的左右对比图",
    )
    parser.add_argument("--list-targets", action="store_true", help="列出目标语言后退出")
    args = parser.parse_args(argv)
    if args.list_targets:
        for code, label in TARGET_LANGUAGES:
            mark = " (default)" if code == DEFAULT_TARGET else ""
            print(f"{code}\t{label}{mark}")
        return 0
    if not args.input:
        parser.error("-i/--input is required")
    areas = [tuple(area) for area in args.area] if args.area else None
    result = convert_image_file(
        args.input,
        args.output,
        target=args.target_lang,
        font_path=args.font,
        areas=areas,
        inpaint_mode=args.inpaint,
        comparison_path=args.comparison,
    )
    print(f"Saved {result.output_path}")
    if not result.changes:
        print("No text needed conversion.")
    for change in result.changes:
        print(f"{change.original} -> {change.translated}")
    if result.skipped:
        print("Left unchanged: " + " | ".join(result.skipped))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
