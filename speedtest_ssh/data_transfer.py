from typing import TYPE_CHECKING
from pathlib import Path
import subprocess
import random
import shutil
import string
import os

from tqdm import tqdm

from .sftp_wrapper import sftp_wrapper
from .config import Config

if TYPE_CHECKING:
    from paramiko import SFTPClient


__all__ = ("DataTransfer", "SFTP", "Rsync")


class ProgressBar(tqdm):
    """
    A small tqdm wrapper for paramiko's SFTP callbacks to use
    """

    def __init__(self, desc: str):
        super().__init__(
            desc=desc,
            unit=" B",
            unit_scale=True,
            unit_divisor=1024,
            dynamic_ncols=True
        )

    def __call__(self, bytes_done: int, bytes_remaining: int):
        """
        :param bytes_done: The number of bytes transferred
        :param bytes_remaining: The number of bytes yet to be transferred
        """
        if self.total is None:
            self.total = bytes_remaining
        self.update(bytes_done - self.n)


class DataTransfer:
    """
    A context mananger used to send and receive data to and from the remote client
    This class is a context manager; on exit will remove the remote file on deletion
    """
    def __init__(self, config: Config):
        """
        :param config: The Config object the DataTransfer instance should use
        """
        alphabet: str = string.ascii_uppercase + string.ascii_lowercase + string.digits
        self._remote_f: str = "/tmp/speedtest_ssh." + "".join(random.choice(alphabet) for _ in range(8))
        self._sftp_cm = sftp_wrapper(config)
        self._sftp: SFTPClient  # Defined in __enter__

    def __enter__(self) -> "DataTransfer":
        self._sftp = self._sftp_cm.__enter__()
        return self

    def __exit__(self, *args, **kwargs):
        self.clean_remote()
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
        where: str | None = shutil.which("rsync")
        if where is None:
            raise RuntimeError("Cannot find rsync executable")
        rsync: Path = Path(where).resolve()
        if not rsync.exists():
            raise RuntimeError("Cannot find valid rsync executable")
        # Determine rsync version
        try:
            output: str = subprocess.check_output((rsync, "--version")).decode()
            output = output.split("version")[1].split("protocol")[0].strip()
            version: tuple[int,...] = tuple(int(i) for i in output.split("."))
            self._old = version <= (3, 1, 0)  # macOS has an old version by default
            if self._old:
                print("\tOld version of rsync detected. Output will be more verbose.")
        except (subprocess.CalledProcessError, KeyError) as e:
            raise RuntimeError(f"Could not determine rsync version from {rsync}") from e
        # Determine rsync command
        self._cmd: list[str | Path] = [rsync]
        self._env = os.environ.copy()
        if config.password is not None:
            where = shutil.which("sshpass")
            if where is None:
                raise RuntimeError("Cannot pass password to rsync without sshpass installed")
            sshpass: Path = Path(where).resolve()
            if not sshpass.exists():
                raise RuntimeError("Cannot pass password to rsync without valid sshpass installed")
            self._cmd = [sshpass, "-e"] + self._cmd
            self._env["SSHPASS"] = config.password
        self._cmd.extend(("-hh", "--progress" if self._old else "--info=progress2"))
        if config.port is not None:
            self._cmd.append(f"--port={config.port}")
        # Determine host info
        self._target: str = ("" if config.user is None else f"{config.user}@") + f"{config.host}:{self._remote_f}"

    def _transfer(self, src: str | Path, dst: str | Path) -> None:
        """
        rsync src to dst
        """
        try:
            _ = subprocess.run((*self._cmd, src, dst), env=self._env, check=True)
        except subprocess.CalledProcessError as e:
            raise RuntimeError("Failed to transfer data during speed test") from e

    def put(self, local: Path) -> None:
        self._transfer(local, self._target)

    def get(self, local: Path) -> None:
        self._transfer(self._target, local)
