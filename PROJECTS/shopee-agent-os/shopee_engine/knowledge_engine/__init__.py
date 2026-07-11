"""
Knowledge Engine — Knowledge Platform for suenaidee.com

Public API (stable):

    from shopee_engine.knowledge_engine import (
        # Core linking
        get_article_links,
        compute_links,
        LinkBundle,
        LinkRecord,

        # Profiles and signals
        ArticleProfile,
        SignalVector,
        compute_signals,

        # Graph
        KnowledgeGraph,
        GraphNode,
        GraphEdge,

        # Topic Clusters (Phase 3D)
        ClusterBundle,

        # Exceptions
        KnowledgeEngineError,
        GraphValidationError,
        ConfigValidationError,
        PinsValidationError,
    )

Internal modules (subject to change without notice):
    knowledge_engine.graph      — YAML loading and validation
    knowledge_engine.signals    — ArticleProfile, SignalVector, compute_signals
    knowledge_engine.linker     — compute_links, get_article_links
    knowledge_engine.cluster    — ClusterBundle (Phase 3D stub)
    knowledge_engine._exceptions — exception hierarchy
"""

from ._exceptions import (
    KnowledgeEngineError,
    GraphValidationError,
    ConfigValidationError,
    PinsValidationError,
)
from .cluster import ClusterBundle
from .graph import GraphEdge, GraphNode, KnowledgeGraph
from .linker import LinkBundle, LinkRecord, compute_links, get_article_links
from .signals import ArticleProfile, SignalVector, compute_signals

__all__ = [
    # Core linking
    "get_article_links",
    "compute_links",
    "LinkBundle",
    "LinkRecord",
    # Profiles and signals
    "ArticleProfile",
    "SignalVector",
    "compute_signals",
    # Graph
    "KnowledgeGraph",
    "GraphNode",
    "GraphEdge",
    # Topic Clusters
    "ClusterBundle",
    # Exceptions
    "KnowledgeEngineError",
    "GraphValidationError",
    "ConfigValidationError",
    "PinsValidationError",
]
