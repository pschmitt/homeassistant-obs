"""SSH port-forwarding tunnel for OBS WebSocket access."""

from __future__ import annotations

import asyncio
import logging

import asyncssh

from .exceptions import OBSSSHError

_LOGGER = logging.getLogger(__name__)


def _build_known_hosts(known_hosts_content: str | None):
    """Return an asyncssh known_hosts value from user-supplied content.

    Returns None when the content is empty (skip host-key verification).
    """
    if not known_hosts_content or not known_hosts_content.strip():
        return None
    try:
        return asyncssh.import_known_hosts(known_hosts_content.strip())
    except Exception as err:
        raise OBSSSHError(f"Invalid known_hosts content: {err}") from err


def _build_client_keys(key_path: str | None, key_content: str | None) -> list:
    """Return client keys for asyncssh from either a path or inline content."""
    if key_content and key_content.strip():
        try:
            return [asyncssh.import_private_key(key_content.strip())]
        except Exception as err:
            raise OBSSSHError(f"Invalid SSH private key: {err}") from err
    if key_path and key_path.strip():
        return [key_path.strip()]
    return []


class OBSSSHTunnel:
    """Persistent SSH tunnel that forwards a remote OBS WebSocket port locally.

    Lifecycle:
        1. Call async_start() once to establish the SSH connection and begin
           forwarding. The local port assigned by the OS is available via the
           local_port property.
        2. Call async_ensure_alive() before each OBS request; it restarts the
           tunnel transparently if the SSH connection has dropped.
        3. Call async_stop() when the integration unloads.
    """

    def __init__(
        self,
        ssh_host: str,
        ssh_port: int,
        ssh_username: str,
        ssh_key_path: str | None,
        obs_remote_host: str,
        obs_remote_port: int,
        ssh_key_content: str | None = None,
        ssh_known_hosts: str | None = None,
    ) -> None:
        self._ssh_host = ssh_host
        self._ssh_port = ssh_port
        self._ssh_username = ssh_username
        self._ssh_key_path = ssh_key_path
        self._ssh_key_content = ssh_key_content
        self._ssh_known_hosts = ssh_known_hosts
        self._obs_remote_host = obs_remote_host
        self._obs_remote_port = obs_remote_port

        self._conn: asyncssh.SSHClientConnection | None = None
        self._listener: asyncssh.SSHListener | None = None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @property
    def local_port(self) -> int | None:
        """Return the local port the tunnel is listening on, or None."""
        if self._listener is None:
            return None
        try:
            return self._listener.get_port()
        except Exception:
            return None

    @property
    def is_alive(self) -> bool:
        """Return True when the SSH connection is up and forwarding."""
        return (
            self._conn is not None
            and not self._conn.is_closed()
            and self._listener is not None
        )

    async def async_start(self) -> int:
        """Establish the SSH tunnel and return the assigned local port."""
        await self.async_stop()
        try:
            client_keys = _build_client_keys(self._ssh_key_path, self._ssh_key_content)
            known_hosts = _build_known_hosts(self._ssh_known_hosts)
            self._conn = await asyncssh.connect(
                self._ssh_host,
                port=self._ssh_port,
                username=self._ssh_username,
                client_keys=client_keys if client_keys else None,
                known_hosts=known_hosts,
            )
            self._listener = await self._conn.forward_local_port(
                "127.0.0.1",
                0,  # OS assigns an available port
                self._obs_remote_host,
                self._obs_remote_port,
            )
            port = self._listener.get_port()
            _LOGGER.debug(
                "SSH tunnel active: 127.0.0.1:%s → %s:%s (via %s)",
                port,
                self._obs_remote_host,
                self._obs_remote_port,
                self._ssh_host,
            )
            return port
        except OBSSSHError:
            await self.async_stop()
            raise
        except (asyncssh.Error, OSError, ValueError) as err:
            await self.async_stop()
            raise OBSSSHError(
                f"Failed to establish SSH tunnel to {self._ssh_host}: {err}"
            ) from err

    async def async_stop(self) -> None:
        """Tear down the SSH connection and tunnel."""
        if self._listener is not None:
            try:
                self._listener.close()
            except Exception:
                pass
            self._listener = None

        if self._conn is not None:
            try:
                self._conn.close()
                await asyncio.wait_for(self._conn.wait_closed(), timeout=5)
            except Exception:
                pass
            self._conn = None

    async def async_ensure_alive(self) -> int:
        """Restart the tunnel if the SSH connection has dropped.

        Returns the current local port (which may change after a restart).
        """
        if not self.is_alive:
            _LOGGER.info(
                "SSH tunnel to %s is down – reconnecting…", self._ssh_host
            )
            return await self.async_start()
        return self.local_port  # type: ignore[return-value]
