from dataclasses import dataclass
from datetime import datetime
import asyncio
import base64
import socket
import ssl
from time import perf_counter
from urllib.parse import quote, urlsplit

from sqlalchemy import String, cast, or_
from sqlmodel import select

from database import get_async_session
from model.egress_proxy.proxies import EgressProxy
from model.sandbox.containers import SandboxContainer
from schema.egress_proxy.proxies import EgressProxyType
from schema.sandbox.containers import SandboxContainerEgressMode
from service.common.pagination import Page, paginate_statement


EGRESS_PROXY_TEST_URL = "https://www.gstatic.com/generate_204"
EGRESS_PROXY_TEST_TIMEOUT_SECONDS = 8.0


@dataclass(frozen=True)
class DeleteEgressProxyResult:
    deleted: bool
    not_found: bool = False
    message: str = ""


@dataclass(frozen=True)
class UpdateEgressProxyResult:
    proxy: EgressProxy | None
    not_found: bool = False
    message: str = ""


@dataclass(frozen=True)
class TestEgressProxyResult:
    id: int
    success: bool
    status_code: int | None
    elapsed_ms: int
    message: str
    not_found: bool = False


async def create_egress_proxy(
    proxy_type: EgressProxyType,
    proxy_host: str,
    proxy_port: int,
    proxy_account: str = "",
    proxy_password: str = "",
) -> EgressProxy:
    now = datetime.now()
    proxy = EgressProxy(
        proxy_type=proxy_type,
        proxy_host=proxy_host,
        proxy_port=proxy_port,
        proxy_account=proxy_account,
        proxy_password=proxy_password,
        created_at=now,
        updated_at=now,
    )

    async with get_async_session() as session:
        session.add(proxy)
        await session.commit()
        await session.refresh(proxy)
    return proxy


async def update_egress_proxy(
    id: int,
    proxy_type: EgressProxyType | None = None,
    proxy_host: str | None = None,
    proxy_port: int | None = None,
    proxy_account: str | None = None,
    proxy_password: str | None = None,
) -> UpdateEgressProxyResult:
    async with get_async_session() as session:
        proxy = await session.get(EgressProxy, id)
        if proxy is None:
            return UpdateEgressProxyResult(proxy=None, not_found=True, message="egress proxy not found")

        if proxy_type is not None:
            proxy.proxy_type = proxy_type
        if proxy_host is not None:
            proxy.proxy_host = proxy_host
        if proxy_port is not None:
            proxy.proxy_port = proxy_port
        if proxy_account is not None:
            proxy.proxy_account = proxy_account
        if proxy_password is not None:
            proxy.proxy_password = proxy_password

        proxy.updated_at = datetime.now()
        session.add(proxy)
        await session.commit()
        await session.refresh(proxy)
        return UpdateEgressProxyResult(proxy=proxy)


async def delete_egress_proxy(id: int) -> DeleteEgressProxyResult:
    async with get_async_session() as session:
        proxy = await session.get(EgressProxy, id)
        if proxy is None:
            return DeleteEgressProxyResult(deleted=False, not_found=True, message="egress proxy not found")
        if await _egress_proxy_has_sandbox_containers(session, id):
            return DeleteEgressProxyResult(
                deleted=False,
                message="egress proxy is used by sandbox containers",
            )

        await session.delete(proxy)
        await session.commit()
        return DeleteEgressProxyResult(deleted=True)


async def query_egress_proxies(page: int = 1, size: int = 100, keyword: str = "") -> Page[EgressProxy]:
    statement = select(EgressProxy).order_by(EgressProxy.id)

    keyword = keyword.strip()
    if keyword:
        pattern = f"%{keyword}%"
        statement = statement.where(
            or_(
                EgressProxy.proxy_host.ilike(pattern),
                EgressProxy.proxy_account.ilike(pattern),
                cast(EgressProxy.proxy_type, String).ilike(pattern),
                cast(EgressProxy.proxy_port, String).ilike(pattern),
            )
        )

    return await paginate_statement(statement, page=page, size=size)


