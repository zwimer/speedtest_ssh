from subprocess import CalledProcessError
from logging import INFO
from sys import platform

from .util import find_exe, tee_cmd


__all__ = ("PingFailed", "ping")


_LOG = "Ping"


class PingFailed(RuntimeError):
    """
    Raise on ping failure
    """


def ping(host: str, n_pings: int = 10, max_wait: int = 3) -> float:
    """
    :param host: The host to ping
    :return: The number Ping host
    """
    # We use subprocess b/c ping is suid and we don't want to require root
    print("Pinging...")
    exe = find_exe("ping")
    try:
        wait: str = f"-W{max_wait*1000}" if platform == "darwin" else f"-w{max_wait}"
        p, stdout = tee_cmd(exe, "-i.1", f"-c{n_pings}", wait, host, level=INFO)
        if p.returncode:
            raise PingFailed(f"{exe} exit code: {p.returncode}")
        output: str = stdout.strip()
    except CalledProcessError as e:
        raise PingFailed("Unkown error") from e
    try:
        return float(output.split("/")[-3])
    except IndexError as e:
        raise PingFailed("Bad output", output) from e
