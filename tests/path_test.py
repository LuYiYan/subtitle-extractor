# -*- coding: utf-8 -*-
import os
import sys
import tempfile
import unittest

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.tools.common_tools import read_image, windows_short_path_or_original
from backend.tools.qpt_paddle_modules import paddle_module_name


class ReadablePathTest(unittest.TestCase):
    def test_missing_short_name_keeps_the_original_path(self):
        path = r"E:\SubtitleExtractor\免抽气压缩收纳袋\sample.jpg"
        self.assertEqual(windows_short_path_or_original(path, 0, ""), path)
        self.assertEqual(windows_short_path_or_original(path, 0, None), path)

    def test_short_name_is_used_when_windows_returns_one(self):
        path = r"E:\SubtitleExtractor\免抽气压缩收纳袋\sample.jpg"
        short = r"E:\SUBTIT~1\sample.jpg"
        self.assertEqual(windows_short_path_or_original(path, len(short), short), short)

    def test_read_and_save_image_with_chinese_path(self):
        image = np.zeros((16, 16, 3), dtype=np.uint8)
        image[:, :, 1] = 255
        directory = tempfile.mkdtemp(prefix="path-test-")
        folder = os.path.join(directory, "免抽气压缩收纳袋")
        os.makedirs(folder)
        path = os.path.join(folder, "结果.jpg")
        ok, encoded = cv2.imencode(".jpg", image)
        self.assertTrue(ok)
        encoded.tofile(path)
        loaded = read_image(path)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.shape[0], 16)
        self.assertEqual(loaded.shape[1], 16)


class PaddleModuleNameTest(unittest.TestCase):
    def test_paddleocr_and_paddlex_do_not_share_a_qpt_folder(self):
        ocr = paddle_module_name("paddleocr")
        x = paddle_module_name("paddlex")
        self.assertNotEqual(ocr, x)
        self.assertEqual(ocr, "AddPaddlePaddlePackage_paddleocr")
        self.assertEqual(x, "AddPaddlePaddlePackage_paddlex")
        self.assertNotEqual(ocr, "AddPaddlePaddlePackage")


if __name__ == "__main__":
    unittest.main()
