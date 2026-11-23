# 字幕去除与硬字幕繁体转换

本仓库基于 [YaoFANGUK/video-subtitle-remover](https://github.com/YaoFANGUK/video-subtitle-remover)（Apache License 2.0，版权归 YaoFANGUK 及贡献者所有）。上游项目用本地模型擦除图片或视频里的硬字幕、文字水印，并保留原始分辨率。本仓库在完整上游源码之上增加了一项可选能力：把选区内的简体硬字幕转成台湾用语繁体，擦除原字后再画回去，并保留原音轨。

关闭这项能力时，擦除流程与上游一致。

![License](https://img.shields.io/badge/License-Apache%202.0-red.svg)
![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)

## 功能

- 无损分辨率去除硬字幕或文字水印。模型包括 STTN 智能擦除、STTN 字幕检测、LAMA、ProPainter、OpenCV。
- 可选硬字幕转繁体，不需要外部字幕文件：
  1. 对用户选区做文字检测和 OCR。
  2. 把时间上相同的行合并成一条字幕。
  3. 只用 OpenCC `s2twp` 转换汉字（台湾用语）。英文、数字和其他非中文保持原样。
  4. 用所选修复模型擦掉原来的字幕。
  5. 用内置 Noto Sans CJK TC（或你自己的字体）按原来的位置、大小和近似颜色把繁体字画回去。
  6. 用 FFmpeg 把原音轨拷回输出视频。
- 可选导出繁体 `.srt`。
- 可选 `--burn-srt`：校对 SRT 之后，再擦一遍并把校对稿烧回去。
- 命令行和原来的图形界面都可以打开这些开关。

## 环境

- Python 3.12 及以上
- Git，以及 [Git LFS](https://git-lfs.com/)
- 约 2 GB 磁盘（源码、字体和模型权重合计约 900 MB）

各平台的 FFmpeg 可执行文件已经放在 `backend/ffmpeg/`，程序会优先使用它们。

## 安装

### 1. 克隆并拉取 LFS 权重

模型权重在 Git LFS 里。只 `git clone`、不执行 `git lfs pull` 时，`.pt` / `.pth` / `.pdiparams` 和 FFmpeg 二进制会是几十到一两百字节的指针文本，程序无法加载。

```shell
git lfs install
git clone https://github.com/LuYiYan/subtitle-extractor.git
cd subtitle-extractor
git lfs pull
```

确认拿到的是真实文件，而不是指针：

```shell
git lfs ls-files
# 下面的文件应是几十 MB，而不是以 "version https://git-lfs.github.com/spec/v1" 开头
ls -lh backend/models/sttn-auto/infer_model.pth backend/models/sttn-det/sttn.pth
```

上游把超过约 50 MB 的 LAMA 和 ProPainter 权重拆成多个分片，并附带 `fs_manifest.csv`。本仓库保持这个分片布局。程序第一次用到 LAMA 或 ProPainter 时，会用 `filesplit` 按清单合成：

| 分片目录 | 清单 | 运行时合成的文件（已写入 .gitignore，不会提交） |
| --- | --- | --- |
| `backend/models/big-lama/` | `fs_manifest.csv` | `big-lama.pt` |
| `backend/models/propainter/` | `fs_manifest.csv` | `ProPainter.pth` |
| `backend/ffmpeg/win_x64/` | `fs_manifest.csv` | `ffmpeg.exe` |

STTN 的两个权重没有分片，路径是：

- `backend/models/sttn-auto/infer_model.pth`
- `backend/models/sttn-det/sttn.pth`

ProPainter 目录里还有未分片的 `raft-things.pth` 和 `recurrent_flow_completion.pth`，同样在 LFS 中。字幕检测用的 PP-OCRv5 检测模型在 `backend/models/V5/ch_det`（精准）和 `backend/models/V5/ch_det_fast`（快速）。

识别模型不在上游仓库里。第一次做繁体 OCR 时，PaddleOCR 会下载 `PP-OCRv5_server_rec` 到本机缓存。

### 2. 虚拟环境与依赖

```shell
python3 -m venv videoEnv
source videoEnv/bin/activate
# Windows: videoEnv\Scripts\activate
```

按显卡安装 Paddle 和 PyTorch，然后再装 `requirements.txt`。

NVIDIA CUDA 11.8：

```shell
pip install paddlepaddle-gpu==3.0.0 -i https://www.paddlepaddle.org.cn/packages/stable/cu118/
pip install torch==2.7.0 torchvision==0.22.0 --index-url https://download.pytorch.org/whl/cu118
pip install -r requirements.txt
pip install onnxruntime-gpu==1.20.1 --index-url https://aiinfra.pkgs.visualstudio.com/PublicPackages/_packaging/onnxruntime-cuda-11/pypi/simple/
```

CUDA 12.x 把最后一条换成 `pip install onnxruntime-gpu==1.22.0`。

只有 CPU 时：

```shell
pip install paddlepaddle==3.0.0 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
pip install torch==2.7.0 torchvision==0.22.0
pip install -r requirements.txt
```

macOS（Apple Silicon）同样使用 CPU 版 Paddle，Torch 用上面的 CPU/默认轮子即可。Windows 上的 AMD / Intel 显卡可以改用 DirectML：

```shell
pip install paddlepaddle==3.0.0 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
pip install -r requirements.txt
pip install torch_directml==0.2.5.dev240914
```

`requirements.txt` 里已经包含转繁体需要的 `opencc-python-reimplemented`（导入名是 `opencc`，配置名 `s2twp`）。

## 使用示例

坐标顺序是 `ymin ymax xmin xmax`，单位是像素，原点在左上角。`-c` 可以重复多次，表示多个区域。

只去硬字幕，不转繁体：

```shell
python backend/main.py -i input.mp4 -o output.mp4 -c 900 1080 120 1800 --inpaint-mode sttn-auto
```

识别选区里的硬字幕，擦除后画上台湾用语繁体，并写出 SRT：

```shell
python backend/main.py \
  -i input.mp4 \
  -o output_tc.mp4 \
  -c 900 1080 120 1800 \
  --to-traditional \
  --export-srt output_tc.srt
```

`--export-srt` 可以不跟路径，这时 SRT 与输出视频同名，扩展名换成 `.srt`。

只导出繁体 SRT、不把字画回画面（视频仍会按上游流程擦除字幕）：

```shell
python backend/main.py -i input.mp4 -o erased.mp4 -c 900 1080 120 1800 --export-srt erased.srt
```

校对 `output_tc.srt` 之后，用修正稿重新烧录。这一步不再使用 OCR 文本，画面上的字以 SRT 为准：

```shell
python backend/main.py \
  -i input.mp4 \
  -o output_fixed.mp4 \
  -c 900 1080 120 1800 \
  --burn-srt output_tc.srt
```

SRT 里如果还是简体，可以同时加上 `--to-traditional`，烧录前再跑一次 `s2twp`。非中文行不会被改写。

指定自己的字体：

```shell
python backend/main.py -i input.mp4 -c 900 1080 120 1800 --to-traditional --font /path/to/NotoSansCJKtc-Regular.otf
```

不传 `-c` 且打开了 `--to-traditional`、`--export-srt` 或 `--burn-srt` 时，程序不会整帧处理，而是使用界面里默认的底部字幕带（高度 88%–99%，宽度 15%–85%）。三个开关都关闭时，不传 `-c` 仍然表示整帧，和上游一样。

图形界面：

```shell
python gui.py
```

主页有两个开关：

- **硬字幕转繁体**：对应 `--to-traditional`。
- **导出繁体 SRT**：对应 `--export-srt`，文件写在输出视频旁边。

高级设置里可以换字体，以及选择一份修正后的 SRT 并打开「烧录修正后的 SRT」。字体留空时使用 `backend/fonts/NotoSansCJKtc-Regular.otf`。

## 命令行参数

| 参数 | 说明 |
| --- | --- |
| `-i` / `--input` | 输入视频或图片，必填 |
| `-o` / `--output` | 输出路径。省略时，视频写到输入文件旁边，名为 `<原名>_no_sub.mp4`；图片写到 `no_sub/` |
| `-c` / `--subtitle-area-coords YMIN YMAX XMIN XMAX` | 字幕区域，可重复 |
| `--inpaint-mode` | `sttn-auto`（默认）、`sttn-det`、`lama`、`propainter`、`opencv` |
| `--to-traditional` | 打开硬字幕转繁体。擦除后按原位置、字号和近似颜色重绘 |
| `--export-srt [PATH]` | 导出繁体 SRT。不写 PATH 时与输出文件同名 |
| `--burn-srt PATH` | 擦除后把这份 SRT 烧回选区。和 `--to-traditional` 一起用时，SRT 文本会再做 `s2twp` |
| `--font PATH` | `.otf` / `.ttf` / `.ttc`。省略时用内置 Noto Sans CJK TC |
| `-h` / `--help` | 打印以上说明 |

## 配置参数

图形界面和 `config/config.json` 使用 `backend/config.py` 里的这些项。命令行里的 `--inpaint-mode` 会覆盖当次运行的修复模型；其余项在命令行未传入对应开关时保持默认，因此直接跑命令行不会突然打开界面里保存的繁体开关。

| 配置项 | 默认值 | 作用 |
| --- | --- | --- |
| `interface` | 见界面语言 | `ch`、`chinese_cht`、`en`、`ko`、`japan`、`vi`、`es` |
| `subtitleSelectionAreas` | `0.88,0.99,0.15,0.85` | 界面默认选区，以及繁体功能未手工框选时的底部字幕带。值为 `ymin,ymax,xmin,xmax`，小于等于 1.5 时按宽高比例解释 |
| `inpaintMode` | `sttn-auto` | 修复模型 |
| `subtitleDetectMode` | `PP_OCRv5_SERVER` | `PP_OCRv5_SERVER` 精准检测，`PP_OCRv5_MOBILE` 快速检测 |
| `subtitleYXAxisDifferencePixel` | 10（0–300） | 文本框高度比宽度高出超过该像素时，视为误检并丢弃 |
| `subtitleAreaDeviationPixel` | 10（1–300） | 擦除 mask 四周扩展的像素，避免留下字边 |
| `subtitleAreaYAxisDifferencePixel` | 20（0–300） | 两个框的高度差在该值以内时视为同一行 |
| `subtitleAreaPixelToleranceYPixel` | 20（0–300） | 判断两个框是否为同一区域时的 Y 容差 |
| `subtitleAreaPixelToleranceXPixel` | 20（0–300） | 同上，X 容差 |
| `subtitleTimelineBackwardFrameCount` | 3（0–300） | 检测到字幕后，往前多擦的帧数 |
| `subtitleTimelineForwardFrameCount` | 3（0–300） | 往后多擦的帧数 |
| `sttnNeighborStride` | 5（1–100） | STTN 参考帧步长 |
| `sttnReferenceLength` | 10（1–100） | STTN 参考帧数量。单帧区间也会被扩展到不短于这个长度 |
| `sttnMaxLoadNum` | 50（1–300） | STTN 一次载入的最大帧数。实际值不会小于 `neighborStride * referenceLength` |
| `propainterMaxLoadNum` | 70（1–300） | ProPainter 一次处理的最大帧数，显存占用随之增加 |
| `hardwareAcceleration` | 开 | 使用 CUDA、MPS 或 ONNX。DirectML 只对两种 STTN 生效，其他模型会退回 CPU |
| `checkUpdateOnStartup` | 开 | 启动时检查更新 |
| `saveDirectory` | 空 | 空则保存到输入文件所在目录 |
| `toTraditional` | 关 | 与 `--to-traditional` 相同 |
| `exportTraditionalSrt` | 关 | 与不带路径的 `--export-srt` 相同 |
| `traditionalFontPath` | 空 | 空则使用内置 Noto Sans CJK TC |
| `burnCorrectedSrt` | 关 | 是否烧录 `burnSrtPath` |
| `burnSrtPath` | 空 | 校对后的 SRT 路径 |

模型怎么选：

- `sttn-auto`：真人视频较快，直接擦选区，不先做逐帧字幕检测。显存大约 4 GB 起。
- `sttn-det`：先检测字幕框再擦。显存大约 4 GB 起。
- `lama`：动画和单张图片更合适，必须先检测到文字。图片模式会固定使用 LAMA。
- `propainter`：运动很大的画面更好，更慢，显存大约 8 GB 起。
- `opencv`：最快，只做简单填充，不保证画面质量。

## 模型文件

这些是上游仓库里的官方权重，提交在 Git LFS 中：

| 文件 | 用途 |
| --- | --- |
| `backend/models/big-lama/big-lama_1.pt` … `big-lama_5.pt` | LAMA，50,000,000 字节分片，最后一片 5,803,670 字节 |
| `backend/models/propainter/ProPainter_1.pth` … `ProPainter_4.pth` | ProPainter 主权重分片 |
| `backend/models/propainter/raft-things.pth` | ProPainter 光流 |
| `backend/models/propainter/recurrent_flow_completion.pth` | ProPainter 光流补全 |
| `backend/models/sttn-auto/infer_model.pth` | STTN 智能擦除 |
| `backend/models/sttn-det/sttn.pth` | STTN 字幕检测版 |
| `backend/models/V5/ch_det/` | PP-OCRv5 精准检测 |
| `backend/models/V5/ch_det_fast/` | PP-OCRv5 快速检测 |

## 字体

`backend/fonts/NotoSansCJKtc-Regular.otf` 是 Noto Sans CJK TC Regular。版权为 Copyright 2014-2021 Adobe，Noto 是 Google 的商标，授权是 SIL Open Font License 1.1，全文在 `backend/fonts/OFL.txt`。该字体不适用 Apache-2.0。

## 测试

不加载 Paddle / PyTorch 的转换、合并、SRT 和绘制测试：

```shell
python tests/traditional_subtitle_test.py
```

## 许可证

- 本仓库中来自 video-subtitle-remover 的代码，以及在其上所做的修改，使用 [Apache License 2.0](LICENSE)。
- 上游项目地址：<https://github.com/YaoFANGUK/video-subtitle-remover>
- 变更说明见 [NOTICE](NOTICE)。
- Noto Sans CJK TC 使用 SIL OFL 1.1，见 `backend/fonts/OFL.txt`。
