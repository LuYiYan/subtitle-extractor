# -*- coding: utf-8 -*-
"""Hardcoded subtitle Traditional Chinese conversion.

Pipeline when enabled: OCR the user-selected region, merge identical lines
over time, convert Simplified Chinese to Traditional Chinese with OpenCC
``s2twp`` (Taiwan wording), then redraw the text after the original subtitle
pixels have been erased. Non-Chinese text is left unchanged.

This module does not change removal behavior by itself. Callers run it only
when the user turns the feature on.
"""

import math
import os
import re
import tempfile
from collections import Counter
from dataclasses import dataclass, field

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

_HAN_RUN = re.compile(r'[\u3400-\u4dbf\u4e00-\u9fff]+')
_MEANINGFUL = re.compile(r'[\u3400-\u4dbf\u4e00-\u9fffA-Za-z0-9]')
_TIME_RE = re.compile(r'(\d+:\d+:\d+[,.]\d+)\s*-->\s*(\d+:\d+:\d+[,.]\d+)')
_TIMECODE_RE = re.compile(r'(\d+):(\d+):(\d+)[,.](\d+)')

_OPENCC = None
_FONT_CACHE = {}


@dataclass
class TextLine:
    """One subtitle line. bbox is (xmin, xmax, ymin, ymax) in full-frame pixels."""

    text: str
    bbox: tuple = None
    color_bgr: tuple = (255, 255, 255)
    align: str = "center"


@dataclass
class SubtitleCue:
    start_frame: int
    end_frame: int
    lines: list = field(default_factory=list)


def bundled_font_path():
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'fonts',
        'NotoSansCJKtc-Regular.otf',
    )


def resolve_font_path(user_path=None):
    """Use the user font when it exists, otherwise the bundled Noto Sans CJK TC."""
    if user_path and os.path.isfile(user_path):
        return os.path.abspath(user_path)
    bundled = bundled_font_path()
    if os.path.isfile(bundled):
        return bundled
    missing = user_path or bundled
    raise FileNotFoundError(missing)


def get_converter():
    global _OPENCC
    if _OPENCC is None:
        try:
            from opencc import OpenCC
        except ImportError as exc:
            raise ImportError(
                'OpenCC is required for Traditional conversion. '
                'Install it with: pip install opencc-python-reimplemented'
            ) from exc
        _OPENCC = OpenCC('s2twp')
    return _OPENCC


def convert_han(text, converter=None):
    """Convert Han characters with OpenCC s2twp. Other characters stay as they are."""
    if not text:
        return text
    if converter is None:
        converter = get_converter()
    return _HAN_RUN.sub(lambda match: converter.convert(match.group(0)), text)


def convert_cues(cues, converter=None):
    if converter is None:
        converter = get_converter()
    for cue in cues:
        for line in cue.lines:
            line.text = convert_han(line.text, converter)
    return cues


def default_subtitle_area(frame_h, frame_w, spec="0.88,0.99,0.15,0.85"):
    """Map ymin,ymax,xmin,xmax ratios (or absolute pixels) to a pixel rectangle."""
    ymin, ymax, xmin, xmax = [float(part) for part in str(spec).split(',')]
    if max(ymin, ymax, xmin, xmax) <= 1.5:
        top = int(round(ymin * frame_h))
        bottom = int(round(ymax * frame_h))
        left = int(round(xmin * frame_w))
        right = int(round(xmax * frame_w))
    else:
        top, bottom, left, right = int(ymin), int(ymax), int(xmin), int(xmax)
    top = max(0, min(top, max(0, frame_h - 1)))
    bottom = max(top + 1, min(bottom, frame_h))
    left = max(0, min(left, max(0, frame_w - 1)))
    right = max(left + 1, min(right, frame_w))
    return (top, bottom, left, right)


def sample_step_for_fps(fps):
    fps = float(fps or 0)
    if fps >= 60:
        return 4
    if fps >= 30:
        return 3
    return 2


