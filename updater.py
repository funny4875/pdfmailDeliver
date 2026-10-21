import json
import os
import re
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime


# ================= GitHub 更新設定 =================
# GitHub 上 update.json 的 raw 網址。
MANIFEST_URL = "https://raw.githubusercontent.com/funny4875/pdfmailDeliver/main/update.json"

APP_FILE = "pdfmailDeliver.py"
APP_VERSION_PATTERN = r'APP_VERSION\s*=\s*["\']([^"\']+)["\']'
REQUEST_TIMEOUT = 15
BACKUP_DIR = "_update_backup"


def get_app_path():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def read_local_version(app_path):
    app_file = os.path.join(app_path, APP_FILE)
    if not os.path.exists(app_file):
        return "0.0.0"

    try:
        with open(app_file, "r", encoding="utf-8") as f:
            text = f.read()
    except UnicodeDecodeError:
        with open(app_file, "r", encoding="utf-8-sig") as f:
            text = f.read()

    match = re.search(APP_VERSION_PATTERN, text)
    if match:
        return match.group(1)

    title_match = re.search(r"V(\d+(?:\.\d+)*)", text)
    if title_match:
        return title_match.group(1)

    return "0.0.0"


def version_key(version):
    parts = re.findall(r"\d+|[A-Za-z]+", str(version))
    key = []
    for part in parts:
        if part.isdigit():
            key.append((0, int(part)))
        else:
            key.append((1, part.lower()))
    return key


def is_newer(remote_version, local_version):
    return version_key(remote_version) > version_key(local_version)


def download_text(url):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "pdfmailDeliver-updater",
            "Accept": "application/json,text/plain,*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as response:
        return response.read().decode("utf-8")


def download_file(url, target_path):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "pdfmailDeliver-updater"},
    )
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as response:
        with open(target_path, "wb") as f:
            shutil.copyfileobj(response, f)


def validate_manifest(manifest):
    if not isinstance(manifest, dict):
        raise ValueError("update.json 格式錯誤：最外層必須是物件")
    if not manifest.get("version"):
        raise ValueError("update.json 缺少 version")
    if not isinstance(manifest.get("files"), list) or not manifest["files"]:
        raise ValueError("update.json 缺少 files 清單")

    for item in manifest["files"]:
        if not isinstance(item, dict):
            raise ValueError("files 內每個項目都必須是物件")
        if not item.get("path") or not item.get("url"):
            raise ValueError("files 內每個項目都必須包含 path 與 url")
        normalized = os.path.normpath(item["path"])
        if os.path.isabs(normalized) or normalized.startswith(".."):
            raise ValueError(f"不允許更新資料夾外的檔案：{item['path']}")


def backup_file(app_path, relative_path):
    source = os.path.join(app_path, relative_path)
    if not os.path.exists(source):
        return

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_root = os.path.join(app_path, BACKUP_DIR, stamp)
    backup_path = os.path.join(backup_root, relative_path)
    os.makedirs(os.path.dirname(backup_path), exist_ok=True)
    shutil.copy2(source, backup_path)


def apply_update(app_path, manifest):
    with tempfile.TemporaryDirectory(prefix="pdfmail_update_", dir=app_path) as temp_dir:
        downloaded = []

        for item in manifest["files"]:
            relative_path = os.path.normpath(item["path"])
            temp_path = os.path.join(temp_dir, relative_path)
            os.makedirs(os.path.dirname(temp_path), exist_ok=True)
            print(f"下載更新檔：{relative_path}")
            download_file(item["url"], temp_path)
            downloaded.append((relative_path, temp_path))

        for relative_path, temp_path in downloaded:
            target_path = os.path.join(app_path, relative_path)
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            backup_file(app_path, relative_path)
            os.replace(temp_path, target_path)
            print(f"已更新：{relative_path}")


def check_and_update():
    app_path = get_app_path()
    local_version = read_local_version(app_path)

    if not MANIFEST_URL:
        print("尚未設定 GitHub 更新網址，略過更新檢查。")
        print("請編輯 updater.py 的 MANIFEST_URL，指向 GitHub raw update.json。")
        return 0

    print(f"目前版本：{local_version}")
    print("正在檢查 GitHub 更新...")

    try:
        manifest = json.loads(download_text(MANIFEST_URL))
        validate_manifest(manifest)
        remote_version = str(manifest["version"])

        if not is_newer(remote_version, local_version):
            print(f"已是最新版本：{local_version}")
            return 0

        print(f"發現新版：{remote_version}，開始更新。")
        apply_update(app_path, manifest)
        print("更新完成。")
        return 0
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"更新檢查失敗，將繼續啟動原程式：{exc}")
        return 0
    except Exception as exc:
        print(f"更新失敗，將繼續啟動原程式：{exc}")
        return 0


if __name__ == "__main__":
    raise SystemExit(check_and_update())
