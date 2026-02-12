"""
Shared helpers for pipeline scripts: safe file iteration, logging.
"""
import logging
from pathlib import Path


def project_root() -> Path:
    """Project root (parent of scripts/)."""
    return Path(__file__).resolve().parent.parent


def iter_pdf_files(folder: Path | str) -> list[Path]:
    """
    Safely list all .pdf files in folder. Returns [] if folder missing or empty.
    """
    folder = Path(folder)
    if not folder.is_dir():
        return []
    return sorted(folder.glob("*.pdf"))


def iter_txt_files(folder: Path | str) -> list[Path]:
    """
    Safely list all .txt files in folder. Returns [] if folder missing or empty.
    """
    folder = Path(folder)
    if not folder.is_dir():
        return []
    return sorted(folder.glob("*.txt"))


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """Logger with console handler."""
    log = logging.getLogger(name)
    if not log.handlers:
        log.setLevel(level)
        h = logging.StreamHandler()
        h.setLevel(level)
        log.addHandler(h)
    return log
