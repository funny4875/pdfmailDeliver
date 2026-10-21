import os
import tempfile
import unittest
from unittest.mock import patch

import updater


class UpdateLocationTest(unittest.TestCase):
    def test_download_and_replace_use_application_drive(self):
        with tempfile.TemporaryDirectory() as app_path:
            target = os.path.join(app_path, "pdfmailDeliver.py")
            with open(target, "wb") as file:
                file.write(b"old")

            def fake_download(url, path):
                self.assertEqual(os.path.dirname(os.path.dirname(path)), app_path)
                with open(path, "wb") as file:
                    file.write(b"new")

            manifest = {"files": [{"path": "pdfmailDeliver.py", "url": "mock://new"}]}
            with patch.object(updater, "download_file", side_effect=fake_download):
                updater.apply_update(app_path, manifest)

            with open(target, "rb") as file:
                self.assertEqual(file.read(), b"new")
            self.assertFalse(any(name.startswith("pdfmail_update_") for name in os.listdir(app_path)))


if __name__ == "__main__":
    unittest.main()
