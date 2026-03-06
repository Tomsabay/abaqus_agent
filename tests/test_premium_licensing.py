"""
Tests for premium feature gating (licensing.py).
No Abaqus installation required.
"""

import os
import pytest

from premium.licensing import FeatureGate, PREMIUM_FEATURES, feature_gate
from tools.errors import AbaqusAgentError, ErrorCode


class TestFeatureGate:
    """Test FeatureGate enable/disable/key logic."""

    def setup_method(self):
        """Reset gate state before each test."""
        feature_gate.reset()
        # Clear env vars
        os.environ.pop("ABAQUS_AGENT_FEATURES", None)
        os.environ.pop("ABAQUS_AGENT_LICENSE_KEY", None)

    def test_all_disabled_by_default(self):
        for feat in PREMIUM_FEATURES:
            assert not feature_gate.is_enabled(feat)

    def test_enable_single(self):
        feature_gate.enable("coupling")
        assert feature_gate.is_enabled("coupling")
        assert not feature_gate.is_enabled("parametric")

    def test_enable_all(self):
        feature_gate.enable_all()
        for feat in PREMIUM_FEATURES:
            assert feature_gate.is_enabled(feat)

    def test_disable_all(self):
        feature_gate.enable_all()
        feature_gate.disable_all()
        for feat in PREMIUM_FEATURES:
            assert not feature_gate.is_enabled(feat)

    def test_require_raises_when_disabled(self):
        with pytest.raises(AbaqusAgentError) as exc_info:
            feature_gate.require("coupling")
        assert exc_info.value.code == ErrorCode.PREMIUM_FEATURE_REQUIRED

    def test_require_passes_when_enabled(self):
        feature_gate.enable("coupling")
        feature_gate.require("coupling")  # should not raise

    def test_env_var_features(self):
        os.environ["ABAQUS_AGENT_FEATURES"] = "coupling,parametric"
        assert feature_gate.is_enabled("coupling")
        assert feature_gate.is_enabled("parametric")
        assert not feature_gate.is_enabled("adaptivity")

    def test_env_var_all(self):
        os.environ["ABAQUS_AGENT_FEATURES"] = "all"
        for feat in PREMIUM_FEATURES:
            assert feature_gate.is_enabled(feat)

    def test_dev_license_key(self):
        os.environ["ABAQUS_AGENT_LICENSE_KEY"] = "dev-test123"
        gate = FeatureGate()
        for feat in PREMIUM_FEATURES:
            assert gate.is_enabled(feat)

    def test_generate_and_validate_license_key(self):
        key = FeatureGate.generate_license_key(["coupling", "parametric"])
        gate = FeatureGate()
        assert gate.set_license_key(key)
        assert gate.is_enabled("coupling")
        assert gate.is_enabled("parametric")
        assert not gate.is_enabled("adaptivity")

    def test_invalid_license_key(self):
        gate = FeatureGate()
        assert not gate.set_license_key("invalid-key-here")

    def test_enabled_features_list(self):
        feature_gate.enable("coupling")
        feature_gate.enable("adaptivity")
        enabled = feature_gate.enabled_features()
        assert "coupling" in enabled
        assert "adaptivity" in enabled
        assert "parametric" not in enabled

    def test_reset_clears_overrides(self):
        feature_gate.enable_all()
        feature_gate.reset()
        for feat in PREMIUM_FEATURES:
            assert not feature_gate.is_enabled(feat)

    def test_unknown_feature_returns_false(self):
        assert not feature_gate.is_enabled("nonexistent_feature")
