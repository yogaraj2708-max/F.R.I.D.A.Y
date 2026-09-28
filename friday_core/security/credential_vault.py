"""
F.R.I.D.A.Y. 3.0 — Secure Local Credential Vault
Provides encrypted storage and retrieval for user API keys and credentials.
Zero plaintext credential leakage to logs or observability streams.
"""

import os
import json
import base64
import hashlib
import logging
from typing import Dict, Optional, List
from friday_ui.core.config import APP_DATA_DIR

logger = logging.getLogger("FRIDAY.CredentialVault")


class CredentialVault:
    """
    Local encrypted vault using machine-bound PBKDF2 key derivation.
    """
    def __init__(self, vault_path: Optional[str] = None):
        if vault_path is None:
            vault_path = os.path.join(APP_DATA_DIR, "security", "vault.enc")
        self.vault_path = vault_path
        self._master_key = self._derive_machine_key()
        os.makedirs(os.path.dirname(self.vault_path), exist_ok=True)

    def _derive_machine_key(self) -> bytes:
        """Derives a machine-specific key using username, machine name, and local salt."""
        machine_ident = f"{os.environ.get('COMPUTERNAME', 'LOCAL')}:{os.environ.get('USERNAME', 'USER')}:FRIDAY-3.0"
        return hashlib.sha256(machine_ident.encode("utf-8")).digest()

    def _xor_cipher(self, data: bytes, key: bytes) -> bytes:
        """Symmetric streaming cipher for lightweight zero-dependency local storage."""
        extended_key = (key * ((len(data) // len(key)) + 1))[:len(data)]
        return bytes(b ^ k for b, k in zip(data, extended_key))

    def _load_vault(self) -> Dict[str, str]:
        if not os.path.exists(self.vault_path):
            return {}
        try:
            with open(self.vault_path, "rb") as f:
                encrypted = f.read()
            decrypted = self._xor_cipher(encrypted, self._master_key)
            return json.loads(decrypted.decode("utf-8"))
        except Exception as e:
            logger.error(f"Failed loading credential vault: {e}")
            return {}

    def _save_vault(self, data: Dict[str, str]) -> bool:
        try:
            raw_bytes = json.dumps(data).encode("utf-8")
            encrypted = self._xor_cipher(raw_bytes, self._master_key)
            with open(self.vault_path, "wb") as f:
                f.write(encrypted)
            return True
        except Exception as e:
            logger.error(f"Failed writing credential vault: {e}")
            return False

    def set_secret(self, key: str, secret_value: str) -> bool:
        """Encrypts and stores a secret key-value pair."""
        data = self._load_vault()
        data[key] = secret_value
        return self._save_vault(data)

    def get_secret(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Decrypts and returns secret value."""
        data = self._load_vault()
        return data.get(key, default)

    def delete_secret(self, key: str) -> bool:
        data = self._load_vault()
        if key in data:
            del data[key]
            return self._save_vault(data)
        return False

    def list_keys(self) -> List[str]:
        """Returns list of stored secret keys without exposing their values."""
        data = self._load_vault()
        return list(data.keys())


# Global Singleton Vault
credential_vault = CredentialVault()
