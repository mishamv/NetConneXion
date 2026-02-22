"""GitHub Releases auto-update checker and downloader.

No dependencies on old infrastructure layers.
"""

from __future__ import annotations

import json
import logging
import re
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional
from urllib.request import urlopen, Request
from urllib.error import URLError

logger = logging.getLogger(__name__)

__version__ = "3.0.0"

GITHUB_OWNER = "your-org"
GITHUB_REPO = "Quick-IP-change"


@dataclass
class ReleaseInfo:
    tag: str
    version: str
    name: str
    body: str
    html_url: str
    download_url: Optional[str]
    published_at: str


class GitHubUpdater:
    """Checks GitHub Releases for a newer version and optionally downloads it."""

    def __init__(
        self,
        current_version: str = __version__,
        owner: str = GITHUB_OWNER,
        repo: str = GITHUB_REPO,
    ) -> None:
        self._current = self._parse_version(current_version)
        self._api_url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
        self._latest: Optional[ReleaseInfo] = None

    # ── Public API ────────────────────────────────────────────────

    def check_sync(self) -> Optional[ReleaseInfo]:
        try:
            req = Request(self._api_url, headers={"Accept": "application/vnd.github+json"})
            with urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
        except (URLError, json.JSONDecodeError, OSError) as exc:
            logger.warning("Update check failed: %s", exc)
            return None

        tag = data.get("tag_name", "")
        remote_ver = self._parse_version(tag)
        if remote_ver <= self._current:
            return None

        download_url: Optional[str] = None
        for asset in data.get("assets", []):
            if asset.get("name", "").lower().endswith((".exe", ".zip")):
                download_url = asset.get("browser_download_url")
                break

        info = ReleaseInfo(
            tag=tag,
            version=tag.lstrip("vV").strip(),
            name=data.get("name", tag),
            body=data.get("body", ""),
            html_url=data.get("html_url", ""),
            download_url=download_url,
            published_at=data.get("published_at", ""),
        )
        self._latest = info
        logger.info("New version available: %s", info.version)
        return info

    def check_async(
        self, on_result: Optional[Callable[[Optional[ReleaseInfo]], None]] = None
    ) -> None:
        def _worker() -> None:
            result = self.check_sync()
            if on_result:
                on_result(result)
        threading.Thread(target=_worker, daemon=True, name="update-check").start()

    def download(
        self,
        release: Optional[ReleaseInfo] = None,
        dest_dir: Optional[str] = None,
        on_progress: Optional[Callable[[int, int], None]] = None,
    ) -> Optional[str]:
        rel = release or self._latest
        if rel is None or rel.download_url is None:
            return None
        dest = Path(dest_dir) if dest_dir else Path(tempfile.gettempdir())
        dest.mkdir(parents=True, exist_ok=True)
        filename = rel.download_url.rsplit("/", 1)[-1]
        filepath = dest / filename
        try:
            req = Request(rel.download_url)
            with urlopen(req, timeout=60) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                downloaded = 0
                with open(filepath, "wb") as f:
                    while True:
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if on_progress and total:
                            on_progress(downloaded, total)
            return str(filepath)
        except (URLError, OSError) as exc:
            logger.error("Download failed: %s", exc)
            return None

    def download_async(
        self,
        release: Optional[ReleaseInfo] = None,
        dest_dir: Optional[str] = None,
        on_progress: Optional[Callable[[int, int], None]] = None,
        on_done: Optional[Callable[[Optional[str]], None]] = None,
    ) -> None:
        def _worker() -> None:
            path = self.download(release, dest_dir, on_progress)
            if on_done:
                on_done(path)
        threading.Thread(target=_worker, daemon=True, name="update-download").start()

    @staticmethod
    def _parse_version(tag: str) -> tuple:
        nums = re.findall(r"\d+", tag)
        return tuple(int(n) for n in nums) if nums else (0,)
