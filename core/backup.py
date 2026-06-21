from __future__ import annotations

from datetime import datetime
from pathlib import Path
import zipfile


def create_backup(config_path: Path, overrides_dir: Path, output_dir: Path) -> Path:
    """config.json + overrides/ 폴더를 zip으로 압축합니다.

    Args:
        config_path: config.json 경로
        overrides_dir: overrides/ 디렉터리 경로
        output_dir: 백업 zip을 저장할 디렉터리

    Returns:
        생성된 zip 파일 경로
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_name = f"planner_backup_{timestamp}.zip"
    zip_path = output_dir / zip_name

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        if config_path.exists():
            zf.write(config_path, arcname="config.json")

        if overrides_dir.exists() and overrides_dir.is_dir():
            for override_file in overrides_dir.iterdir():
                if override_file.is_file() and override_file.suffix == ".json":
                    zf.write(override_file, arcname=f"overrides/{override_file.name}")

    return zip_path


def list_backups(output_dir: Path) -> list[Path]:
    """planner_backup_*.zip 파일을 mtime 최신순으로 반환합니다.

    Args:
        output_dir: 백업 zip이 저장된 디렉터리

    Returns:
        zip 파일 경로 목록 (최신순)
    """
    if not output_dir.exists():
        return []

    backups = list(output_dir.glob("planner_backup_*.zip"))
    backups.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return backups
