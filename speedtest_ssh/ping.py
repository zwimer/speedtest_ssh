from typing import TYPE_CHECKING
from sys import platform
import subprocess

if TYPE_CHECKING:
    from pathlib import Path

from .util import find_exe


class PingFailed(RuntimeError):
    """
    Raise on ping failure
    """


def ping(host: str, verbose: bool, n_pings: int = 10, max_wait: int = 3) -> float:
    """
    :param host: The host to ping
    :return: The number Ping host
    """
    # We use subprocess b/c ping is suid and we don't want to require root
    print("Pinging...")
    cmd: tuple[Path | str, ...] = (
        find_exe("ping"),
        "-i.1",
        f"-c{n_pings}",
        ("-W" if platform == "darwin" else "-w") + str(max_wait),
        *([] if verbose else ["-q"]),
        host,
    )
    try:
        output: str = subprocess.check_output(cmd).decode().strip()
    except subprocess.CalledProcessError as e:
        raise PingFailed("Non-zero exit code") from e
    if verbose:
        print(output)
    try:
        return float(output.split("/")[-3])
    except IndexError:
        raise PingFailed("Bad output", output)