def _meaningful(text):
    return bool(text and _MEANINGFUL.search(text))


def _match_key(text, converter):
    text = (text or '').strip()
    if _HAN_RUN.search(text):
        text = re.sub(r'\s+', '', text)
    else:
        text = re.sub(r'\s+', ' ', text)
    return convert_han(text, converter)


def _display_text(text):
    return re.sub(r'\s+', ' ', (text or '').strip())


def _sort_lines(lines):
    def sort_key(line):
        if not line.bbox:
            return (0, 0)
        return (line.bbox[2], line.bbox[0])
    return sorted(lines, key=sort_key)


def estimate_text_color(bgr):
    """Approximate subtitle color as the pixels that differ from the crop border."""
    if bgr is None or bgr.size == 0:
        return (255, 255, 255)
    if bgr.ndim == 2:
        bgr = cv2.cvtColor(bgr, cv2.COLOR_GRAY2BGR)
    if bgr.shape[-1] == 4:
        bgr = cv2.cvtColor(bgr, cv2.COLOR_BGRA2BGR)
    height, width = bgr.shape[:2]
    if height < 2 or width < 2:
        return (255, 255, 255)
    border = np.concatenate([
        bgr[0, :, :],
        bgr[-1, :, :],
        bgr[:, 0, :],
        bgr[:, -1, :],
    ], axis=0).astype(np.float32)
    background = np.median(border, axis=0)
    distance = np.linalg.norm(bgr.astype(np.float32) - background, axis=2)
    threshold = max(28.0, float(np.percentile(distance, 72)))
    pixels = bgr[distance >= threshold]
    if len(pixels) < 8:
        flat = bgr.reshape(-1, 3)
        order = np.argsort(distance.reshape(-1))
        take = max(8, len(order) // 8)
        pixels = flat[order[-take:]]
    median = np.median(np.asarray(pixels), axis=0)
    return tuple(int(round(channel)) for channel in median)


def merge_observations(frame_to_lines, sample_step, fps, frame_count, converter=None):
    """Merge identical on-screen text across nearby frames into cues."""
    frames = sorted(frame_to_lines)
    if not frames:
        return []
    if converter is None:
        converter = get_converter()
    max_gap = max(int(sample_step) * 2, int(round(float(fps or 25) * 0.5)))
    groups = []
    for frame_no in frames:
        lines = _sort_lines(frame_to_lines[frame_no])
        if not lines:
            continue
        signature = tuple(_match_key(line.text, converter) for line in lines)
        if groups and groups[-1][0] == signature and frame_no - groups[-1][1][-1][0] <= max_gap:
            groups[-1][1].append((frame_no, lines))
        else:
            groups.append([signature, [(frame_no, lines)]])

    cues = [_build_cue(items) for _signature, items in groups]
    pad = max(0, int(sample_step) // 2) if int(sample_step) > 1 else 0
    limit = int(frame_count or frames[-1])
    for index, cue in enumerate(cues):
        previous_end = cues[index - 1].end_frame if index else 0
        next_start = cues[index + 1].start_frame if index + 1 < len(cues) else limit + 1
        new_start = max(previous_end + 1, cue.start_frame - pad, 1)
        new_end = min(next_start - 1, cue.end_frame + pad, limit)
        cue.start_frame = new_start
        cue.end_frame = max(new_start, new_end)
    return cues


def _build_cue(items):
    sequences = [lines for _frame_no, lines in items]
    frame_numbers = [frame_no for frame_no, _lines in items]
    line_count = len(sequences[0])
    output_lines = []
    for index in range(line_count):
        texts = [_display_text(seq[index].text) for seq in sequences]
        text = Counter(texts).most_common(1)[0][0]
        bboxes = [seq[index].bbox for seq in sequences if seq[index].bbox]
        if bboxes:
            median_box = np.median(np.array(bboxes, dtype=float), axis=0)
            bbox = tuple(int(round(value)) for value in median_box)
        else:
            bbox = None
        colors = [seq[index].color_bgr for seq in sequences if seq[index].color_bgr]
        if colors:
            median_color = np.median(np.array(colors, dtype=float), axis=0)
            color = tuple(int(round(value)) for value in median_color)
        else:
            color = (255, 255, 255)
        output_lines.append(TextLine(text, bbox, color))
    return SubtitleCue(frame_numbers[0], frame_numbers[-1], output_lines)


def assign_region_layout(cues, areas, frame_size):
    """Place lines that have no box inside the user subtitle region."""
    width, height = frame_size
    if areas:
        ymin, ymax, xmin, xmax = [int(value) for value in areas[0]]
    else:
        ymin, ymax, xmin, xmax = default_subtitle_area(height, width)
    xmin = max(0, min(xmin, max(0, width - 1)))
    xmax = max(xmin + 1, min(xmax, width))
    ymin = max(0, min(ymin, max(0, height - 1)))
    ymax = max(ymin + 1, min(ymax, height))
    for cue in cues:
        pending = [line for line in cue.lines if not line.bbox]
        if not pending:
            continue
        count = len(pending)
        band = max(1, (ymax - ymin) // count)
        for index, line in enumerate(pending):
            y1 = ymin + index * band
            y2 = ymax if index == count - 1 else min(ymax, y1 + band)
            line.bbox = (xmin, xmax, y1, max(y1 + 1, y2))
            if not line.color_bgr:
                line.color_bgr = (255, 255, 255)
    return cues


def cues_to_sub_list(cues, frame_count=None):
    """Frame map of (xmin, xmax, ymin, ymax) boxes, the inpaint mask format."""
    sub_list = {}
    last_frame = int(frame_count) if frame_count else None
    for cue in cues:
        start = max(1, int(cue.start_frame))
        end = int(cue.end_frame)
        if last_frame:
            end = min(end, last_frame)
        if end < start:
            continue
        for frame_no in range(start, end + 1):
            boxes = sub_list.setdefault(frame_no, [])
            for line in cue.lines:
                if not line.bbox:
                    continue
                box = tuple(int(value) for value in line.bbox)
                if box not in boxes:
                    boxes.append(box)
    return sub_list


def union_box_lists(first, second):
    boxes = []
    for box in list(first or []) + list(second or []):
        box = tuple(int(value) for value in box)
        if box not in boxes:
            boxes.append(box)
    return boxes


def union_sub_lists(first, second):
    combined = {}
    keys = set(first or {}) | set(second or {})
    for key in keys:
        boxes = union_box_lists((first or {}).get(key), (second or {}).get(key))
        if boxes:
            combined[key] = boxes
    return combined


def frame_to_timecode(frame_no, fps):
    fps = float(fps) if fps else 25.0
    total_ms = int(round(max(0, int(frame_no) - 1) * 1000.0 / fps))
    hours, remainder = divmod(total_ms, 3600000)
    minutes, remainder = divmod(remainder, 60000)
    seconds, millis = divmod(remainder, 1000)
    return f'{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}'


def timecode_to_seconds(timecode):
    match = _TIMECODE_RE.match(timecode.strip())
    if not match:
        raise ValueError(f'Bad timecode: {timecode}')
    hours, minutes, seconds, millis = match.groups()
    millis = (millis + '000')[:3]
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000.0


def seconds_to_start_frame(seconds, fps):
    fps = float(fps) if fps else 25.0
    return max(1, int(math.floor(float(seconds) * fps + 1e-6)) + 1)


def seconds_to_end_frame(seconds, fps):
    fps = float(fps) if fps else 25.0
    return max(1, int(math.floor(float(seconds) * fps + 1e-6)))


def write_srt(path, cues, fps):
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    blocks = []
    index = 1
    for cue in cues:
        body = "\n".join(line.text for line in cue.lines if line.text)
        if not body.strip():
            continue
        start = frame_to_timecode(cue.start_frame, fps)
        end = frame_to_timecode(cue.end_frame + 1, fps)
        blocks.append(f"{index}\n{start} --> {end}\n{body}")
        index += 1
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write("\n\n".join(blocks))
        if blocks:
            handle.write("\n")
    return path


def parse_srt(text):
    text = (text or '').lstrip('\ufeff').replace('\r\n', '\n').replace('\r', '\n')
    if not text.strip():
        return []
    parsed = []
    for block in re.split(r'\n\s*\n', text.strip()):
        lines = block.split('\n')
        time_index = None
        start = end = None
        for index, line in enumerate(lines):
            match = _TIME_RE.search(line)
            if match:
                time_index = index
                start, end = match.group(1), match.group(2)
                break
        if time_index is None:
            continue
        body = [line.strip() for line in lines[time_index + 1:] if line.strip()]
        parsed.append((start, end, body))
    return parsed


def cues_from_srt(text, fps):
    cues = []
    for start_tc, end_tc, body in parse_srt(text):
        start_frame = seconds_to_start_frame(timecode_to_seconds(start_tc), fps)
        end_frame = seconds_to_end_frame(timecode_to_seconds(end_tc), fps)
        if end_frame < start_frame:
            end_frame = start_frame
        lines = [TextLine(line, None, (255, 255, 255)) for line in body if line.strip()]
        if lines:
            cues.append(SubtitleCue(start_frame, end_frame, lines))
    return cues


def _get_font(font_path, size):
    key = (font_path, int(size))
    font = _FONT_CACHE.get(key)
    if font is None:
        font = ImageFont.truetype(font_path, int(size))
        _FONT_CACHE[key] = font
    return font


def _stroke_color(color_bgr):
    blue, green, red = [int(channel) for channel in color_bgr]
    luminance = 0.114 * blue + 0.587 * green + 0.299 * red
    if luminance >= 160:
        return (0, 0, 0)
    return (255, 255, 255)


def draw_text_line(frame_bgr, line, font_path):
    """Draw one line, centered in its original box, in the approximate color."""
    if frame_bgr is None or not line or not line.text or not line.bbox or not font_path:
        return frame_bgr
    height, width = frame_bgr.shape[:2]
    xmin, xmax, ymin, ymax = [int(value) for value in line.bbox]
    xmin = max(0, min(xmin, width - 1))
    xmax = max(0, min(xmax, width))
    ymin = max(0, min(ymin, height - 1))
    ymax = max(0, min(ymax, height))
    if xmax - xmin < 4 or ymax - ymin < 4:
        return frame_bgr
    image = Image.fromarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(image)
    box_w = xmax - xmin
    box_h = ymax - ymin
    low = 8
    high = max(low, int(box_h * 0.92))
    best = low
    best_box = None
    while low <= high:
        mid = (low + high) // 2
        font = _get_font(font_path, mid)
        stroke = max(1, mid // 18)
        text_box = draw.textbbox((0, 0), line.text, font=font, stroke_width=stroke)
        text_w = text_box[2] - text_box[0]
        text_h = text_box[3] - text_box[1]
        if text_w <= box_w and text_h <= box_h:
            best = mid
            best_box = text_box
            low = mid + 1
        else:
            high = mid - 1
    font = _get_font(font_path, best)
    stroke = max(1, best // 18)
    if best_box is None:
        best_box = draw.textbbox((0, 0), line.text, font=font, stroke_width=stroke)
    text_w = best_box[2] - best_box[0]
    text_h = best_box[3] - best_box[1]
    align = getattr(line, "align", None) or "center"
    if align == "left":
        x = xmin - best_box[0]
    elif align == "right":
        x = xmax - text_w - best_box[0]
    else:
        x = xmin + max(0, (box_w - text_w) // 2) - best_box[0]
    y = ymin + max(0, (box_h - text_h) // 2) - best_box[1]
    color_bgr = line.color_bgr or (255, 255, 255)
    fill = (int(color_bgr[2]), int(color_bgr[1]), int(color_bgr[0]))
    stroke_bgr = _stroke_color(color_bgr)
    stroke_rgb = (stroke_bgr[2], stroke_bgr[1], stroke_bgr[0])
    draw.text((x, y), line.text, font=font, fill=fill, stroke_width=stroke, stroke_fill=stroke_rgb)
    frame_bgr[:] = cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR)
    return frame_bgr


def render_cues_on_frame(frame_bgr, cues, frame_no, font_path):
    for cue in cues:
        if cue.end_frame < frame_no:
            continue
        if cue.start_frame > frame_no:
            break
        for line in cue.lines:
            draw_text_line(frame_bgr, line, font_path)
    return frame_bgr


def burn_video(src_path, dst_path, cues, font_path, writer_factory=None):
    """Re-encode src_path with cue text drawn on each frame."""
    capture = cv2.VideoCapture(src_path)
    if not capture.isOpened():
        raise RuntimeError(f'Cannot open video: {src_path}')
    fps = capture.get(cv2.CAP_PROP_FPS) or 25
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if writer_factory is None:
        from backend.tools.video_io import FFmpegVideoWriter
        writer = FFmpegVideoWriter(dst_path, fps, (width, height))
    else:
        writer = writer_factory(dst_path, fps, (width, height))
    ordered = sorted(cues, key=lambda cue: (cue.start_frame, cue.end_frame))
    frame_no = 0
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            frame_no += 1
            render_cues_on_frame(frame, ordered, frame_no, font_path)
            writer.write(frame)
    finally:
        capture.release()
        writer.release()
    return dst_path


def sample_cue_colors(video_path, cues, is_picture=False):
    """Estimate text color from the original frames covered by each cue."""
    if not cues:
        return cues
    if is_picture:
        from backend.tools.common_tools import read_image
        frame = read_image(video_path)
        if frame is not None:
            _apply_colors(frame, cues)
        return cues
    from backend.tools.common_tools import get_readable_path
    capture = cv2.VideoCapture(get_readable_path(video_path))
    try:
        for cue in cues:
            capture.set(cv2.CAP_PROP_POS_FRAMES, max(0, cue.start_frame - 1))
            ok, frame = capture.read()
            if not ok:
                continue
            _apply_colors(frame, [cue])
    finally:
        capture.release()
    return cues


def _apply_colors(frame, cues):
    height, width = frame.shape[:2]
    for cue in cues:
        for line in cue.lines:
            if not line.bbox:
                continue
            xmin, xmax, ymin, ymax = [int(value) for value in line.bbox]
            x1, x2 = max(0, xmin), min(width, xmax)
            y1, y2 = max(0, ymin), min(height, ymax)
            if x2 <= x1 or y2 <= y1:
                continue
            line.color_bgr = estimate_text_color(frame[y1:y2, x1:x2])


def _parse_recognition(result):
    items = result if isinstance(result, (list, tuple)) else [result]
    best_text, best_score = '', 0.0
    for item in items:
        payload = item
        if not isinstance(payload, dict):
            to_json = getattr(payload, 'json', None)
            if callable(to_json):
                try:
                    payload = to_json()
                except Exception:
                    payload = {}
            else:
                payload = {
                    'rec_text': getattr(payload, 'rec_text', ''),
                    'rec_score': getattr(payload, 'rec_score', 0),
                }
        if isinstance(payload, dict) and isinstance(payload.get('res'), dict):
            payload = payload['res']
        if not isinstance(payload, dict):
            continue
        text = (payload.get('rec_text', payload.get('text', '')) or '').strip()
        try:
            score = float(payload.get('rec_score', payload.get('score', 0)) or 0)
        except (TypeError, ValueError):
            score = 0.0
        if score >= best_score:
            best_text, best_score = text, score
    return best_text, best_score


def default_rec_model_dir():
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'models', 'V5', 'ch_rec',
    )


class TextRecognizer:
    """PaddleOCR text recognition. The model is loaded on first use."""

    def __init__(self, model_dir=None):
        self.model_dir = model_dir
        self._model = None

    def _load(self):
        if self._model is not None:
            return self._model
        import paddle
        paddle.disable_signal_handler()
        from paddleocr import TextRecognition
        kwargs = {'model_name': 'PP-OCRv5_server_rec', 'device': 'cpu'}
        model_dir = self.model_dir or default_rec_model_dir()
        params = os.path.join(model_dir, 'inference.pdiparams')
        if os.path.isdir(model_dir) and os.path.isfile(params):
            kwargs['model_dir'] = model_dir
        self._model = TextRecognition(**kwargs)
        return self._model

    def recognize(self, image):
        model = self._load()
        try:
            result = model.predict(image)
        except Exception:
            handle, path = tempfile.mkstemp(suffix='.png')
            os.close(handle)
            try:
                cv2.imwrite(path, image)
                result = model.predict(path)
            finally:
                try:
                    os.remove(path)
                except OSError:
                    pass
        return _parse_recognition(result)


def recognize_frame(detector, recognizer, frame, min_score=0.45):
    boxes = detector.detect_subtitle(frame)
    height, width = frame.shape[:2]
    lines = []
    for xmin, xmax, ymin, ymax in boxes:
        if xmax - xmin < 4 or ymax - ymin < 8:
            continue
        pad = 2
        x1 = max(0, int(xmin) - pad)
        x2 = min(width, int(xmax) + pad)
        y1 = max(0, int(ymin) - pad)
        y2 = min(height, int(ymax) + pad)
        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            continue
        text, score = recognizer.recognize(crop)
        if score < min_score or not _meaningful(text):
            continue
        color = estimate_text_color(crop)
        lines.append(TextLine(text, (int(xmin), int(xmax), int(ymin), int(ymax)), color))
    return _sort_lines(lines)


def ocr_video_cues(video_path, sub_areas, is_picture, fps, frame_count, ab_sections=None):
    """OCR subtitle lines inside sub_areas and merge them into cues."""
    from tqdm import tqdm

    from backend.tools.inpaint_tools import is_frame_number_in_ab_sections
    from backend.tools.subtitle_detect import SubtitleDetect

    detector = SubtitleDetect(video_path, sub_areas)
    recognizer = TextRecognizer()
    sample_step = 1 if is_picture else sample_step_for_fps(fps)
    frame_to_lines = {}
    if is_picture:
        from backend.tools.common_tools import read_image
        frame = read_image(video_path)
        if frame is not None:
            lines = recognize_frame(detector, recognizer, frame)
            if lines:
                frame_to_lines[1] = lines
        total_frames = 1
    else:
        from backend.tools.common_tools import get_readable_path
        capture = cv2.VideoCapture(get_readable_path(video_path))
        total_frames = int(frame_count or capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        progress = tqdm(total=total_frames or None, unit='frame', desc='Subtitle OCR')
        frame_no = 0
        try:
            while capture.isOpened():
                ok, frame = capture.read()
                if not ok:
                    break
                frame_no += 1
                progress.update(1)
                if not is_frame_number_in_ab_sections(frame_no - 1, ab_sections):
                    continue
                if sample_step > 1 and (frame_no - 1) % sample_step != 0:
                    continue
                lines = recognize_frame(detector, recognizer, frame)
                if lines:
                    frame_to_lines[frame_no] = lines
        finally:
            progress.close()
            capture.release()
        if not total_frames:
            total_frames = frame_no
    return merge_observations(frame_to_lines, sample_step, fps or 25, total_frames)
