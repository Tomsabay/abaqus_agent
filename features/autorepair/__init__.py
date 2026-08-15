"""
features.autorepair
-------------------
Failure auto-repair for Abaqus Agent.

LLM-powered log analysis, diagnosis, and automatic retry.
"""

from features.autorepair.retry_loop import autorepair_hook
from features.feature_registry import register_hook

register_hook("post_submit_failure", autorepair_hook)
