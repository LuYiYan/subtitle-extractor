# -*- coding: utf-8 -*-
"""Pick an image, choose a target language, preview, and save a converted copy."""

import os

import cv2
import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QVBoxLayout, QWidget
from qfluentwidgets import ComboBox, PrimaryPushButton, PushButton, SubtitleLabel, TextEdit

from backend.config import config, tr
from backend.tools.image_text import (
    DEFAULT_TARGET,
    TARGET_LANGUAGES,
    convert_image_array,
    default_output_path,
    load_image,
    normalize_target,
    save_image,
    stack_comparison,
)


class _ConvertThread(QtCore.QThread):
    succeeded = QtCore.Signal(object, object)
    failed = QtCore.Signal(str)

    def __init__(self, image, target, font_path, parent=None):
        super().__init__(parent)
        self.image = image
        self.target = target
        self.font_path = font_path

    def run(self):
        try:
            result = convert_image_array(
                self.image,
                target=self.target,
                font_path=self.font_path or None,
                inpaint_mode="opencv",
            )
            self.succeeded.emit(self.image, result)
        except Exception as exc:
            self.failed.emit(str(exc))


class ImageTextInterface(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ImageTextInterface")
        self.image = None
        self.image_path = ""
        self.result = None
        self._thread = None
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(SubtitleLabel(tr["ImageText"]["Title"], self))

        controls = QHBoxLayout()
        self.open_button = PushButton(tr["ImageText"]["Open"], self)
        self.open_button.clicked.connect(self.open_image)
        controls.addWidget(self.open_button)

        self.target_box = ComboBox(self)
        self._codes = []
        saved = str(config.imageTargetLang.value or DEFAULT_TARGET)
        selected = 0
        for index, (code, label) in enumerate(TARGET_LANGUAGES):
            self.target_box.addItem(f"{label} ({code})")
            self._codes.append(code)
            if code == normalize_target(saved):
                selected = index
        self.target_box.setCurrentIndex(selected)
        self.target_box.currentIndexChanged.connect(self._store_target)
        controls.addWidget(self.target_box, 1)

        self.convert_button = PrimaryPushButton(tr["ImageText"]["Convert"], self)
        self.convert_button.clicked.connect(self.convert_image)
        controls.addWidget(self.convert_button)

        self.save_button = PushButton(tr["ImageText"]["Save"], self)
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self.save_image)
        controls.addWidget(self.save_button)
        layout.addLayout(controls)

        self.preview = QLabel(tr["ImageText"]["PreviewEmpty"], self)
        self.preview.setAlignment(QtCore.Qt.AlignCenter)
        self.preview.setMinimumHeight(360)
        self.preview.setStyleSheet("background: rgba(0, 0, 0, 18); border-radius: 8px;")
        layout.addWidget(self.preview, 1)

        self.log = TextEdit(self)
        self.log.setReadOnly(True)
        self.log.setFixedHeight(120)
        layout.addWidget(self.log)
        self._log(tr["ImageText"]["StatusReady"])

    def _store_target(self):
        config.set(config.imageTargetLang, self._codes[self.target_box.currentIndex()])

    def _log(self, text):
        self.log.append(str(text))

    def open_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr["ImageText"]["Open"],
            "",
            "Images (*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff)",
        )
        if not path:
            return
        try:
            self.image = load_image(path)
        except Exception as exc:
            self._log(tr["ImageText"]["StatusFailed"].format(exc))
            return
        self.image_path = path
        self.result = None
        self.save_button.setEnabled(False)
        self._show_preview(self.image)
        self._log(path)

    def convert_image(self):
        if self.image is None:
            self._log(tr["ImageText"]["NoImage"])
            return
        if self._thread is not None and self._thread.isRunning():
            return
        self.convert_button.setEnabled(False)
        self._log(tr["ImageText"]["StatusRunning"])
        font_path = str(config.traditionalFontPath.value or "")
        target = self._codes[self.target_box.currentIndex()]
        self._thread = _ConvertThread(self.image.copy(), target, font_path, self)
        self._thread.succeeded.connect(self._on_converted)
        self._thread.failed.connect(self._on_failed)
        self._thread.finished.connect(lambda: self.convert_button.setEnabled(True))
        self._thread.start()

    def _on_converted(self, original, result):
        self.result = result
        self.save_button.setEnabled(True)
        preview = original if not result.changes else stack_comparison(original, result.image)
        self._show_preview(preview)
        if not result.changes:
            self._log(tr["ImageText"]["NoChange"])
            return
        for change in result.changes:
            self._log(f"{change.original} -> {change.translated}")
        self._log(tr["ImageText"]["StatusDone"].format(len(result.changes)))

    def _on_failed(self, message):
        self._log(tr["ImageText"]["StatusFailed"].format(message))

    def save_image(self):
        if self.result is None:
            return
        suggestion = default_output_path(self.image_path or "image.png", self._codes[self.target_box.currentIndex()])
        path, _ = QFileDialog.getSaveFileName(
            self,
            tr["ImageText"]["Save"],
            suggestion,
            "Images (*.jpg *.jpeg *.png *.webp *.bmp)",
        )
        if not path:
            return
        save_image(path, self.result.image)
        self._log(tr["ImageText"]["Saved"].format(path))

    def _show_preview(self, image):
        rgb = np.ascontiguousarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
        height, width = rgb.shape[:2]
        qimage = QtGui.QImage(rgb.data, width, height, width * 3, QtGui.QImage.Format_RGB888).copy()
        pixmap = QtGui.QPixmap.fromImage(qimage)
        target = self.preview.size()
        if target.width() > 20 and target.height() > 20:
            pixmap = pixmap.scaled(target, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
        self.preview.setPixmap(pixmap)
