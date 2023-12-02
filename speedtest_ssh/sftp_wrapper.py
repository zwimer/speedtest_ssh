from typing import TYPE_CHECKING, Generator
from contextlib import contextmanager
from pathlib import Path
import dataclasses

from paramiko.config import SSHConfig, SSHConfigDict
from paramiko import SSHClient

from .config import Config

if TYPE_CHECKING:
    from paramiko import SFTPClient, HostKeys


__all__ = ("sftp_wrapper",)


def create_paramiko_config(raw: Config) -> dict:
    """
    Create a dict for paramiko to use as its config
    :return: A dict containing info needed for paramiko to ssh
    """
    config: dict[str, str | int | None] = dataclasses.asdict(raw)
    config["username"] = config.pop("user", None)
    config["hostname"] = config.pop("host").lower()
    # Loads ssh config
    config_f: Path = Path.home() / ".ssh/config"
    if config_f.exists():
        ssh_config: SSHConfig = SSHConfig.from_path(config_f)
        global_config: SSHConfigDict = ssh_config.lookup("*")
        host_config: SSHConfigDict = ssh_config.lookup(raw.host)
        def load(cname: str, name: str) -> None:
            if config.get(cname, None) is None:
                value = host_config.get(name, None)
                value = global_config.get(name, None) if value is None else value
                if value is not None:
                    config[cname] = value
        load("port", "port")
        load("username", "user")
        load("key_filename", "identityfile")
    # Install fallbacks
    if config.get("port", None) is None:
        config["port"] = 22
    return config


def load_keys(client: SSHClient, host: str, port: int) -> None:
    """
    Load available ssh keys into the ssh client
    """
    hosts_f = Path.home() / ".ssh/known_hosts"
    if hosts_f.exists():
        client.load_host_keys(hosts_f)
    keys: HostKeys = client.get_host_keys()
    # Paramiko seems overly strict about ssh keys in a way ssh is not
    for i in (host, host.lower()):
        if i in keys:
            keys[f"[{i}]:{port}"] = keys[i]


@contextmanager
def sftp_wrapper(raw: Config) -> Generator["SFTPClient", None, None]:
    """
    A context manager which yields a conncted SFTPClient
    """
    with SSHClient() as client:
        config: dict[str, str | int | None] = create_paramiko_config(raw)
        load_keys(client, raw.host, config["port"])
        client.connect(**config)
        with client.open_sftp() as sftp:
            yield sftp