async def query_egress_proxy_by_id(id: int) -> EgressProxy | None:
    async with get_async_session() as session:
        return await session.get(EgressProxy, id)


async def test_egress_proxy(id: int) -> TestEgressProxyResult:
    proxy = await query_egress_proxy_by_id(id)
    if proxy is None:
        return TestEgressProxyResult(
            id=id,
            success=False,
            status_code=None,
            elapsed_ms=0,
            message="egress proxy not found",
            not_found=True,
        )

    started = perf_counter()
    try:
        status_code = await _test_proxy_connectivity(proxy)
    except (OSError, TimeoutError, ValueError) as exc:
        return TestEgressProxyResult(
            id=id,
            success=False,
            status_code=None,
            elapsed_ms=int((perf_counter() - started) * 1000),
            message=f"proxy test failed: {exc}",
        )

    elapsed_ms = int((perf_counter() - started) * 1000)
    success = 200 <= status_code < 400
    return TestEgressProxyResult(
        id=id,
        success=success,
        status_code=status_code,
        elapsed_ms=elapsed_ms,
        message="proxy test succeeded" if success else f"proxy test returned HTTP {status_code}",
    )


def egress_proxy_upstream(proxy: EgressProxy) -> str:
    auth = ""
    if proxy.proxy_account:
        account = quote(proxy.proxy_account, safe="")
        password = quote(proxy.proxy_password, safe="")
        auth = f"{account}:{password}@"
    return f"{auth}{proxy.proxy_host}:{proxy.proxy_port}"


async def _egress_proxy_has_sandbox_containers(session, proxy_id: int) -> bool:
    result = await session.exec(
        select(SandboxContainer.id)
        .where(SandboxContainer.egress_mode == SandboxContainerEgressMode.PROXY)
        .where(SandboxContainer.egress_proxy_id == proxy_id)
        .limit(1)
    )
    return result.first() is not None


async def _test_proxy_connectivity(proxy: EgressProxy) -> int:
    return await asyncio.to_thread(_test_proxy_connectivity_sync, proxy)


def _test_proxy_connectivity_sync(proxy: EgressProxy) -> int:
    target = urlsplit(EGRESS_PROXY_TEST_URL)
    if target.scheme != "https" or not target.hostname:
        raise ValueError("proxy test URL must be https")
    target_host = target.hostname
    target_port = target.port or 443
    target_addr = f"{target_host}:{target_port}"
    path = target.path or "/"
    if target.query:
        path += f"?{target.query}"

    if proxy.proxy_type == EgressProxyType.SOCKS5:
        sock = _connect_socks5_proxy(proxy, target_host, target_port)
    elif proxy.proxy_type in {EgressProxyType.HTTP, EgressProxyType.HTTPS}:
        sock = _connect_http_proxy(proxy, target_addr)
    else:
        raise ValueError(f"unsupported proxy type: {proxy.proxy_type.value}")

    try:
        with ssl.create_default_context().wrap_socket(sock, server_hostname=target_host) as tls_sock:
            request = (
                f"GET {path} HTTP/1.1\r\n"
                f"Host: {target_host}\r\n"
                "Connection: close\r\n"
                "User-Agent: Z3r0-Proxy-Test/1.0\r\n"
                "\r\n"
            )
            tls_sock.sendall(request.encode("ascii"))
            return _read_http_response_status(tls_sock)
    finally:
        sock.close()


