# -*- coding: utf-8 -*-
"""Point the QPT portable launcher at a windowed, detached GUI process.

Upstream QPT's Release shortcut is Debug.exe (a console program). It runs
``python.exe`` and then waits. Closing that console delivers a close event to
the GUI, because the GUI is attached to the same console.

The replacement keeps QPT's own windowed ``Main.exe``. That executable starts
``configs\\entry.cmd`` with WinExec and SW_HIDE, so it does not own a visible
console. The script then:

- on the first launch, opens a separate preparation window and exits that
  Python process before the GUI starts;
- starts the real app with ``pythonw.exe`` through ``start``, so the GUI is
  not attached to either console.
"""

import os
import shutil
import struct


def render_entry_cmd(main_file):
    """Batch script placed at Release/configs/entry.cmd."""
    main_file = (main_file or "gui.py").strip() or "gui.py"
    lines = [
        "@echo off",
        "chcp 65001 >nul",
        'cd /d "%~dp0"',
        "cd ..\\resources",
        "set QPT_COLOR=False",
        "set QPT_MODE=Run",
        "set PYTHONUNBUFFERED=1",
        "set PYTHONIOENCODING=utf-8",
        "set KMP_DUPLICATE_LIB_OK=TRUE",
        "set QPT_PY_MAIN_FILE=" + main_file,
        'if not exist "..\\Python\\pythonw.exe" (',
        "  echo pythonw.exe was not packaged.",
        "  exit /b 1",
        ")",
        'if not exist "..\\configs\\run_act.lock" (',
        "  set QPT_SETUP_ONLY=1",
        '  start "正在准备运行环境，请稍候" /wait /D "%CD%" cmd /c "echo 第一次打开，正在准备运行环境。请等待本窗口自己关掉，不要手动关闭。& ..\\Python\\python.exe %QPT_PY_MAIN_FILE%"',
        "  set QPT_SETUP_ONLY=",
        ")",
        'start "" /D "%CD%" "..\\Python\\pythonw.exe" %QPT_PY_MAIN_FILE%',
        "exit /b 0",
        "",
    ]
    return "\r\n".join(lines)


def render_sitecustomize(original):
    """Keep QPT's first-run setup, then return control to gui.py.

    pythonw has no console, so stdout/stderr cannot stay as None.

    Do not raise SystemExit here. sitecustomize runs while Python is still
    importing site. On Python 3.12 that abort is reported as
    ``Fatal Python error: init_import_site`` and the process never reaches
    ``-m pip``. QPT's first-run install invokes pip with the same environment,
    so a setup-only exit in this file makes every package install fail.
    gui.py exits normally after setup when QPT_SETUP_ONLY=1; pip never loads
    gui.py.
    """
    text = original or ""
    prefix = (
        "import os\n"
        "import sys\n"
        "if sys.stdout is None:\n"
        "    sys.stdout = open(os.devnull, 'w', encoding='utf-8', errors='replace')\n"
        "if sys.stderr is None:\n"
        "    sys.stderr = open(os.devnull, 'w', encoding='utf-8', errors='replace')\n"
    )
    if not text.startswith("import os"):
        text = prefix + text
    elif "sys.stdout is None" not in text:
        text = prefix + text
    # Drop the v1.4.1 hook if a previous patch already appended it.
    text = text.replace(
        "\nif os.environ.get('QPT_SETUP_ONLY') == '1':\n    raise SystemExit(0)\n",
        "\n",
    )
    return text


def read_packaged_main_file(entry_text, default="gui.py"):
    for line in (entry_text or "").splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("set qpt_py_main_file="):
            value = stripped.split("=", 1)[1].strip().strip('"')
            if value and value.upper() != "NONE":
                return value
    return default


def _pe_subsystem(path):
    data = open(path, "rb").read(512)
    if data[:2] != b"MZ":
        raise RuntimeError(path + " is not a Windows executable")
    e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
    with open(path, "rb") as handle:
        handle.seek(e_lfanew + 24 + 68)
        return struct.unpack("<H", handle.read(2))[0]


def install_windowed_launcher(release_dir, qpt_main_exe, icon_path=None):
    """Replace the console shortcut with QPT's windowed Main.exe and our script."""
    release_dir = os.path.abspath(release_dir)
    configs = os.path.join(release_dir, "configs")
    entry_path = os.path.join(configs, "entry.cmd")
    launcher_path = os.path.join(release_dir, "启动程序.exe")
    pythonw = os.path.join(release_dir, "Python", "pythonw.exe")
    sitecustomize = os.path.join(release_dir, "Python", "Lib", "site-packages", "sitecustomize.py")
    if not os.path.isfile(qpt_main_exe):
        raise FileNotFoundError(qpt_main_exe)
    if not os.path.isfile(pythonw):
        raise FileNotFoundError(pythonw)
    os.makedirs(configs, exist_ok=True)
    previous = ""
    if os.path.isfile(entry_path):
        with open(entry_path, "r", encoding="utf-8", errors="replace") as handle:
            previous = handle.read()
    main_file = read_packaged_main_file(previous)
    with open(entry_path, "w", encoding="utf-8-sig", newline="") as handle:
        handle.write(render_entry_cmd(main_file))
    shutil.copyfile(qpt_main_exe, launcher_path)
    if _pe_subsystem(launcher_path) != 2:
        raise RuntimeError("启动程序.exe is still a console program")
    if icon_path and os.path.isfile(icon_path):
        try:
            from qpt.kernel.qpe import make_icon
            make_icon(icon_path, pe_path=launcher_path, img_save_path=os.path.join(configs, "Logo.ico"))
        except Exception as exc:
            print("warning: launcher icon was not applied: " + str(exc))
    if os.path.isfile(sitecustomize):
        with open(sitecustomize, "r", encoding="utf-8", errors="replace") as handle:
            updated = render_sitecustomize(handle.read())
        with open(sitecustomize, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(updated)
    return entry_path
