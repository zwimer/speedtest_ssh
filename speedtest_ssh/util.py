from pathlib import Path
from shutil import which
import os


def find_exe(name: str) -> Path:
    """
    :param name: The name of the executable to find
    :return: The path to the executable
    """
    where: str | None = which(name)
    if where is None:
        raise RuntimeError(f"Cannot find {name} executable")
    exe: Path = Path(where).resolve()
    if not os.access(exe, os.X_OK):
        raise RuntimeError(f"Cannot find valid {name} executable")
    return exe