def _connect_http_proxy(proxy: EgressProxy, target_addr: str) -> socket.socket:
    raw_sock = socket.create_connection(
        (proxy.proxy_host, proxy.proxy_port),
        timeout=EGRESS_PROXY_TEST_TIMEOUT_SECONDS,
    )
    raw_sock.settimeout(EGRESS_PROXY_TEST_TIMEOUT_SECONDS)
    sock: socket.socket | ssl.SSLSocket = raw_sock
    if proxy.proxy_type == EgressProxyType.HTTPS:
        try:
            sock = ssl.create_default_context().wrap_socket(raw_sock, server_hostname=proxy.proxy_host)
        except Exception:
            raw_sock.close()
            raise

    try:
        headers = [
            f"CONNECT {target_addr} HTTP/1.1",
            f"Host: {target_addr}",
            "Proxy-Connection: close",
        ]
        auth = _proxy_authorization_header(proxy)
        if auth:
            headers.append(f"Proxy-Authorization: {auth}")
        sock.sendall(("\r\n".join(headers) + "\r\n\r\n").encode("ascii"))
        status_code = _read_http_response_status(sock)
        if status_code < 200 or status_code > 299:
            raise OSError(f"http proxy CONNECT returned HTTP {status_code}")
        return sock
    except Exception:
        sock.close()
        raise


def _connect_socks5_proxy(proxy: EgressProxy, target_host: str, target_port: int) -> socket.socket:
    sock = socket.create_connection(
        (proxy.proxy_host, proxy.proxy_port),
        timeout=EGRESS_PROXY_TEST_TIMEOUT_SECONDS,
    )
    sock.settimeout(EGRESS_PROXY_TEST_TIMEOUT_SECONDS)
    try:
        methods = b"\x00"
        if proxy.proxy_account:
            methods = b"\x00\x02"
        sock.sendall(bytes([0x05, len(methods)]) + methods)
        reply = _read_exact(sock, 2)
        if reply[0] != 0x05 or reply[1] == 0xFF:
            raise OSError("socks5 method rejected")
        if reply[1] == 0x02:
            user = proxy.proxy_account.encode("utf-8")
            password = proxy.proxy_password.encode("utf-8")
            if len(user) > 255 or len(password) > 255:
                raise ValueError("socks5 credentials too long")
            sock.sendall(bytes([0x01, len(user)]) + user + bytes([len(password)]) + password)
            auth_reply = _read_exact(sock, 2)
            if len(auth_reply) != 2 or auth_reply[1] != 0:
                raise OSError("socks5 authentication failed")
        elif reply[1] != 0x00:
            raise OSError(f"unsupported socks5 authentication method: {reply[1]}")

        host_bytes = target_host.encode("idna")
        if len(host_bytes) > 255:
            raise ValueError("target host too long")
        request = (
            b"\x05\x01\x00\x03"
            + bytes([len(host_bytes)])
            + host_bytes
            + target_port.to_bytes(2, "big")
        )
        sock.sendall(request)
        head = _read_exact(sock, 4)
        if head[1] != 0:
            raise OSError(f"socks5 connect failed: {head[1]}")
        if head[3] == 0x01:
            _read_exact(sock, 4)
        elif head[3] == 0x03:
            length = _read_exact(sock, 1)[0]
            _read_exact(sock, length)
        elif head[3] == 0x04:
            _read_exact(sock, 16)
        else:
            raise OSError(f"invalid socks5 address type: {head[3]}")
        _read_exact(sock, 2)
        return sock
    except Exception:
        sock.close()
        raise


def _proxy_authorization_header(proxy: EgressProxy) -> str:
    if not proxy.proxy_account:
        return ""
    token = base64.b64encode(f"{proxy.proxy_account}:{proxy.proxy_password}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def _read_exact(sock: socket.socket, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining > 0:
        chunk = sock.recv(remaining)
        if not chunk:
            raise OSError("connection closed while reading proxy response")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _read_http_response_status(sock: socket.socket) -> int:
    data = bytearray()
    while b"\r\n\r\n" not in data:
        chunk = sock.recv(1024)
        if not chunk:
            raise OSError("connection closed before HTTP response headers")
        data.extend(chunk)
        if len(data) > 65536:
            raise OSError("HTTP response headers are too large")
    line = bytes(data).split(b"\r\n", 1)[0].decode("iso-8859-1")
    parts = line.split(" ", 2)
    if len(parts) < 2 or not parts[1].isdigit():
        raise OSError(f"invalid HTTP status line: {line}")
    return int(parts[1])
