"""Exceptions for the OBS Studio integration."""

from __future__ import annotations


class OBSError(Exception):
    """Base exception for OBS integration errors."""


class OBSConnectionError(OBSError):
    """Raised when the OBS WebSocket cannot be reached."""


class OBSAuthError(OBSError):
    """Raised when OBS WebSocket authentication fails."""


class OBSRequestError(OBSError):
    """Raised when an OBS WebSocket request returns an error."""


class OBSSSHError(OBSError):
    """Raised when the SSH tunnel fails."""
