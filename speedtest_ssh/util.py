from logging import getLogger, DEBUG
from pathlib import Path
from shutil import which
import subprocess
import shlex
import os


__all__ = ("find_exe", "run_cmd")


_LOG = "Util"


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


def _log_cmd(cmd: Path, args: tuple[str | Path, ...]) -> None:
    log = getLogger(_LOG)
    if log.isEnabledFor(DEBUG):
        full = (cmd, *args)
        msg = f"{'*'*30} Running Command: {cmd.name} {'*'*30}"
        msg = f"{msg}\n{' '.join(shlex.quote(str(i)) for i in full)}\n{'*'*len(msg)}"
        log.debug(msg)


def run_cmd(cmd: Path, *args: str | Path, **kwargs) -> subprocess.CompletedProcess:
    """
    :param cmd: The command to run
    :param args: The arguments of cmd
    :param kwargs: Fowarded to subprocess.Popen
    :return: Completed process
    """
    _log_cmd(cmd, args)
    return subprocess.run((cmd, *args), **kwargs)  # nosec B603


def tee_cmd(cmd: Path, *args: str | Path, level: int, **kwargs) -> tuple[subprocess.Popen, str]:
    """
    :param cmd: The command to run (and info log the output of)
    :param args: The arguments of cmd
    :param level: The log level to use
    :param kwargs: Fowarded to subprocess.Popen aside from test and stdout
    :return: Completed process, stdout (do not read stdout from CompletedProcess)
    """
    assert "text" not in kwargs  # nosec B101
    assert "stdout" not in kwargs  # nosec B101
    log = getLogger(_LOG)
    _log_cmd(cmd, args)
    p = subprocess.Popen((cmd, *args), text=True, stdout=subprocess.PIPE, **kwargs)  # nosec B603
    stdout = ""
    for line in p.stdout:  # type: ignore
        log.log(level, line[:-1])
        stdout += line
    return p, stdout
