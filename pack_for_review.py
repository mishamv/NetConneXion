"""pack_for_review.py — собирает исходный код проекта в ZIP для анализа.

Включает: quickip/, tests/, данные конфигурации (pyproject.toml, requirements*.txt и т.д.)
Исключает: .venv/, __pycache__/, .git/, .ruff_cache/, .pytest_cache/, *.pyc

Запуск:
    python pack_for_review.py
    python pack_for_review.py --out review.zip
"""

import argparse
import zipfile
from pathlib import Path
from datetime import datetime

# ── Что включаем ──────────────────────────────────────────────────────────────

INCLUDE_DIRS = [
    "quickip",
    "tests",
    "data",
]

INCLUDE_ROOT_FILES = [
    "pyproject.toml",
    "requirements.txt",
    "requirements-dev.txt",
    "setup.cfg",
    "setup.py",
    "README.md",
    "CHANGELOG.md",
    ".github/workflows/ci.yml",
]

# ── Что исключаем ──────────────────────────────────────────────────────────────

EXCLUDE_DIRS = {
    ".venv", "venv", "__pycache__",
    ".git", ".ruff_cache", ".pytest_cache",
    "node_modules", "dist", "build", ".mypy_cache",
}

EXCLUDE_EXTENSIONS = {".pyc", ".pyo", ".pyd", ".so", ".dll", ".exe", ".egg-info"}

EXCLUDE_FILES = {"pack_for_review.py"}


def _should_exclude(path: Path) -> bool:
    # Любой компонент пути из чёрного списка → пропустить
    for part in path.parts:
        if part in EXCLUDE_DIRS:
            return True
    if path.suffix in EXCLUDE_EXTENSIONS:
        return True
    if path.name in EXCLUDE_FILES:
        return True
    return False


def collect_files(root: Path) -> list[Path]:
    files: list[Path] = []

    # Файлы из директорий
    for d in INCLUDE_DIRS:
        target = root / d
        if not target.exists():
            continue
        for f in sorted(target.rglob("*")):
            if f.is_file() and not _should_exclude(f.relative_to(root)):
                files.append(f)

    # Файлы в корне
    for name in INCLUDE_ROOT_FILES:
        f = root / name
        if f.exists():
            files.append(f)

    return files


def build_zip(root: Path, out_path: Path) -> int:
    files = collect_files(root)
    total_bytes = 0

    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for f in files:
            arcname = f.relative_to(root)
            zf.write(f, arcname)
            total_bytes += f.stat().st_size
            print(f"  + {arcname}")

    return len(files), total_bytes


def main() -> None:
    parser = argparse.ArgumentParser(description="Pack project source for review")
    parser.add_argument(
        "--out", default="",
        help="Output ZIP path (default: netconnexion_review_YYYYMMDD_HHMM.zip)"
    )
    args = parser.parse_args()

    root = Path(__file__).parent.resolve()

    if args.out:
        out_path = Path(args.out)
    else:
        stamp = datetime.now().strftime("%Y%m%d_%H%M")
        out_path = root / f"netconnexion_review_{stamp}.zip"

    print(f"Root   : {root}")
    print(f"Output : {out_path}")
    print()

    count, raw_bytes = build_zip(root, out_path)
    zip_size = out_path.stat().st_size

    print()
    print(f"Упаковано файлов : {count}")
    print(f"Исходный размер  : {raw_bytes:,} байт")
    print(f"Размер архива    : {zip_size:,} байт ({zip_size / 1024:.1f} КБ)")
    print(f"\nГотово: {out_path.name}")


if __name__ == "__main__":
    main()
