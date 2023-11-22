from __future__ import annotations
from tempfile import mkdtemp
from pathlib import Path
import argparse
import shutil
import socket
import shlex
import time
import sys
import os

import paramiko

from . import __version__


_max_sec = 20
_base_size = 16 * (1024**2)


def _ur_file(size: int, d: Path) -> Path:
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


def get_stats(up_ns: int, down_ns: int, size: int) -> tuple[str, str]:
    """
    :return: Up speed, down speed in MBit/s
    """
    speed = lambda s: 8 * (size/1024**2) / (s/1000**3)
    return f"{speed(up_ns):.2f} MBit/s", f"{speed(down_ns):.2f} MBit/s"


def _iteration(local_d: Path, remote_d: str, ftp: paramiko.SFTPClient, size: int) -> tuple[int, int]:
    """
    Time uploading and downloading a file of size bytes
    :return: <nanoseconds to upload>, <nanoseconds to download>
    """
    local = str(local_d / "down")
    remote = str(remote_d / "down")
    print(f"  Testing with size: {size / 1024**2}MB")
    test_f = _ur_file(size, local_d)
    try:
        start: int = time.time_ns()
        ftp.put(str(test_f), remote)
        up: int = time.time_ns() - start
        ftp.get(remote, local)
        down: int = time.time_ns() - start - up
    finally:
        test_f.unlink()
        if Path(local).exists():
            Path(local).unlink()
    return up, down


def speedtest_ssh(host: str, max_seconds: int, **kwargs: str) -> None:
    """
    speedtest_ssh, client shoule be False unless called by this program
    """

    print("Initializing...")
    # Config
    config = dict(kwargs)
    config_f = Path.home() / ".ssh/config"
    if config_f.exists():
        ssh_config = paramiko.config.SSHConfig.from_path(config_f)
        global_config = ssh_config.lookup("*")
        host_config = ssh_config.lookup(host)
        if config.get("port") is None:
            config["port"] = host_config.get("port", 22)
        if config.get("username") is None:
            config["username"] = host_config["user"]
        key = host_config.get("identityfile", None)
        if key is not None:
            config["key_filename"] = key
    # Host keys
    hosts_f = Path.home() / ".ssh/known_hosts"
    client = paramiko.SSHClient()
    if hosts_f.exists():
        client.load_host_keys(hosts_f)
    keys = client.get_host_keys()
    try:
        keys[f"[{host.lower()}]:{config['port']}"] = keys[host.lower()]
    except:
        pass

    print("Connecting...")
    client.connect(host.lower(), **config)

    print("Configuring...")
    # Create remote temp directory
    cmd: str = 'from tempfile import mkdtemp; print(mkdtemp(prefix="/tmp/speedtest_ssh."))'
    stdin, stdout, stderr = client.exec_command(f"python3 -c {shlex.quote(cmd)}", timeout=30)
    stdin.close()
    err = stderr.read()
    stderr.close()
    assert not err, f"Bootstrapping finished with: {err}"
    out = stdout.read()
    assert out, "Temp directory name is empty."
    stdout.close()
    remote_d: str = Path(out.strip().decode())
    ftp = client.open_sftp()
    local_d = Path(mkdtemp(prefix="/tmp/speedtest_ssh."))

    # Iterations
    nano_sec = 0
    size = _base_size
    try:
        print("Testing speed...")
        while nano_sec < (max_seconds*1E9)//4:
            up_t, down_t = _iteration(local_d, remote_d, ftp, size)
            nano_sec = up_t + down_t
            size *= 2
        size /= 2
        ftp.close()
    finally:
        print("Cleaning up...")
        local_d.rmdir()
        stdin, stdout, stderr = client.exec_command(f"rm -rf {shlex.quote(str(remote_d))}", timeout=30)

    up, down = get_stats(up_t, down_t, size)
    print("\n" + f"Upload Speed: {up}" + "\n" + f"Download Speed: {down}")


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
    parser.add_argument("--max_seconds", type=int, default=30, help="A soft limit for how many seconds to spend uploading / downloading")
    return speedtest_ssh(**vars(parser.parse_args(argv[1:])))


def cli() -> None:
    """
    speedtest_ssh CLI
    """
    main(sys.argv)


if __name__ == "__main__":
    cli()
