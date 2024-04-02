from __future__ import annotations
from subprocess import CalledProcessError, PIPE
from logging import getLogger, DEBUG, INFO
from typing import TYPE_CHECKING
from datetime import datetime
from pathlib import Path
import random
import string
import re
import os

from tqdm import tqdm

from .sftp_wrapper import sftp_wrapper
from .util import find_exe, run_cmd
from .config import Config

if TYPE_CHECKING:
    from paramiko import SFTPClient


__all__ = ("DataTransfer", "SFTP", "Rsync")


_dict = string.ascii_uppercase + string.ascii_lowercase + string.digits


def _rand_str(size: int) -> str:
    return "".join(random.choice(_dict) for _ in range(size))  # nosec B311


class ProgressBar(tqdm):
    """
    A small tqdm wrapper for paramiko's SFTP callbacks to use
    """

    def __init__(self, desc: str):
        super().__init__(desc=desc, unit="B", unit_scale=True, unit_divisor=1024, dynamic_ncols=True)

    def __call__(self, bytes_done: int, bytes_remaining: int):
        """
        :param bytes_done: The number of bytes transferred
        :param bytes_remaining: The number of bytes yet to be transferred
        """
        self.total: int | None
        if self.total is None:
            self.total = bytes_remaining
        self.update(bytes_done - self.n)


class DataTransfer:
    """
    A context manager used to send and receive data to and from the remote client
    This class is a context manager; on exit will remove the remote file on deletion
    """

    _LOG = "DataTransfer"

    def __init__(self, config: Config):
        """
        :param config: The Config object the DataTransfer instance should use
        """
        self._l = getLogger(self._LOG)
        self._remote_f: str = f"/tmp/speedtest-ssh_{datetime.now()}_{_rand_str(8)}.tmp"
        self._remote_f = self._remote_f.replace(":", "-").replace(" ", "_")
        # We promise that _remote_f components match: ^[a-zA-Z\d_.-]+$ (old rsync args suck)
        self._l.debug("Parsing ssh config and loading keys...")
        self._sftp_cm = sftp_wrapper(config)
        self._sftp: SFTPClient  # Defined in __enter__

    def __enter__(self) -> DataTransfer:
        self._l.debug("Chosen remote file name: %s", self._remote_f)
        self._sftp = self._sftp_cm.__enter__()
        return self

    def __exit__(self, *args, **kwargs):
        self.clean_remote()
        self._l.debug("Terminating SFTP connection...")
        self._sftp_cm.__exit__(*args, **kwargs)

    def put(self, local: Path) -> None:
        """
        Send the local file to be saved at the remote path
        """
        raise NotImplementedError

    def get(self, local: Path) -> None:
        """
        Get the remote file to and save it at the local path
        """
        raise NotImplementedError

    def clean_remote(self) -> None:
        """
        Removes the remote file
        """
        try:
            self._l.debug("Removing remote file (if it exists): %s", self._remote_f)
            self._sftp.remove(self._remote_f)
        except FileNotFoundError:
            pass


class SFTP(DataTransfer):
    """
    A DataTransfer classes that uses SFTP
    """

    def put(self, local: Path) -> None:
        with ProgressBar("Upload   ") as p:
            self._sftp.put(str(local), self._remote_f, callback=p)

    def get(self, local: Path) -> None:
        with ProgressBar("Download ") as p:
            self._sftp.get(self._remote_f, str(local), callback=p)


class Rsync(DataTransfer):
    """
    A DataTransfer that uses rsync
    Requires rsync be installed
    """

    def __init__(self, config: Config):
        """
        :param host: The hostname ssh uses for the remote client
        """
        super().__init__(config)
        self._remote_f = re.sub(r"[^a-zA-Z\d_/-]", "_", self._remote_f)  # Old rsync args suck
        self._rsync = find_exe("rsync")
        # Determine rsync version
        try:
            p = run_cmd(self._rsync, "--version", stdout=PIPE, check=True)
            output = p.stdout.decode().split("version")[1].split("protocol")[0].strip()
            version: tuple[int, ...] = tuple(int(i) for i in output.split("."))
            self._old = version <= (3, 1, 0)  # macOS has an old version by default
            if self._old:
                print("\tOld version of rsync detected. Output will be more verbose.")
            else:
                self._l.debug("Newer version of rsync detected")
        except (CalledProcessError, KeyError) as e:
            raise RuntimeError(f"Could not determine rsync version from {self._rsync}") from e
        # Determine rsync command
        self._flags: list[str | Path] = []
        self._env = os.environ.copy()
        if config.password is not None:
            sshpass = find_exe("sshpass")
            self._flags = [sshpass, "-e"] + self._flags  # type: ignore
            self._env["SSHPASS"] = config.password
        self._flags.extend(("-hh", "--progress" if self._old else "--info=progress2"))
        if self._l.isEnabledFor(INFO):
            self._flags.append("--verbose")
        if self._l.isEnabledFor(DEBUG):
            self._flags.append("-vvv")
        if config.port is not None:
            self._flags.append(f"--port={config.port}")
        # Determine host info
        self._target: str = ("" if config.user is None else f"{config.user}@") + f"{config.host}:{self._remote_f}"

    def _transfer(self, src: str | Path, dst: str | Path) -> None:
        """
        :param src: The file to rsync to dst
        :param dst: The location to rsync src to
        """
        try:
            _ = run_cmd(self._rsync, *self._flags, src, dst, env=self._env, check=True)
        except CalledProcessError as e:
            raise RuntimeError("Failed to transfer data during speed test") from e

    def put(self, local: Path) -> None:
        self._transfer(local, self._target)

    def get(self, local: Path) -> None:
        self._transfer(self._target, local)
