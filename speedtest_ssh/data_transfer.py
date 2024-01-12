from __future__ import annotations
from typing import TYPE_CHECKING
from datetime import datetime
from pathlib import Path
import subprocess
import random
import string
import shlex
import re
import os

from tqdm import tqdm

from .sftp_wrapper import sftp_wrapper
from .config import Config
from .util import find_exe

if TYPE_CHECKING:
    from paramiko import SFTPClient


__all__ = ("DataTransfer", "SFTP", "Rsync")


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
    A context mananger used to send and receive data to and from the remote client
    This class is a context manager; on exit will remove the remote file on deletion
    """

    def __init__(self, config: Config, verbose: bool):
        """
        :param config: The Config object the DataTransfer instance should use
        :param verbose: If true, be more verbose
        """
        self._verbose = verbose
        rand = lambda: random.choice(string.ascii_uppercase + string.ascii_lowercase + string.digits)
        self._remote_f: str = f"/tmp/speedtest-ssh_{datetime.now()}_{''.join(rand() for _ in range(8))}.tmp"
        self._remote_f = self._remote_f.replace(":", "-").replace(" ", "_")
        # We promise that _remote_f components match: ^[a-zA-Z\d_.-]+$ (old rsync args suck)
        if self._verbose:
            print("Parsing ssh config and loading keys...")
        self._sftp_cm = sftp_wrapper(config)
        self._sftp: SFTPClient  # Defined in __enter__

    def __enter__(self) -> DataTransfer:
        if self._verbose:
            print("Establishing SFTP connection...")
        self._sftp = self._sftp_cm.__enter__()
        return self

    def __exit__(self, *args, **kwargs):
        self.clean_remote()
        if self._verbose:
            print("Terminating SFTP connection...")
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
            if self._verbose:
                print(f"Removing remote file (if it exists): {self._remote_f}")
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

    def __init__(self, config: Config, verbose: bool):
        """
        :param host: The hostname ssh uses for the remote client
        :param verbose: If true, be more verbose
        """
        super().__init__(config, verbose)
        self._remote_f = re.sub("[^a-zA-Z\\d_-]", "_", self._remote_f)  # Old rsync args suck
        self._rsync = find_exe("rsync")
        # Determine rsync version
        try:
            output: str = self._run(self._rsync, "--version", stdout=subprocess.PIPE, check=True).stdout.decode()
            output = output.split("version")[1].split("protocol")[0].strip()
            version: tuple[int, ...] = tuple(int(i) for i in output.split("."))
            self._old = version <= (3, 1, 0)  # macOS has an old version by default
            if self._old:
                print("\tOld version of rsync detected. Output will be more verbose.")
        except (subprocess.CalledProcessError, KeyError) as e:
            raise RuntimeError(f"Could not determine rsync version from {self._rsync}") from e
        # Determine rsync command
        self._flags: list[str | Path] = []
        self._env = os.environ.copy()
        if config.password is not None:
            sshpass = find_exe("sshpass")
            self._flags = [sshpass, "-e"] + self._flags  # type: ignore
            self._env["SSHPASS"] = config.password
        self._flags.extend(("-hh", "--progress" if self._old else "--info=progress2"))
        if self._verbose:
            self._flags.extend(["--verbose", "-vvv"])
        if config.port is not None:
            self._flags.append(f"--port={config.port}")
        # Determine host info
        self._target: str = ("" if config.user is None else f"{config.user}@") + f"{config.host}:{self._remote_f}"

    def _run(self, cmd: Path, *args: str | Path, **kwargs) -> subprocess.CompletedProcess:
        full = (cmd, *args)
        if self._verbose:
            msg = f"{'*'*30} Running Command: {cmd.name} {'*'*30}"
            print(f"{msg}\n{' '.join(shlex.quote(str(i)) for i in full)}\n{'*'*len(msg)}")
        return subprocess.run(full, **kwargs)

    def _transfer(self, src: str | Path, dst: str | Path) -> None:
        """
        :param src: The file to rsync to dst
        :param dst: The location to rsync src to
        """
        try:
            _ = self._run(self._rsync, *self._flags, src, dst, env=self._env, check=True)
        except subprocess.CalledProcessError as e:
            raise RuntimeError("Failed to transfer data during speed test") from e

    def put(self, local: Path) -> None:
        self._transfer(local, self._target)

    def get(self, local: Path) -> None:
        self._transfer(self._target, local)
