from __future__ import annotations

import asyncio
import fcntl
import inspect
import os
import pty
import signal
import struct
import termios
import time
from dataclasses import dataclass, field
from typing import Any

from model.host.hosts import ManagedHost
from service.host.hosts import DEFAULT_LOCAL_HOST_ID, query_managed_host_by_id


_DEFAULT_SHELL_ROWS = 24
_DEFAULT_SHELL_COLS = 80
_SSH_CONNECT_TIMEOUT_SECONDS = 10


@dataclass
class HostShellSession:
    connection: Any
    process: Any
    closed: bool = False

    def shutdown(self) -> None:
        if self.closed:
            return
        self.process.close()

    async def close(self) -> None:
        if self.closed:
            return
        self.closed = True

        try:
            self.process.close()
            await self.process.wait_closed()
        finally:
            self.connection.close()
            await self.connection.wait_closed()


@dataclass
class LocalShellSession:
    master_fd: int
    pid: int
    closed: bool = False
    _fd_closed: bool = field(default=False, repr=False)

    def shutdown(self) -> None:
        if self._fd_closed:
            return
        self._fd_closed = True
        try:
            os.close(self.master_fd)
        except OSError:
            pass

    async def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self.shutdown()
        await asyncio.get_running_loop().run_in_executor(None, self._reap_child)

    def _reap_child(self) -> None:
        try:
            pid, _ = os.waitpid(self.pid, os.WNOHANG)
            if pid != 0:
                return
        except ChildProcessError:
            return

        try:
            os.kill(self.pid, signal.SIGTERM)
        except ProcessLookupError:
            return

        for _ in range(10):
            try:
                pid, _ = os.waitpid(self.pid, os.WNOHANG)
                if pid != 0:
                    return
            except ChildProcessError:
                return
            time.sleep(0.05)

        try:
            os.kill(self.pid, signal.SIGKILL)
            os.waitpid(self.pid, 0)
        except (ChildProcessError, ProcessLookupError):
            pass


ShellSession = HostShellSession | LocalShellSession


def _is_local_host(host: ManagedHost) -> bool:
    return host.id == DEFAULT_LOCAL_HOST_ID


async def resolve_shell_host(id: int) -> ManagedHost | None:
    return await query_managed_host_by_id(id)


async def open_host_shell(
    host: ManagedHost,
    rows: int = _DEFAULT_SHELL_ROWS,
    cols: int = _DEFAULT_SHELL_COLS,
) -> ShellSession:
    if _is_local_host(host):
        return await _open_local_shell(rows, cols)
    return await _open_ssh_shell(host, rows, cols)


async def _open_local_shell(rows: int, cols: int) -> LocalShellSession:
    master_fd, slave_fd = pty.openpty()
    _set_terminal_size(master_fd, rows, cols)

    pid = os.fork()
    if pid == 0:
        os.setsid()
        os.close(master_fd)

        fcntl.ioctl(slave_fd, termios.TIOCSCTTY, 0)
        os.dup2(slave_fd, 0)
        os.dup2(slave_fd, 1)
        os.dup2(slave_fd, 2)
        if slave_fd > 2:
            os.close(slave_fd)

        shell = os.environ.get("SHELL", "/bin/bash")
        os.execvpe(shell, [shell, "-l"], os.environ)

    os.close(slave_fd)
    return LocalShellSession(master_fd=master_fd, pid=pid)


async def _open_ssh_shell(
    host: ManagedHost,
    rows: int,
    cols: int,
) -> HostShellSession:
    try:
        import asyncssh
    except ImportError as exc:
        raise RuntimeError("asyncssh is required for remote host shell access") from exc

    connection = await asyncssh.connect(
        host.ip_address,
        port=host.ssh_port,
        username=host.host_account,
        password=host.host_password,
        known_hosts=None,
        connect_timeout=_SSH_CONNECT_TIMEOUT_SECONDS,
    )
    try:
        process = await connection.create_process(
            request_pty=True,
            term_type="xterm-256color",
            term_size=(cols, rows),
            encoding=None,
        )
    except Exception:
        connection.close()
        await connection.wait_closed()
        raise
    return HostShellSession(connection=connection, process=process)


async def resize_host_shell(session: ShellSession, rows: int, cols: int) -> None:
    rows = max(1, min(rows, 300))
    cols = max(1, min(cols, 500))
    if isinstance(session, LocalShellSession):
        _set_terminal_size(session.master_fd, rows, cols)
    else:
        session.process.change_terminal_size(cols, rows)


async def read_host_shell(session: ShellSession) -> bytes:
    if isinstance(session, LocalShellSession):
        return await _read_local_shell(session)
    return await _read_ssh_shell(session)


async def write_host_shell(session: ShellSession, data: str) -> None:
    if not data:
        return
    if isinstance(session, LocalShellSession):
        await _write_local_shell(session, data)
    else:
        await _write_ssh_shell(session, data)


async def _read_local_shell(session: LocalShellSession) -> bytes:
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(None, _read_master_fd, session.master_fd)
    except (OSError, ValueError):
        return b""


def _read_master_fd(fd: int) -> bytes:
    try:
        return os.read(fd, 4096)
    except OSError:
        return b""


async def _write_local_shell(session: LocalShellSession, data: str) -> None:
    payload = data.encode()
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _write_master_fd, session.master_fd, payload)


def _write_master_fd(fd: int, data: bytes) -> None:
    while data:
        try:
            written = os.write(fd, data)
            data = data[written:]
        except OSError:
            break


async def _read_ssh_shell(session: HostShellSession) -> bytes:
    try:
        data = await session.process.stdout.read(4096)
    except (OSError, ValueError, asyncio.CancelledError):
        return b""
    if isinstance(data, str):
        return data.encode()
    return data or b""


async def _write_ssh_shell(session: HostShellSession, data: str) -> None:
    payload = data.encode()
    session.process.stdin.write(payload)
    drain = getattr(session.process.stdin, "drain", None)
    if callable(drain):
        result = drain()
        if inspect.isawaitable(result):
            await result


def _set_terminal_size(fd: int, rows: int, cols: int) -> None:
    winsize = struct.pack("HHHH", rows, cols, 0, 0)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)
