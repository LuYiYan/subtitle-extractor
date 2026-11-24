# -*- coding: utf-8 -*-
import os
import unittest


ISS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "packaging",
    "subtitle-extractor.iss",
)


class InstallerPathTest(unittest.TestCase):
    def setUp(self):
        with open(ISS_PATH, "r", encoding="utf-8-sig") as handle:
            self.script = handle.read()

    def test_default_directory_is_ascii_without_spaces(self):
        self.assertIn("DefaultDirName=C:\\SubtitleExtractor", self.script)
        self.assertNotIn("{autopf}", self.script)
        self.assertIn("UsePreviousAppDir=no", self.script)

    def test_wizard_blocks_chinese_and_spaces(self):
        self.assertIn("IsSafeInstallDir", self.script)
        self.assertIn("不能包含中文、空格或其他特殊字符", self.script)
        self.assertIn("C:\\SubtitleExtractor", self.script)
        self.assertIn("E:\\SubtitleExtractor", self.script)
        self.assertIn("字幕去除器", self.script)
        self.assertNotIn("试用", self.script)


if __name__ == "__main__":
    unittest.main()
