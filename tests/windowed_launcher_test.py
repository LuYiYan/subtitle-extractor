# -*- coding: utf-8 -*-
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.tools.windowed_launcher import (
    read_packaged_main_file,
    render_entry_cmd,
    render_sitecustomize,
)


class WindowedLauncherTest(unittest.TestCase):
    def test_entry_detaches_gui_with_pythonw(self):
        script = render_entry_cmd("gui.py")
        self.assertIn("pythonw.exe", script)
        self.assertIn('start "" /D "%CD%" "..\\Python\\pythonw.exe"', script)
        self.assertNotIn("pause", script.lower())
        self.assertIn("QPT_SETUP_ONLY=1", script)
        self.assertIn("set QPT_SETUP_ONLY=", script)
        self.assertIn("python.exe", script)
        self.assertLess(script.index("QPT_SETUP_ONLY=1"), script.index('start "" /D "%CD%" "..\\Python\\pythonw.exe"'))

    def test_entry_keeps_qpt_main_file(self):
        text = "set QPT_PY_MAIN_FILE=gui.py\r\n"
        self.assertEqual(read_packaged_main_file(text), "gui.py")
        self.assertEqual(read_packaged_main_file("set QPT_PY_MAIN_FILE=NONE\n"), "gui.py")

    def test_sitecustomize_survives_pythonw_and_setup_only(self):
        original = (
            "import os\n"
            "if \"ing\" not in os.environ.get(\"QPT_MODE\"):\n"
            " from qpt.run_wrapper import wrapper\n"
            " wrapper()\n"
            " from qpt.executor import RunExecutableModule\n"
            " RunExecutableModule(\"..\").run()\n"
        )
        updated = render_sitecustomize(original)
        self.assertIn("sys.stdout is None", updated)
        self.assertIn("QPT_SETUP_ONLY", updated)
        self.assertIn("SystemExit(0)", updated)
        self.assertIn("RunExecutableModule", updated)
        self.assertEqual(render_sitecustomize(updated), updated)


if __name__ == "__main__":
    unittest.main()
