"""
licensing.py
------------
Feature gating for premium features.

Supports three modes:
  1. License key (env: ABAQUS_AGENT_LICENSE_KEY or ~/.abaqus_agent_license)
  2. Feature flags (env: ABAQUS_AGENT_FEATURES="coupling,parametric,...")
  3. Programmatic enable/disable (for testing)
"""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path

from tools.errors import AbaqusAgentError, ErrorCode


# All premium features and their display names
PREMIUM_FEATURES = {
    "coupling":     "Multi-Physics Coupling",
    "adaptivity":   "Automatic Mesh Adaptivity",
    "parametric":   "Batch Parametric Sweeps",
    "geometry_ext": "Extended Geometry Types",
    "autorepair":   "Advanced Failure Auto-Repair",
}

LICENSE_FILE = Path.home() / ".abaqus_agent_license"


class FeatureGate:
    """
    Singleton that manages premium feature access.

    Usage
    -----
    from premium.licensing import feature_gate

    feature_gate.require("coupling")      # raises if not licensed
    if feature_gate.is_enabled("parametric"):
        ...
    """

    def __init__(self):
        self._overrides: dict[str, bool] = {}
        self._license_key: str | None = None
        self._license_features: set[str] | None = None

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def is_enabled(self, feature: str) -> bool:
        """Check if a premium feature is enabled."""
        if feature not in PREMIUM_FEATURES:
            return False

        # Programmatic overrides take priority
        if feature in self._overrides:
            return self._overrides[feature]

        # Environment variable feature flags
        env_features = os.environ.get("ABAQUS_AGENT_FEATURES", "")
        if env_features:
            enabled = {f.strip().lower() for f in env_features.split(",")}
            if "all" in enabled:
                return True
            return feature in enabled

        # License key validation
        return self._check_license_key(feature)

    def require(self, feature: str) -> None:
        """Raise PremiumFeatureRequired if feature is not enabled."""
        if not self.is_enabled(feature):
            display = PREMIUM_FEATURES.get(feature, feature)
            raise AbaqusAgentError(
                ErrorCode.PREMIUM_FEATURE_REQUIRED,
                f"Premium feature '{display}' requires a license. "
                f"Set ABAQUS_AGENT_LICENSE_KEY or ABAQUS_AGENT_FEATURES={feature}",
            )

    def enabled_features(self) -> list[str]:
        """Return list of all currently enabled premium features."""
        return [f for f in PREMIUM_FEATURES if self.is_enabled(f)]

    def enable(self, feature: str) -> None:
        """Programmatically enable a feature (for testing)."""
        self._overrides[feature] = True

    def disable(self, feature: str) -> None:
        """Programmatically disable a feature (for testing)."""
        self._overrides[feature] = False

    def enable_all(self) -> None:
        """Enable all premium features."""
        for f in PREMIUM_FEATURES:
            self._overrides[f] = True

    def disable_all(self) -> None:
        """Disable all premium features."""
        for f in PREMIUM_FEATURES:
            self._overrides[f] = False

    def reset(self) -> None:
        """Clear all programmatic overrides."""
        self._overrides.clear()
        self._license_key = None
        self._license_features = None

    def set_license_key(self, key: str) -> bool:
        """Set and validate a license key. Returns True if valid."""
        features = self._decode_license_key(key)
        if features is not None:
            self._license_key = key
            self._license_features = features
            return True
        return False

    # -----------------------------------------------------------------
    # License key handling
    # -----------------------------------------------------------------

    def _check_license_key(self, feature: str) -> bool:
        """Check if the current license key enables this feature."""
        if self._license_features is None:
            self._load_license_key()
        return self._license_features is not None and (
            "all" in self._license_features or feature in self._license_features
        )

    def _load_license_key(self) -> None:
        """Load license key from env var or file."""
        key = os.environ.get("ABAQUS_AGENT_LICENSE_KEY", "")
        if not key and LICENSE_FILE.exists():
            key = LICENSE_FILE.read_text(encoding="utf-8").strip()
        if key:
            self._license_features = self._decode_license_key(key)

    @staticmethod
    def _decode_license_key(key: str) -> set[str] | None:
        """
        Decode a license key and return the set of enabled features.

        License key format: <features_hex>-<signature>
        Where features_hex encodes a comma-separated feature list
        and signature is HMAC-like verification.

        For development/testing, keys starting with 'dev-' enable
        all features without verification.
        """
        if not key:
            return None

        # Development keys: dev-<anything> enables all features
        if key.startswith("dev-"):
            return {"all"}

        # Production key: <features_encoded>-<checksum>
        parts = key.rsplit("-", 1)
        if len(parts) != 2:
            return None

        features_part, checksum = parts

        # Verify checksum (simple HMAC-like)
        expected = hashlib.sha256(
            f"abaqus-agent-premium:{features_part}".encode()
        ).hexdigest()[:12]

        if checksum != expected:
            return None

        # Decode features
        try:
            features_str = bytes.fromhex(features_part).decode("utf-8")
            return {f.strip() for f in features_str.split(",")}
        except (ValueError, UnicodeDecodeError):
            return None

    @staticmethod
    def generate_license_key(features: list[str]) -> str:
        """Generate a valid license key for given features."""
        features_str = ",".join(sorted(features))
        features_hex = features_str.encode("utf-8").hex()
        checksum = hashlib.sha256(
            f"abaqus-agent-premium:{features_hex}".encode()
        ).hexdigest()[:12]
        return f"{features_hex}-{checksum}"


# Module-level singleton
feature_gate = FeatureGate()
