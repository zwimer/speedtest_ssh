from pathlib import Path
import subprocess
import shutil

from tqdm import tqdm
import paramiko


__all__ = ("DataTransfer", "SFTP", "Rsync")


class _ProgressBar(tqdm):
    """
    A small tqdm wrapper for paramiko's SFTP callbacks to use
    """

    def __init__(self, desc: str):
        super().__init__(
            desc=desc,
            unit=" B",
            unit_scale=True,
            unit_divisor=1024,
            leave=False,
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
    A class used to send and receive data to and from the remote client
    """

    def put(self, local: Path, remote: Path) -> None:
        """
        Send the local file to be saved at the remote path
        """
        raise NotImplementedError

    def get(self, remote: Path, local: Path) -> None:
        """
        Get the remote file to and save it at the local path
        """
        raise NotImplementedError


class SFTP(DataTransfer):
    """
    A DataTransfer classes that uses SFTP
    """

    def __init__(self, sftp: paramiko.SFTPClient):
        """
        :param sftp: An existing sftp client to use
        """
        self._sftp: paramiko.SFTPClient = sftp

    def put(self, local: Path, remote: Path) -> None:
        with _ProgressBar("Upload") as p:
            self._sftp.put(str(local), str(remote), callback=p)

    def get(self, remote: Path, local: Path) -> None:
        with _ProgressBar("Upload") as p:
            self._sftp.get(str(remote), str(local), callback=p)


class Rsync(DataTransfer):
    """
    A DataTransfer that uses rsync
    Requires rsync be installed
    """

    def __init__(self, host: str):
        """
        :param host: The hostname ssh uses for the remote client
        """
        self._host: str = host
        rsync: str | None = shutil.which("rsync")
        if rsync is None:
            raise RuntimeError("Cannot find rsync executable")
        self._rsync = Path(rsync).resolve()
        if not self._rsync.exists():
            raise RuntimeError("Cannot find valid rsync executable")
        # Determine rsync version
        try:
            output: str = subprocess.check_output((self._rsync, "--version")).decode()
            output = output.split("version")[1].split("protocol")[0].strip()
            version: tuple[int,...] = tuple(int(i) for i in output.split("."))
            self._old = version <= (3, 1, 0)  # macOS has an old version by default
            if self._old:
                print("\tOld version of rsync detected. Output will be more verbose.")
        except (subprocess.CalledProcessError, KeyError) as e:
            raise RuntimeError(f"Could not determine rsync version from {self._rsync}") from e

    def _transfer(self, src: str | Path, dst: str | Path) -> None:
        """
        rsync src to dst
        """
        try:
            prog: str = "--progress" if self._old else "--info=progress2"
            _ = subprocess.run((self._rsync, prog, "-hh", src, dst), check=True)
        except subprocess.CalledProcessError as e:
            raise RuntimeError("Failed to transfer data during speed test") from e

    def put(self, local: Path, remote: Path) -> None:
        self._transfer(local, f"{self._host}:remote")

    def get(self, remote: Path, local: Path) -> None:
        self._transfer(f"{self._host}:remote", local)
