from dataclasses import dataclass

import docker

from logger import get_logger
from schema.sandbox.containers import SandboxContainerPortMapping, SandboxContainerStatus
from model.host.hosts import ManagedHost
from service.host.docker import docker_client_for_host


logger = get_logger(__name__)


@dataclass(frozen=True)
class DockerContainerState:
    exists: bool
    status: str = ""


def _to_docker_ports(port_mappings: list[SandboxContainerPortMapping]) -> dict[str, tuple[str, int]] | None:
    if not port_mappings:
        return None
    return {
        f"{mapping.container_port}/{mapping.protocol}": ("0.0.0.0", mapping.host_port)
        for mapping in port_mappings
    }


def create_container_sync(
    host: ManagedHost,
    image_ref: str,
    container_name_prefix: str,
    port_mappings: list[SandboxContainerPortMapping],
    environment: dict[str, str] | None = None,
) -> tuple[str, str]:
    client = docker_client_for_host(host)
    try:
        create_kwargs = {
            "image": image_ref,
            "ports": _to_docker_ports(port_mappings),
            "stdin_open": True,
            "tty": False,
        }
        if environment:
            create_kwargs["environment"] = environment

        container = client.containers.create(
            **create_kwargs,
        )
        container_name = f"{container_name_prefix}-{container.id[:12]}"
        try:
            container.rename(container_name)
        except Exception:
            container.remove(force=True)
            raise
        return container.id, container_name
    finally:
        client.close()


def inspect_container_state_sync(host: ManagedHost, container_hash: str) -> DockerContainerState:
    client = docker_client_for_host(host)
    try:
        container = client.containers.get(container_hash)
        container.reload()
        return DockerContainerState(exists=True, status=str(container.status or ""))
    except docker.errors.NotFound:
        return DockerContainerState(exists=False)
    finally:
        client.close()


def start_container_sync(host: ManagedHost, container_hash: str) -> None:
    client = docker_client_for_host(host)
    try:
        container = client.containers.get(container_hash)
        container.start()
    finally:
        client.close()


def stop_container_sync(host: ManagedHost, container_hash: str) -> None:
    client = docker_client_for_host(host)
    try:
        container = client.containers.get(container_hash)
        container.stop()
    finally:
        client.close()


def remove_container_sync(host: ManagedHost, container_hash: str) -> None:
    client = docker_client_for_host(host)
    try:
        container = client.containers.get(container_hash)
        container.remove(force=True)
    except docker.errors.NotFound:
        logger.debug("sandbox container instance already absent: %s", container_hash)
    finally:
        client.close()


def docker_status_to_sandbox_status(status: str) -> SandboxContainerStatus:
    normalized = status.strip().lower()
    if normalized == "running":
        return SandboxContainerStatus.RUNNING
    if normalized == "created":
        return SandboxContainerStatus.CREATED
    if normalized == "exited":
        return SandboxContainerStatus.STOPPED
    return SandboxContainerStatus.ERROR
