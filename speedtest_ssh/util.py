from pathlib import Path
from shutil import which
import subprocess
import shlex
import os


__all__ = ("find_exe", "run_cmd")


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


def run_cmd(cmd: Path, *args: str | Path, verbose: bool, **kwargs) -> subprocess.CompletedProcess:
    full = (cmd, *args)
    if verbose:
        msg = f"{'*'*30} Running Command: {cmd.name} {'*'*30}"
        print(f"{msg}\n{' '.join(shlex.quote(str(i)) for i in full)}\n{'*'*len(msg)}")
    return subprocess.run(full, **kwargs)
