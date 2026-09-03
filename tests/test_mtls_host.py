"""Host mTLS fingerprint checks (no board required)."""
from __future__ import annotations

import ssl
import sys
from pathlib import Path
from unittest import mock

import pytest

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

from mcxn_lib.mtls import FingerprintError, der_sha256, wrap_client  # noqa: E402


def test_fingerprint_mismatch_raises():
    cfg = {
        "mtls": {
            "ca_cert": "ca.crt",
            "client_cert": "c.crt",
            "client_key": "c.key",
        }
    }
    unit = {"mtls_server_cert_sha256": "ab" * 32}

    class FakeSsl:
        def getpeercert(self, binary_form=False):
            return b"not-the-server-cert"

        def close(self):
            pass

    class FakeCtx:
        def wrap_socket(self, sock, server_hostname=None):
            return FakeSsl()

    with mock.patch("mcxn_lib.mtls.load_client_ctx", return_value=FakeCtx()):
        with pytest.raises(FingerprintError):
            wrap_client(mock.Mock(), cfg, unit)


def test_der_sha256_stable():
    assert der_sha256(b"abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
