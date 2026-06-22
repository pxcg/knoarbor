from __future__ import annotations

from knoarbor.core.schemas.wiki_relation_plan import WikiRelationOperation, WikiRelationPlan


class WikiPageOperation(WikiRelationOperation):
    """Page planning operation.

    This class intentionally inherits the current relation-plan operation while
    the ingest pipeline migrates from relation wording to page-plan wording.
    The selected atom fields on the parent schema are the stable bridge for the
    knowledge atom ingest architecture.
    """


class WikiPagePlan(WikiRelationPlan):
    """Page planning result for ingest.

    The runtime still accepts `wiki_relation_plan.v1` for migration stability,
    but page planning should use this type name in new code and docs.
    """

