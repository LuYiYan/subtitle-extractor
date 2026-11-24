import os
import sys
import ctypes

import cv2
import numpy as np
from fsplit.filesplit import Filesplit

video_extensions = {
    '.mp4', '.m4a', '.m4v', '.f4v', '.f4a', '.m4b', '.m4r', '.f4b', '.mov',
    '.3gp', '.3gp2', '.3g2', '.3gpp', '.3gpp2', '.ogg', '.oga', '.ogv', '.ogx',
    '.wmv', '.wma', '.asf', '.webm', '.flv', '.avi', '.gifv', '.mkv', '.rm',
    '.rmvb', '.vob', '.dvd', '.mpg', '.mpeg', '.mp2', '.mpe', '.mpv', '.mpg',
    '.mpeg', '.m2v', '.svi', '.3gp', '.mxf', '.roq', '.nsv', '.flv', '.f4v',
    '.f4p', '.f4a', '.f4b'
}

image_extensions = {
    '.jpg', '.jpeg', '.jpe', '.jif', '.jfif', '.jfi', '.png', '.gif',
    '.webp', '.tiff', '.tif', '.psd', '.raw', '.arw', '.cr2', '.nrw',
    '.k25', '.bmp', '.dib', '.heif', '.heic', '.ind', '.indd', '.indt',
    '.jp2', '.j2k', '.jpf', '.jpx', '.jpm', '.mj2', '.svg', '.svgz',
    '.ai', '.eps', '.ico'
}


def is_video_file(filename):
    return os.path.splitext(filename)[-1].lower() in video_extensions


def is_image_file(filename):
    return os.path.splitext(filename)[-1].lower() in image_extensions


def is_video_or_image(filename):
    file_extension = os.path.splitext(filename)[-1].lower()
    # 检查扩展名是否在定义的视频或图片文件后缀集合中
    return file_extension in video_extensions or file_extension in image_extensions

def merge_big_file_if_not_exists(dir, file, man_filename = None):
    if file not in os.listdir(dir):
        fs = Filesplit()
        if man_filename is not None:
            fs.man_filename = man_filename
        fs.merge(input_dir=dir)

def windows_short_path_or_original(path, short_length, short_value):
    """Use an 8.3 path when Windows created one, otherwise keep the original.

    GetShortPathNameW returns 0 on paths that have no short name. Modern
    Windows often disables 8.3 names, and a Chinese folder such as
    「免抽气压缩收纳袋」then has no short path. Returning the empty buffer
    makes OpenCV and the image reader look at a blank path.
    """
    if not path:
        return path
    if short_length and short_value:
        return short_value
    return path


def get_readable_path(path):
    if sys.platform != 'win32' or not path:
        return path
    buf = ctypes.create_unicode_buffer(4096)
    length = ctypes.windll.kernel32.GetShortPathNameW(str(path), buf, len(buf))
    return windows_short_path_or_original(path, length, buf.value)

def read_image(path):
    if os.path.getsize(path) > 100*1024*1024: # 100MB
        print(f"Image {path} is too large, skip")
        return None
    img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), -1)
    if img is not None and img.shape[-1] == 4:
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
    return img