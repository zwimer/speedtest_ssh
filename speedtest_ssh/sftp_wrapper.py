from collections.abc import Generator
from contextlib import contextmanager
from typing import TYPE_CHECKING
from logging import getLogger
from pathlib import Path
import dataclasses

from paramiko.config import SSHConfig, SSHConfigDict
from paramiko import SSHClient

from .config import Config

if TYPE_CHECKING:
    from paramiko import SFTPClient, HostKeys


__all__ = ("sftp_wrapper",)


_LOG = "SFTPWrapper"


def create_paramiko_config(raw: Config) -> dict:
    """
    Create a dict for paramiko to use as its config
    :return: A dict containing info needed for paramiko to ssh
    """
    log = getLogger(_LOG)
    config: dict[str, str | int | None] = dataclasses.asdict(raw)
    config["username"] = config.pop("user", None)
    config["hostname"] = config.pop("host").lower()  # type: ignore
    # Loads ssh config
    config_f: Path = Path.home() / ".ssh/config"
    if config_f.exists():
        log.debug("Loading SSH config from: %s", config_f)
        ssh_config: SSHConfig = SSHConfig.from_path(str(config_f))
        global_config: SSHConfigDict = ssh_config.lookup("*")
        host_config: SSHConfigDict = ssh_config.lookup(raw.host)

        def load(cname: str, name: str) -> None:
            if config.get(cname, None) is None:
                value = host_config.get(name, None)
                value = global_config.get(name, None) if value is None else value
                if value is not None:
                    log.debug("  %s: %s", cname, value)
                    config[cname] = value

        load("port", "port")
        load("username", "user")
        load("key_filename", "identityfile")
    # Install fallbacks
    if config.get("port", None) is None:
        log.debug("Assuming port 22")
        config["port"] = 22
    return config


def load_keys(client: SSHClient, host: str, port: int) -> None:
    """
    Load available ssh keys into the ssh client
    """
    log = getLogger(_LOG)
    hosts_f = Path.home() / ".ssh/known_hosts"
    if hosts_f.exists():
        log.debug("Installing known hosts from: %s", hosts_f)
        client.load_host_keys(str(hosts_f))
    keys: HostKeys = client.get_host_keys()
    # Paramiko seems overly strict about ssh keys in a way ssh is not
    log.debug("Relaxing paramiko's knownhosts configuration to align with ssh's")
    for i in (host, host.lower()):
        if i in keys:
            keys[f"[{i}]:{port}"] = keys[i]


@contextmanager
def sftp_wrapper(raw: Config) -> Generator["SFTPClient", None, None]:
    """
    A context manager which yields a conncted SFTPClient
    """
    log = getLogger(_LOG)
    log.debug("Initializing ssh client")
    with SSHClient() as client:
        config: dict[str, str | int | None] = create_paramiko_config(raw)
        load_keys(client, raw.host, config["port"])  # type: ignore
        client.connect(**config)  # type: ignore
        log.debug("Initializing SFTP client")
        with client.open_sftp() as sftp:
            yield sftp
