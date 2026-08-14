"""Encoding regressions for LAS input and CLI output."""

import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from wellio.cli import _configure_utf8_output
from wellio.parsers.las import read_las


LAS_TEXT = """~Version
VERS. 2.0 : CWLS LAS version
WRAP. NO : One line per depth step
~Well
STRT.F 0
STOP.F 1
STEP.F 1
NULL. -999.25
~Curve
DEPT.F : Depth Index
dhtemp.°F : Downhole_Temp
~ASCII
0 100
1 101
"""


class LasEncodingTests(unittest.TestCase):
    def _read_encoded_las(self, encoding: str):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "temperature.las"
            path.write_bytes(LAS_TEXT.encode(encoding))
            return read_las(path)

    def test_reads_utf8_header_without_mojibake(self):
        dataset = self._read_encoded_las("utf-8")

        self.assertEqual(dataset.curves[1].unit, "°F")

    def test_falls_back_for_legacy_windows_header(self):
        dataset = self._read_encoded_las("windows-1252")

        self.assertEqual(dataset.curves[1].unit, "°F")


class CliEncodingTests(unittest.TestCase):
    def test_reconfigures_standard_streams_as_strict_utf8(self):
        stdout_bytes = io.BytesIO()
        stderr_bytes = io.BytesIO()
        stdout = io.TextIOWrapper(stdout_bytes, encoding="gbk")
        stderr = io.TextIOWrapper(stderr_bytes, encoding="gbk")

        with patch.object(sys, "stdout", stdout), patch.object(sys, "stderr", stderr):
            _configure_utf8_output()
            print("Â°F", end="")
            print("错误", end="", file=sys.stderr)
            stdout.flush()
            stderr.flush()

        self.assertEqual(stdout.encoding, "utf-8")
        self.assertEqual(stderr.encoding, "utf-8")
        self.assertEqual(stdout.errors, "strict")
        self.assertEqual(stderr.errors, "strict")
        self.assertEqual(stdout_bytes.getvalue().decode("utf-8"), "Â°F")
        self.assertEqual(stderr_bytes.getvalue().decode("utf-8"), "错误")


if __name__ == "__main__":
    unittest.main()
