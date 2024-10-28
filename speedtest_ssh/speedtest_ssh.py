from logging import getLogger, basicConfig, WARNING, DEBUG, INFO
from tempfile import NamedTemporaryFile as NTF
from dataclasses import fields
from pathlib import Path
import argparse
import math
import time
import os

import argcomplete

from .config import Config
from .data_transfer import DataTransfer, SFTP, Rsync
from .ping import ping as ping_test
from ._version import __version__


base_size = 2 * (1024**2)
_password_env_name = "SPEEDTEST_SSH_PASSWORD"  # nosec B105
_LOG_VERBOSITY: dict[int, int] = {0: WARNING, 1: INFO, 2: DEBUG}
_LOG = "speedtest_ssh"


def _iteration(temp: Path, client: DataTransfer, size: int) -> tuple[int, int]:
    """
    Time uploading and downloading a file of size bytes
    :param temp: A temporary file we have ownership of
    :param client: A client used to transfer the data
    :param size: how much data to transfer
    :return: <nanoseconds to upload>, <nanoseconds to download>
    """
    # Create the file to upload; sendfile not always supported so we do this the hard way
    log = getLogger(_LOG)
    log.debug("Filling %s with %s MiB from /dev/urandom... ", temp, size / 2**20)
    block: int = min(base_size, 1024**2)
    with temp.open("ab") as f:
        done: int = os.fstat(f.fileno()).st_size  # .tell() can be odd in append mode
        with Path("/dev/urandom").open("rb") as ur:
            while done < size:
                f.write(ur.read(block))
                done += block
        f.truncate(size)
    # Time uploading the file
    log.debug("Starting upload test")
    client.clean_remote()
    start: int = time.time_ns()
    client.put(temp)
    up: int = time.time_ns() - start
    # Time downloading the file
    log.debug("Time taken: %s ns\nStarting download test", up)
    temp.unlink()
    start = time.time_ns()
    client.get(temp)
    down: int = time.time_ns() - start
    log.debug("Time taken: %s ns\n", down)
    return up, down


def _print_results(ping_delay: float | None, up_ns: int, down_ns: int, size: int) -> None:
    """
    Print the speed test results
    """
    prefix = "\n" + ("" if ping_delay is None else f"Ping: {ping_delay} ms\n")
    fmt = lambda s: f"{8 * (size/1024**2) / (s/1000**3):.2f} Mbit/s"
    print(f"{prefix}Upload Speed: {fmt(up_ns)}\nDownload Speed: {fmt(down_ns)}")


def speedtest_ssh(seconds: int, ping: bool, mode: str, conf: Config) -> None:
    """
    Run speedtest_ssh
    """
    log = getLogger(_LOG)
    ping_delay: float | None = ping_test(conf.host) if ping else None
    print("Connecting...")
    with (Rsync if mode == "rsync" else SFTP)(conf) as remote:
        with NTF(prefix="speedtest_ssh.", dir="/tmp", delete_on_close=False) as ntf:
            ntf.close()
            temp = Path(ntf.name)
            log.debug("Created temporary file: %s", temp)
            print("Testing...")
            nano_sec: int = 0
            size: int = base_size
            remaining: int = int(1e9) * seconds
            while int(1.5 * nano_sec) < remaining - 1:  # Try to get close to seconds
                size *= 2 ** (0 if not nano_sec else max(1, int(math.log(remaining / nano_sec, 2))))
                # ^ Faster than just *=2
                up_t, down_t = _iteration(temp, remote, size)
                nano_sec = up_t + down_t
                remaining -= nano_sec
    log.debug(f"\n{'*'*30} Final Results {'*'*30}")
    _print_results(ping_delay, up_t, down_t, size)


def cli() -> None:
    """
    speedtest_ssh main
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("-V", "--version", action="version", version=f"{parser.prog} {__version__}")
    remote = parser.add_argument_group("SSH Options")
    remote.add_argument("host", help="The host to speedtest the conection to")
    remote.add_argument("-u", "--user", help="The user used for ssh")
    remote.add_argument("-p", "--port", type=int, help="The port used for ssh")
    remote.add_argument(
        "-E",
        "--password-env",
        action="store_true",
        help=f"Read password from {_password_env_name} environment variable",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase Log verbosity, pass more than once to increase verbosity",
    )
    modes = parser.add_argument_group("SpeedTest Options")
    modes.add_argument("-P", "--ping", action="store_true", help="Ping test the host as well")
    modes.add_argument(
        "-s", "--seconds", type=int, default=20, help="An approximate number of seconds the speed tests should take"
    )
    modes.add_argument(
        "-m", "--mode", choices=["rsync", "sftp"], default="sftp", help="The speedtest method. Defaults to rsync"
    )
    argcomplete.autocomplete(parser)  # Tab completion
    ns = vars(parser.parse_args())
    # Configure logging
    lvl = ns.pop("verbose")
    lvl = _LOG_VERBOSITY[max(i for i in _LOG_VERBOSITY if i <= lvl)]
    basicConfig(level=lvl, format="%(levelname)-8s %(message)s")
    getLogger("main").debug("Log level set to %d", lvl)
    # Call speedtest
    ns["password"] = None
    if ns.pop("password_env"):
        ns["password"] = os.environ.get(_password_env_name, None)
        if ns["password"] is None:
            raise RuntimeError(f"{_password_env_name} is not set")
    conf = Config(**{i.name: ns.pop(i.name) for i in fields(Config)})  # type: ignore
    speedtest_ssh(**ns, conf=conf)  # type: ignore
