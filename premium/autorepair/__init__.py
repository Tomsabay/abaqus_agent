"""
premium.autorepair
------------------
Advanced failure auto-repair for Abaqus Agent (premium).

LLM-powered log analysis, diagnosis, and automatic retry.
"""

from premium.autorepair.retry_loop import autorepair_hook
from premium.feature_registry import register_hook

register_hook("post_submit_failure", "autorepair", autorepair_hook)
