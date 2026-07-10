from dataclasses import dataclass
from typing import Literal

from model.sandbox.containers import SandboxContainer


SandboxContainerProtocol = Literal["tcp", "udp"]


@dataclass(frozen=True)
class SandboxContainerRecord:
    container: SandboxContainer
    image_name: str
    supports_tor: bool
    control_proxy_port: int
    owner_username: str
    host_ip_address: str
    egress_label: str = ""


@dataclass(frozen=True)
class SandboxContainerMutationResult:
    record: SandboxContainerRecord | None
    succeeded: bool
    message: str = ""
    not_found: bool = False


@dataclass(frozen=True)
class SandboxContainerCommandResult:
    output: str
    exit_code: int


@dataclass(frozen=True)
class SandboxContainerToolBinding:
    id: int
    generation: int
