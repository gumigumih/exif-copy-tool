import tempfile
import unittest
import plistlib
from pathlib import Path
from unittest import mock

import exif_context_app as app


class PlatformSupportTests(unittest.TestCase):
    def test_generates_one_finder_service_per_format(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as helper_tmp, \
                mock.patch.object(app, "is_macos", return_value=True), \
                mock.patch.object(app, "finder_services_dir", return_value=Path(tmp)), \
                mock.patch.object(app, "finder_service_executable", return_value=Path(helper_tmp) / "ExifCopyService"), \
                mock.patch.object(app.subprocess, "run"):
            helper = Path(helper_tmp) / "ExifCopyService"
            helper.write_bytes(b"native service")
            count = app.sync_finder_format_services(app.DEFAULT_FORMATS[:2])
            generated = sorted(Path(tmp).glob("ExifCopyTool-*.service"))
            self.assertEqual(count, 2)
            self.assertEqual(len(generated), 2)
            with (generated[1] / "Contents" / "Info.plist").open("rb") as f:
                info = plistlib.load(f)
            service = info["NSServices"][0]
            self.assertEqual(service["NSMenuItem"]["default"], "EXIFコピー：SNS用")
            self.assertEqual(service["NSMessage"], "copyExif")
            self.assertEqual(service["NSUserData"], "SNS用")
            self.assertEqual(service["NSRequiredContext"]["NSApplicationIdentifier"], "com.apple.finder")
            self.assertIn("public.image", service["NSSendFileTypes"])
            executable = generated[1] / "Contents" / "MacOS" / "ExifCopyService"
            self.assertTrue(executable.is_file())
            self.assertTrue(executable.stat().st_mode & 0o111)

    def test_windows_data_dir_contract_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(app, "is_windows", return_value=True), \
                mock.patch.object(app, "is_macos", return_value=False), \
                mock.patch.dict(app.os.environ, {"APPDATA": tmp}):
            self.assertEqual(app.data_dir(), Path(tmp) / app.APP_NAME)

    def test_macos_data_dir_uses_application_support(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(app, "is_windows", return_value=False), \
                mock.patch.object(app, "is_macos", return_value=True), \
                mock.patch.object(Path, "home", return_value=Path(tmp)):
            self.assertEqual(
                app.data_dir(),
                Path(tmp) / "Library" / "Application Support" / app.APP_NAME,
            )

    def test_macos_clipboard_uses_osascript(self) -> None:
        with mock.patch.object(app, "is_windows", return_value=False), \
                mock.patch.object(app, "is_macos", return_value=True), \
                mock.patch.object(app, "_run_hidden") as run_hidden:
            app.copy_to_clipboard("日本語\nEXIF")
            args = run_hidden.call_args.args[0]
            self.assertEqual(args[:2], ["/usr/bin/osascript", "-e"])
            self.assertEqual(args[-1], "日本語\nEXIF")

    def test_macos_clipboard_falls_back_after_osascript_error(self) -> None:
        with mock.patch.object(app, "is_windows", return_value=False), \
                mock.patch.object(app, "is_macos", return_value=True), \
                mock.patch.object(app, "copy_to_clipboard_osascript", side_effect=RuntimeError("failed")), \
                mock.patch.object(app, "copy_to_clipboard_tk") as tk_copy:
            app.copy_to_clipboard("fallback")
            tk_copy.assert_called_once_with("fallback")

    def test_macos_format_picker_returns_selected_format(self) -> None:
        completed = mock.Mock(returncode=0, stdout="SNS用\n", stderr="")
        with mock.patch.object(app, "is_macos", return_value=True), \
                mock.patch.object(app.subprocess, "run", return_value=completed) as run:
            selected = app.choose_format_macos(app.DEFAULT_FORMATS)
        self.assertEqual(selected, "SNS用")
        args = run.call_args.args[0]
        self.assertEqual(args[:2], ["/usr/bin/osascript", "-e"])
        self.assertEqual(args[-4:], ["撮影設定", "SNS用", "Markdown", "全部ざっくり"])

    def test_macos_format_picker_allows_cancel(self) -> None:
        completed = mock.Mock(returncode=0, stdout="\n", stderr="")
        with mock.patch.object(app, "is_macos", return_value=True), \
                mock.patch.object(app.subprocess, "run", return_value=completed):
            self.assertIsNone(app.choose_format_macos(app.DEFAULT_FORMATS))

    def test_default_format_rendering_remains_available(self) -> None:
        rendered = app.render_template(
            app.DEFAULT_FORMATS[0]["template"],
            app.PREVIEW_SAMPLE_EXIF,
        )
        self.assertIn("SONY ILCE-7M4", rendered)
        self.assertIn("ISO400", rendered)


if __name__ == "__main__":
    unittest.main()
