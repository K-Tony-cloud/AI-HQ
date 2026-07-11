"""
ClusterBundle — Topic Cluster view across multiple articles.

Phase 3D stub. Raises NotImplementedError until implemented.
"""

from __future__ import annotations


class ClusterBundle:
    """
    Topic Cluster — a set of articles organized around a shared pillar topic.

    Relationship to LinkBundle:
        ClusterBundle.link_bundles[article_id] == LinkBundle for that article.
        LinkBundle is a single-article projection of a ClusterBundle.

    Not yet implemented. Planned for Phase 3D.
    """

    def __init__(self, *args, **kwargs) -> None:
        raise NotImplementedError(
            "ClusterBundle is planned for Phase 3D. "
            "Use get_article_links() for single-article links (Phase 3A/3B)."
        )
