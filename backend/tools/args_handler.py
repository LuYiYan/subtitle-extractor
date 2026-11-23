import argparse

from .constant import InpaintMode


def parse_args():
    parser = argparse.ArgumentParser(
        description="硬字幕去除，以及可选的简体硬字幕转台湾用语繁体"
    )
    parser.add_argument(
        "--input", "-i", required=True, type=str,
        help="输入视频或图片路径"
    )
    parser.add_argument(
        "--output", "-o", required=False, type=str, default=None,
        help="输出文件路径。省略时写到输入文件旁边，视频名为 <原名>_no_sub.mp4"
    )
    parser.add_argument(
        "--subtitle-area-coords", "-c", action="append", nargs=4, type=int,
        metavar=("YMIN", "YMAX", "XMIN", "XMAX"),
        help="字幕区域，像素坐标 ymin ymax xmin xmax。可重复传入多个区域"
    )
    parser.add_argument(
        "--inpaint-mode", type=str, default="sttn-auto",
        choices=[mode.name.lower().replace('_', '-') for mode in InpaintMode],
        help="擦除模型，默认 sttn-auto。可选 sttn-auto、sttn-det、lama、propainter、opencv"
    )
    parser.add_argument(
        "--to-traditional", action="store_true",
        help="识别选区内硬字幕，擦除后用 OpenCC s2twp 转成台湾用语繁体并按原位置重绘。非中文保持不变。关闭时行为与上游一致"
    )
    parser.add_argument(
        "--export-srt", nargs="?", const="", default=None, metavar="PATH",
        help="导出繁体 SRT。可以不带路径，默认写到输出视频同名 .srt；也可写成 --export-srt out.srt"
    )
    parser.add_argument(
        "--burn-srt", default=None, metavar="PATH",
        help="擦除硬字幕后，把这份已校对的 SRT 重新烧录回去。与 --to-traditional 同时使用时，会先把 SRT 中的简体转成繁体"
    )
    parser.add_argument(
        "--font", default=None, metavar="PATH",
        help="重绘字体，支持 .otf/.ttf/.ttc。默认使用内置 Noto Sans CJK TC"
    )
    parser.add_argument(
        "--target-lang", "--target", dest="target_lang", default=None, metavar="LANG",
        help="只用于静图：把图中的文字换成目标语言后另存。默认不启用。"
             "zh-Hant 为 OpenCC s2twp 繁体，还可选 en、ja、ko、es、vi、zh-Hans"
    )
    args = parser.parse_args()
    args.inpaint_mode = InpaintMode[args.inpaint_mode.replace('-', '_').upper()]
    if args.subtitle_area_coords is None:
        args.subtitle_area_coords = []
    return args
