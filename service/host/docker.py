from __future__ import annotations

from datetime import datetime, timezone
from ipaddress import ip_address, IPv6Address
from pathlib import Path
import re
import shutil
import tempfile

import docker
from docker.api.client import APIClient
from docker.tls import TLSConfig
from docker.utils import parse_repository_tag

from model.host.hosts import ManagedHost
from schema.host.hosts import ManagedHostImageSchema, PullManagedHostImageResultSchema


def docker_client_for_host(host: ManagedHost, *, timeout: int = 60) -> docker.DockerClient:
    tls_config = None
    tls_temp_dir = None
    if host.docker_tls_enabled:
        tls_config, tls_temp_dir = _docker_tls_config_for_host(host)

    try:
        return DirectDockerClient(
            base_url=_docker_base_url(host),
            timeout=timeout,
            tls=tls_config,
            tls_temp_dir=tls_temp_dir,
        )
    except Exception:
        if tls_temp_dir:
            shutil.rmtree(tls_temp_dir, ignore_errors=True)
        raise


class DirectDockerClient(docker.DockerClient):
    def __init__(self, *args, tls_temp_dir: str | None = None, **kwargs):
        self._tls_temp_dir = tls_temp_dir
        self.api = DirectDockerAPIClient(*args, **kwargs)

    def close(self) -> None:
        try:
            self.api.close()
        finally:
            if self._tls_temp_dir:
                shutil.rmtree(self._tls_temp_dir, ignore_errors=True)
                self._tls_temp_dir = None


class DirectDockerAPIClient(APIClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.trust_env = False

    def _retrieve_server_version(self):
        self.trust_env = False
        return super()._retrieve_server_version()


def _docker_base_url(host: ManagedHost) -> str:
    address = ip_address(host.ip_address)
    host_address = f"[{address}]" if isinstance(address, IPv6Address) else str(address)
    return f"tcp://{host_address}:{host.docker_management_port}"


def _docker_tls_config_for_host(host: ManagedHost) -> tuple[TLSConfig, str]:
    if not all((host.docker_client_ca_cert, host.docker_client_cert, host.docker_client_key)):
        raise ValueError("docker TLS CA certificate, client certificate, and client key are required")

    safe_ip = re.sub(r"[^A-Za-z0-9]+", "_", host.ip_address).strip("_") or "host"
    host_id = host.id if host.id is not None else "new"
    temp_dir = tempfile.mkdtemp(prefix=f"z3r0-docker-tls-{host_id}-{safe_ip}-")

    ca_path = Path(temp_dir) / "ca.pem"
    cert_path = Path(temp_dir) / "cert.pem"
    key_path = Path(temp_dir) / "key.pem"
    try:
        ca_path.write_text(host.docker_client_ca_cert, encoding="utf-8")
        cert_path.write_text(host.docker_client_cert, encoding="utf-8")
        key_path.touch(mode=0o600, exist_ok=False)
        key_path.write_text(host.docker_client_key, encoding="utf-8")
        key_path.chmod(0o600)
        return TLSConfig(
            client_cert=(str(cert_path), str(key_path)),
            ca_cert=str(ca_path),
            verify=True,
        ), temp_dir
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def inspect_image_on_host_sync(host: ManagedHost, image_name: str) -> dict:
    client = docker_client_for_host(host)
    try:
        return client.api.inspect_image(image_name)
    finally:
        client.close()


def list_host_images_sync(host: ManagedHost) -> list[ManagedHostImageSchema]:
    client = docker_client_for_host(host)
    try:
        images = client.images.list()
        return [_image_schema(image.attrs) for image in images]
    finally:
        client.close()


def pull_host_images_sync(host: ManagedHost, image_names: list[str]) -> list[PullManagedHostImageResultSchema]:
    client = docker_client_for_host(host, timeout=300)
    try:
        results: list[PullManagedHostImageResultSchema] = []
        for image_name in image_names:
            try:
                repository, tag = parse_repository_tag(image_name)
                client.api.pull(repository, tag=tag)
                results.append(PullManagedHostImageResultSchema(
                    image_name=image_name,
                    success=True,
                    message="pulled",
                ))
            except Exception as exc:
                results.append(PullManagedHostImageResultSchema(
                    image_name=image_name,
                    success=False,
                    message=str(exc) or "pull failed",
                ))
        return results
    finally:
        client.close()


def remove_host_image_sync(host: ManagedHost, image_id: str, force: bool = False) -> None:
    client = docker_client_for_host(host)
    try:
        client.images.remove(image_id, force=force)
    finally:
        client.close()


def _image_schema(attrs: dict) -> ManagedHostImageSchema:
    image_id = str(attrs.get("Id") or "")
    repo_tags = attrs.get("RepoTags") if isinstance(attrs.get("RepoTags"), list) else []
    image_name = next((str(tag) for tag in repo_tags if tag and tag != "<none>:<none>"), "")
    created_at = _parse_docker_datetime(attrs.get("Created"))
    return ManagedHostImageSchema(
        image_name=image_name or image_id.removeprefix("sha256:")[:12],
        image_id=image_id,
        image_hash=image_id.removeprefix("sha256:"),
        image_size=max(int(attrs.get("Size") or 0), 0),
        created_at=created_at,
    )


def _parse_docker_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    normalized = value.rstrip("Z")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed
