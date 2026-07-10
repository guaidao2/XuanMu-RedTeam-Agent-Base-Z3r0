from dataclasses import dataclass

from model.egress_proxy.proxies import EgressProxy
from model.sandbox.containers import SandboxContainer
from schema.sandbox.containers import SandboxContainerEgressMode
from service.egress_proxy.proxies import egress_proxy_upstream


NO_PROXY_VALUE = "localhost,127.0.0.1,::1"
LOCAL_EGRESS_PROXY_URL = "http://127.0.0.1:8118"
EGRESS_UPSTREAM_TYPE_ENV = "SANDBOX_EGRESS_UPSTREAM_TYPE"
EGRESS_UPSTREAM_ADDR_ENV = "SANDBOX_EGRESS_UPSTREAM_ADDR"


@dataclass(frozen=True)
class SandboxEgressSelection:
    mode: SandboxContainerEgressMode
    proxy: EgressProxy | None = None


def sandbox_runtime_proxy_environment() -> dict[str, str]:
    return {
        "HTTP_PROXY": LOCAL_EGRESS_PROXY_URL,
        "http_proxy": LOCAL_EGRESS_PROXY_URL,
        "HTTPS_PROXY": LOCAL_EGRESS_PROXY_URL,
        "https_proxy": LOCAL_EGRESS_PROXY_URL,
        "ALL_PROXY": LOCAL_EGRESS_PROXY_URL,
        "all_proxy": LOCAL_EGRESS_PROXY_URL,
        "NO_PROXY": NO_PROXY_VALUE,
        "no_proxy": NO_PROXY_VALUE,
    }


def sandbox_egress_upstream_environment(selection: SandboxEgressSelection) -> dict[str, str]:
    if selection.mode == SandboxContainerEgressMode.DIRECT:
        return {
            EGRESS_UPSTREAM_TYPE_ENV: "",
            EGRESS_UPSTREAM_ADDR_ENV: "",
        }
    if selection.mode == SandboxContainerEgressMode.TOR:
        return {
            EGRESS_UPSTREAM_TYPE_ENV: SandboxContainerEgressMode.TOR.value,
            EGRESS_UPSTREAM_ADDR_ENV: "",
        }
    if selection.proxy is None:
        raise ValueError("managed proxy is required for proxy egress mode")
    return {
        EGRESS_UPSTREAM_TYPE_ENV: selection.proxy.proxy_type.value,
        EGRESS_UPSTREAM_ADDR_ENV: egress_proxy_upstream(selection.proxy),
    }


def sandbox_egress_container_environment(selection: SandboxEgressSelection) -> dict[str, str]:
    return {
        **sandbox_runtime_proxy_environment(),
        **sandbox_egress_upstream_environment(selection),
    }


def sandbox_egress_label(container: SandboxContainer, proxy: EgressProxy | None) -> str:
    if container.egress_mode == SandboxContainerEgressMode.DIRECT:
        return SandboxContainerEgressMode.DIRECT.value
    if container.egress_mode == SandboxContainerEgressMode.TOR:
        return SandboxContainerEgressMode.TOR.value
    if proxy is None:
        return ""
    return f"{proxy.proxy_type.value}://{proxy.proxy_host}:{proxy.proxy_port}"
