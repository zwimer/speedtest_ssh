from __future__ import annotations
from tempfile import NamedTemporaryFile as NTF
from pathlib import Path
from math import log
import argparse
import time
import sys
import os

from .data_transfer import Config, DataTransfer, SFTP, Rsync
from ._version import __version__


base_size = 2 * (1024**2)
_password_env_name = "SPEEDTEST_SSH_PASSWORD"


def _iteration(temp: Path, client: DataTransfer, size: int) -> tuple[int, int]:
    """
    Time uploading and downloading a file of size bytes
    :param temp: A temporary file we have ownership of
    :param client: A client used to transfer the data
    :param size: how much data to transfer
    :return: <nanoseconds to upload>, <nanoseconds to download>
    """
    # Create the file to upload; sendfile not always supported so we do this the hard way
    block: int = min(base_size, 1024**2)
    with temp.open("ab") as f:
        done: int = os.fstat(f.fileno()).st_size  # .tell() can be odd in append mode
        with open("/dev/urandom", "rb") as ur:
            while done < size:
                f.write(ur.read(block))
                done += block
        f.truncate(size)
    # Time uploading the file
    client.clean_remote()
    start: int = time.time_ns()
    client.put(temp)
    up: int = time.time_ns() - start
    # Time downloading the file
    temp.unlink()
    start = time.time_ns()
    client.get(temp)
    down: int = time.time_ns() - start
    return up, down


def _print_results(up_ns: int, down_ns: int, size: int) -> None:
    """
    Print the speed test results
    """
    fmt = lambda s: f"{8 * (size/1024**2) / (s/1000**3):.2f} Mbit/s"
    print("\n" + f"Upload Speed: {fmt(up_ns)}" + "\n" + f"Download Speed: {fmt(down_ns)}")


def speedtest_ssh(host: str, num_seconds: int, mode: str, **kwargs: int | str | None) -> None:
    """
    Run speedtest_ssh
    """
    kwargs["password"] = None
    if kwargs.pop("password_env"):
        kwargs["password"] = os.environ.get(_password_env_name, None)
        if kwargs["password"] is None:
            raise RuntimeError(f"{_password_env_name} is not set")
    print("Initializing...")
    with (Rsync if mode == "rsync" else SFTP)(Config(host=host, **kwargs)) as remote:
        with NTF(prefix="speedtest_ssh.", dir="/tmp", delete_on_close=False) as ntf:
            ntf.close()
            temp = Path(ntf.name)
            print("Testing...")
            nano_sec: int = 0
            size: int = base_size
            remaining: int = int(1E9)*num_seconds
            while int(1.5*nano_sec) < remaining-1: # Try to get close to seconds
                size *= 2**(0 if not nano_sec else max(1, int(log(remaining / nano_sec, 2))))
                # ^ Faster than just *=2
                up_t, down_t = _iteration(temp, remote, size)
                nano_sec = up_t + down_t
                remaining -= nano_sec
    _print_results(up_t, down_t, size)


def main(argv: list[str]) -> None:
    """
    speedtest_ssh from arguments
    """
    base: str = os.path.basename(argv[0])
    parser = argparse.ArgumentParser(prog=base)
    parser.add_argument("--version", action="version", version=f"{base} {__version__}")
    parser.add_argument("host", help="The host to speedtest the conection to")
    parser.add_argument("-u", "--user", default=None, help="The user used for ssh")
    parser.add_argument("--password-env", action="store_true",
        help=f"Read password from {_password_env_name} environment variable")
    parser.add_argument("--port", type=int, default=None, help="The port used for ssh")
    parser.add_argument("--num-seconds", type=int, default=20,
        help="An approximate number of seconds of time this test should take")
    parser.add_argument("-m", "--mode", choices=["rsync", "sftp"], default="rsync",
        help="The speedtest method. Defaults to rsync")
    return speedtest_ssh(**vars(parser.parse_args(argv[1:])))


def cli() -> None:
    """
    speedtest_ssh CLI
    """
    main(sys.argv)


if __name__ == "__main__":
    cli()
