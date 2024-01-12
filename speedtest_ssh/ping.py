from subprocess import CalledProcessError, PIPE
from sys import platform

from .util import find_exe, run_cmd


__all__ = ("PingFailed", "ping")


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
    exe = find_exe("ping")
    try:
        wait: str = ("-W" if platform == "darwin" else "-w") + str(max_wait)
        q = [] if verbose else ["-q"]
        p = run_cmd(exe, "-i.1", f"-c{n_pings}", wait, *q, host, verbose=verbose, stdout=PIPE)
        if p.returncode:
            raise PingFailed(f"{exe} exit code: {p.returncode}")
        output: str = p.stdout.decode().strip()
    except CalledProcessError as e:
        raise PingFailed("Unkown error") from e
    if verbose:
        print(output)
    try:
        return float(output.split("/")[-3])
    except IndexError as e:
        raise PingFailed("Bad output", output) from e
