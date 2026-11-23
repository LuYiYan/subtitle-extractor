# -*- coding: utf-8 -*-
import os
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.tools.traditional_subtitle import (
    SubtitleCue,
    TextLine,
    assign_region_layout,
    bundled_font_path,
    convert_cues,
    convert_han,
    cues_from_srt,
    cues_to_sub_list,
    default_subtitle_area,
    draw_text_line,
    estimate_text_color,
    merge_observations,
    parse_srt,
    render_cues_on_frame,
    write_srt,
)
from backend.tools.args_handler import parse_args


class TraditionalConversionTest(unittest.TestCase):
    def test_opencc_s2twp_taiwan_wording_and_non_chinese(self):
        samples = {
            '软件': '軟體',
            '网络': '網路',
            '视频': '影片',
            '内存': '記憶體',
            '默认': '預設',
            '程序': '程式',
            '互联网': '網際網路',
        }
        for simplified, traditional in samples.items():
            self.assertEqual(convert_han(simplified), traditional)
        self.assertEqual(convert_han('Hello, world! 123'), 'Hello, world! 123')
        self.assertEqual(convert_han('OK-软件'), 'OK-軟體')
        self.assertEqual(convert_han('（软件）'), '（軟體）')
        self.assertEqual(convert_han('Hello 软件'), 'Hello 軟體')

    def test_merge_identical_lines_and_keep_english(self):
        chinese = []
        for frame_no in (1, 4, 7):
            chinese.append((frame_no, [TextLine('软件', (10, 200, 400, 440), (255, 255, 255))]))
        english = []
        for frame_no in (40, 43):
            english.append((frame_no, [TextLine('Hello', (10, 80, 400, 440), (255, 255, 0))]))
        frame_to_lines = dict(chinese + english)
        cues = convert_cues(merge_observations(frame_to_lines, sample_step=3, fps=30, frame_count=50))
        self.assertEqual(len(cues), 2)
        self.assertEqual(cues[0].lines[0].text, '軟體')
        self.assertLessEqual(cues[0].start_frame, 1)
        self.assertGreaterEqual(cues[0].end_frame, 7)
        self.assertLess(cues[0].end_frame, cues[1].start_frame)
        self.assertEqual(cues[1].lines[0].text, 'Hello')
        self.assertEqual(cues[0].lines[0].color_bgr, (255, 255, 255))

    def test_different_text_is_not_merged(self):
        frame_to_lines = {
            1: [TextLine('软件', (0, 10, 0, 10), (255, 255, 255))],
            4: [TextLine('网络', (0, 10, 0, 10), (255, 255, 255))],
        }
        cues = merge_observations(frame_to_lines, sample_step=3, fps=30, frame_count=10)
        self.assertEqual(len(cues), 2)

    def test_srt_roundtrip(self):
        cues = [
            SubtitleCue(1, 25, [TextLine('軟體', (1, 2, 3, 4), (255, 255, 255))]),
            SubtitleCue(26, 50, [TextLine('Hello', (1, 2, 3, 4)), TextLine('網路', (1, 2, 8, 12))]),
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'out.srt')
            write_srt(path, cues, 25)
            with open(path, encoding='utf-8') as handle:
                parsed = cues_from_srt(handle.read(), 25)
        self.assertEqual([(cue.start_frame, cue.end_frame) for cue in parsed], [(1, 25), (26, 50)])
        self.assertEqual(parsed[0].lines[0].text, '軟體')
        self.assertEqual([line.text for line in parsed[1].lines], ['Hello', '網路'])

    def test_parse_srt_ignores_index_and_bom(self):
        text = "\ufeff1\n00:00:01,000 --> 00:00:02,000\n软件\n\n2\n00:00:02.500 --> 00:00:03.000\nHello\n"
        blocks = parse_srt(text)
        self.assertEqual(blocks[0][2], ['软件'])
        self.assertEqual(blocks[1][2], ['Hello'])

    def test_default_area_and_burn_layout(self):
        area = default_subtitle_area(1000, 2000, "0.88,0.99,0.15,0.85")
        self.assertEqual(area, (880, 990, 300, 1700))
        cues = cues_from_srt("1\n00:00:00,000 --> 00:00:01,000\n第一行\n第二行\n", 25)
        assign_region_layout(cues, [area], (2000, 1000))
        self.assertEqual(len(cues[0].lines), 2)
        self.assertLess(cues[0].lines[0].bbox[2], cues[0].lines[1].bbox[2])
        self.assertEqual(cues[0].lines[0].bbox[0], area[2])
        sub_list = cues_to_sub_list(cues, frame_count=25)
        self.assertIn(1, sub_list)
        self.assertIn(25, sub_list)
        self.assertNotIn(26, sub_list)

    def test_color_estimate_white_and_yellow_text(self):
        white = np.zeros((40, 80, 3), dtype=np.uint8)
        white[12:28, 20:60] = (255, 255, 255)
        color = estimate_text_color(white)
        self.assertGreater(min(color), 200)
        yellow = np.zeros((40, 80, 3), dtype=np.uint8)
        yellow[12:28, 20:60] = (0, 255, 255)
        color = estimate_text_color(yellow)
        self.assertLess(color[0], 40)
        self.assertGreater(color[1], 200)
        self.assertGreater(color[2], 200)

    def test_draw_uses_bundled_font(self):
        font = bundled_font_path()
        self.assertTrue(os.path.isfile(font))
        frame = np.zeros((80, 240, 3), dtype=np.uint8)
        line = TextLine('軟體', (10, 230, 10, 70), (255, 255, 255))
        draw_text_line(frame, line, font)
        self.assertGreater(int(frame.max()), 200)
        english = np.zeros((80, 240, 3), dtype=np.uint8)
        before = english.copy()
        draw_text_line(english, TextLine('Hello', (10, 160, 15, 65), (0, 255, 255)), font)
        self.assertFalse(np.array_equal(before, english))
        cues = [SubtitleCue(2, 2, [TextLine('軟體', (10, 230, 10, 70), (255, 255, 255))])]
        blank = np.zeros((80, 240, 3), dtype=np.uint8)
        render_cues_on_frame(blank, cues, 1, font)
        self.assertEqual(int(blank.max()), 0)
        render_cues_on_frame(blank, cues, 2, font)
        self.assertGreater(int(blank.max()), 200)

    def test_cli_flags(self):
        argv = sys.argv
        try:
            sys.argv = [
                'main', '-i', 'a.mp4', '--to-traditional', '--export-srt',
                '--burn-srt', 'fixed.srt', '--font', 'font.otf',
                '-c', '100', '200', '10', '300',
            ]
            args = parse_args()
            self.assertTrue(args.to_traditional)
            self.assertEqual(args.export_srt, '')
            self.assertEqual(args.burn_srt, 'fixed.srt')
            self.assertEqual(args.font, 'font.otf')
            self.assertEqual(args.subtitle_area_coords, [[100, 200, 10, 300]])
            sys.argv = ['main', '-i', 'a.mp4', '--export-srt', 'out.srt']
            args = parse_args()
            self.assertFalse(args.to_traditional)
            self.assertEqual(args.export_srt, 'out.srt')
            self.assertIsNone(args.burn_srt)
        finally:
            sys.argv = argv


if __name__ == '__main__':
    unittest.main()
