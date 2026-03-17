import os
import logging

logger = logging.getLogger(__name__)
logger.info("\n[PromptBuilder] __init__.py is being loaded...")

# WEB_DIRECTORY must be set before any import failure can skip it
_js_dir = os.path.join(os.path.dirname(__file__), "js")
WEB_DIRECTORY = "./js" if os.path.isdir(_js_dir) else None

try:
    from .nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS
    logger.info(f"[PromptBuilder] Loaded nodes: {list(NODE_CLASS_MAPPINGS.keys())}")
except Exception as e:
    logger.warning(f"[PromptBuilder] Failed to load nodes: {e}")
    NODE_CLASS_MAPPINGS = {}
    NODE_DISPLAY_NAME_MAPPINGS = {}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
