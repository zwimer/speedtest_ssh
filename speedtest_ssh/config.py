from dataclasses import dataclass


@dataclass(kw_only=True)
class Config:
    """
    A simple config dataclass that holds information used to access a remote client
    """
    host: str
    user: str | None
    password: str | None
    port: int | None
