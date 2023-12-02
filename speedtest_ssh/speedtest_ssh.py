from __future__ import annotations
from tempfile import mkdtemp
from pathlib import Path
from math import log
import argparse
import shlex
import time
import sys
import os

import paramiko

from .data_transfer import DataTransfer, SFTP, Rsync
from ._version import __version__


_base_size = 2 * (1024**2)
_ssh_timeout = 10


def _load_config(host: str, default: dict[str, int | str | None]) -> dict:
    """
    :param default: A starting dict to build off of
    :return: A dict containing info needed for paramiko to ssh
    """
    config = dict(default)
    config_f = Path.home() / ".ssh/config"
    if config_f.exists():
        ssh_config = paramiko.config.SSHConfig.from_path(config_f)
        global_config: paramiko.config.SSHConfigDict = ssh_config.lookup("*")
        host_config: paramiko.config.SSHConfigDict = ssh_config.lookup(host)
        def load(cname: str, name: str) -> None:
            if config.get(cname, None) is None:
                value = host_config.get(name, None)
                value = global_config.get(name, None) if value is None else value
                if value is not None:
                    config[cname] = value
        load("port", "port")
        load("username", "user")
        load("key_filename", "identityfile")
    if config.get("port", None) is None:
        config["port"] = 22
    return config


def _load_keys(client: paramiko.SSHClient, host: str, port: int) -> None:
    """
    Load available ssh keys into the ssh client
    """
    hosts_f = Path.home() / ".ssh/known_hosts"
    if hosts_f.exists():
        client.load_host_keys(hosts_f)
    keys: paramiko.HostKeys = client.get_host_keys()
    try:
        keys[f"[{host.lower()}]:{port}"] = keys[host.lower()]
    except KeyError:
        pass


def _mkdtemp_remote(client: paramiko.SSHClient) -> Path:
    """
    :return: A path to a temp directory on the remote client
    """
    cmd: str = shlex.quote('from tempfile import mkdtemp; print(mkdtemp(prefix="/tmp/speedtest_ssh."))')
    stdin, stdout, stderr = client.exec_command(f"python3 -c {cmd}", timeout=_ssh_timeout)
    stdin.close()
    err: bytes = stderr.read()
    stderr.close()
    if err:
        raise RuntimeError(f"Bootstrapping finished with: {err!r}")
    out: bytes = stdout.read()
    if not out:
        raise RuntimeError("Temp directory name is empty.")
    stdout.close()
    return Path(out.strip().decode())


def _ur_file(size: int, d: Path) -> Path:
    """
    Create a file in directory d of that is size bytes large
    :return: The path to the newly created file
    """
    # sendfile not always supported so we do this the hard way
    done = 0
    block = _base_size
    ret = d / str(size)
    with ret.open("wb") as f:
        with open("/dev/urandom", "rb") as ur:
            with ret.open("wb") as f:
                while done < size:
                    f.write(ur.read(block))
                    done += block
    return ret


def _iteration(local_d: Path, remote_d: Path, dt: DataTransfer, size: int) -> tuple[int, int]:
    """
    Time uploading and downloading a file of size bytes
    :return: <nanoseconds to upload>, <nanoseconds to download>
    """
    local: Path = local_d / "down"
    remote: Path = remote_d / "down"
    test_f: Path = _ur_file(size, local_d)
    try:
        start: int = time.time_ns()
        dt.put(test_f, remote)
        up: int = time.time_ns() - start
        dt.get(remote, local)
        down: int = time.time_ns() - start - up
    finally:
        test_f.unlink()
        if Path(local).exists():
            Path(local).unlink()
    return up, down


def _print_results(up_ns: int, down_ns: int, size: int) -> None:
    """
    Print the speed test results
    """
    fmt = lambda s: f"{8 * (size/1024**2) / (s/1000**3):.2f} Mbit/s"
    print("\n" + f"Upload Speed: {fmt(up_ns)}" + "\n" + f"Download Speed: {fmt(down_ns)}")


def _rm_rf_remote(client: paramiko.SSHClient, d: Path) -> None:
    """
    Remotely run: rm -rf on d
    """
    try:
        stdin, stdout, stderr = client.exec_command("rm -rf {shlex.quote(cmd)}", timeout=_ssh_timeout)
        stdin.close()
        stdout.close()
        stderr.close()
    except Exception as e:
        raise RuntimeError(f"Failed to clean up, please remove {d} from the host manually") from e


def speedtest_ssh(host: str, num_seconds: int, mode: str, **kwargs: int | str | None) -> None:
    """
    speedtest_ssh, client shoule be False unless called by this program
    """
    print("Initializing...")
    config = _load_config(host, kwargs)
    client = paramiko.SSHClient()
    _load_keys(client, host, config["port"])

    print("Connecting...")
    client.connect(host.lower(), **config)

    print("Configuring...")
    sftp: paramiko.SFTPClient = client.open_sftp()
    dt: DataTransfer = Rsync(host) if mode == "rsync" else SFTP(sftp)
    local_d = Path(mkdtemp(prefix="/tmp/speedtest_ssh."))
    remote_d: Path = _mkdtemp_remote(client)

    # Iterations
    print("Testing...")
    nano_sec: int = 0
    size: int = _base_size
    try:
        remaining: int = int(1E9)*num_seconds
        while int(1.5*nano_sec) < remaining-1:
            size *= 2**(0 if not nano_sec else max(1, int(log(remaining / nano_sec, 2))))  # Faster than just *=2
            up_t, down_t = _iteration(local_d, remote_d, dt, size)
            nano_sec = up_t + down_t
            remaining -= nano_sec
        sftp.close()
    finally:
        print("Cleaning up...")
        local_d.rmdir()
        try:
            _rm_rf_remote(client, remote_d)
        except RuntimeError as e:
            print(f"Error: {e}")  # Not really much we can do but warn about it

    # Print results
    _print_results(up_t, down_t, size)


def main(argv: list[str]) -> None:
    """
    speedtest_ssh from arguments
    """
    base: str = os.path.basename(argv[0])
    parser = argparse.ArgumentParser(prog=base)
    parser.add_argument("--version", action="version", version=f"{base} {__version__}")
    parser.add_argument("host", help="The host to speedtest the conection to")
    parser.add_argument("-u", "--username", default=None, help="The username to use to ssh")
    parser.add_argument("--password", default=None, help="The password to use to ssh")
    parser.add_argument("--port", type=int, default=None, help="The port to use to ssh")
    parser.add_argument("--num_seconds", type=int, default=20, help="An approximate amount of time this test should take")
    parser.add_argument("-m", "--mode", choices=["rsync", "sftp"], default="rsync", help="The speedtest method. Defaults to rsync")
    return speedtest_ssh(**vars(parser.parse_args(argv[1:])))


def cli() -> None:
    """
    speedtest_ssh CLI
    """
    main(sys.argv)


if __name__ == "__main__":
    cli()
