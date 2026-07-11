"""Knowledge Engine exception hierarchy."""

from __future__ import annotations


class KnowledgeEngineError(Exception):
    """Base exception for all Knowledge Engine errors."""


class GraphValidationError(KnowledgeEngineError):
    """Raised when product_graph.yaml fails validation at startup."""


class ConfigValidationError(KnowledgeEngineError):
    """Raised when link_config.yaml fails validation at startup."""


class PinsValidationError(KnowledgeEngineError):
    """Raised when pinned_links.yaml fails validation at startup."""
