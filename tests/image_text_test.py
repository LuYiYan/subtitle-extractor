# -*- coding: utf-8 -*-
import os
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.tools.image_text import (
    convert_image_array,
    convert_image_file,
    normalize_target,
    translate_text,
)
from backend.tools.traditional_subtitle import TextLine, bundled_font_path


def _sample_image():
    font = ImageFont.truetype(bundled_font_path(), 48)
    canvas = Image.new("RGB", (720, 360), (248, 244, 236))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((16, 16, 120, 90), fill=(24, 86, 150))
    draw.text((360, 36), "网络设置", font=font, fill=(140, 30, 30))
    draw.text((40, 140), "软件版本", font=font, fill=(20, 20, 20))
    draw.text((40, 240), "Hello 2024", font=font, fill=(20, 70, 40))
    image = np.array(canvas)[:, :, ::-1].copy()
    return image


class ImageTextLogicTest(unittest.TestCase):
    def test_target_aliases_and_non_chinese_stay(self):
        self.assertEqual(normalize_target("zh-tw"), "zh-Hant")
        self.assertEqual(normalize_target(None), "zh-Hant")
        self.assertEqual(translate_text("Hello 2024", "zh-Hant"), "Hello 2024")
        self.assertEqual(translate_text("软件版本", "zh-Hant"), "軟體版本")
        self.assertEqual(translate_text("网络设置", "traditional"), "網路設定")
        self.assertEqual(
            translate_text("Hello 软件 12", "en", translator=lambda text, lang: "software" if text == "软件" else text),
            "Hello software 12",
        )

    def test_injected_lines_keep_untouched_pixels_and_save(self):
        image = _sample_image()
        lines = [
            TextLine("软件版本", (36, 320, 140, 200), (20, 20, 20), "left"),
            TextLine("Hello 2024", (36, 360, 240, 300), (20, 70, 40), "left"),
        ]
        result = convert_image_array(image, "zh-Hant", lines=lines, inpaint_mode="opencv")
        self.assertEqual([change.translated for change in result.changes], ["軟體版本"])
        self.assertIn("Hello 2024", result.skipped)
        self.assertTrue(np.array_equal(image[20:80, 20:100], result.image[20:80, 20:100]))
        self.assertTrue(np.array_equal(image[250:290, 40:200], result.image[250:290, 40:200]))
        self.assertFalse(np.array_equal(image[145:195, 40:300], result.image[145:195, 40:300]))
        with tempfile.TemporaryDirectory() as directory:
            source = os.path.join(directory, "input.png")
            Image.fromarray(image[:, :, ::-1]).save(source)
            # The file path is only used by convert_image_file when OCR runs.
            # Here we check save_image through a second call with the same lines
            # by writing the result directly.
            from backend.tools.image_text import save_image
            output = os.path.join(directory, "output.png")
            save_image(output, result.image)
            self.assertTrue(os.path.isfile(output))
            self.assertGreater(os.path.getsize(output), 1000)


class ImageTextEndToEndTest(unittest.TestCase):
    def test_ocr_simplified_image_to_traditional(self):
        try:
            import paddleocr  # noqa: F401
        except ImportError:
            self.skipTest("paddleocr is not installed")
        image = _sample_image()
        repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        demo = os.path.join(repo, "docs", "demo")
        os.makedirs(demo, exist_ok=True)
        before = os.path.join(demo, "image_text_before.png")
        after = os.path.join(demo, "image_text_after.png")
        comparison = os.path.join(demo, "image_text_before_after.png")
        Image.fromarray(image[:, :, ::-1]).save(before)
        result = convert_image_file(
            before,
            after,
            target="zh-Hant",
            inpaint_mode="opencv",
            comparison_path=comparison,
        )
        joined = " ".join(change.translated for change in result.changes)
        self.assertTrue(os.path.isfile(after))
        self.assertTrue(os.path.isfile(comparison))
        self.assertIn("軟體", joined)
        self.assertTrue("網路" in joined or "設定" in joined)
        self.assertNotIn("软件", joined)
        self.assertNotIn("网络", joined)
        self.assertTrue(any("Hello" in text or "2024" in text for text in result.skipped))
        saved = np.array(Image.open(after).convert("RGB"))[:, :, ::-1]
        self.assertTrue(np.array_equal(image[20:80, 20:100], saved[20:80, 20:100]))


if __name__ == "__main__":
    unittest.main()
