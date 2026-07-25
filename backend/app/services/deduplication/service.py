"""Article deduplication using fuzzy body-text similarity."""

import logging

from rapidfuzz.fuzz import token_sort_ratio

from app.schemas.deduplication import DeduplicatedArticle, DeduplicationGroup
from app.schemas.extraction import ExtractedArticle

logger = logging.getLogger(__name__)

TITLE_SIMILARITY_WEIGHT = 0.6
BODY_SIMILARITY_WEIGHT = 0.4
# The weighted score is lower than a body-only match for independently written
# coverage, so 55 preserves meaningful title overlap without requiring prose reuse.
DEFAULT_SIMILARITY_THRESHOLD = 55


class DeduplicationService:
    """Group successfully extracted articles that describe the same story."""

    def __init__(
        self, similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD
    ) -> None:
        """Initialize the service with a minimum fuzzy-match score."""
        if not 0 <= similarity_threshold <= 100:
            raise ValueError("similarity_threshold must be between 0 and 100")
        self.similarity_threshold = similarity_threshold

    def deduplicate(
        self, articles: list[ExtractedArticle]
    ) -> list[DeduplicationGroup]:
        """Return duplicate groups for successfully extracted articles only."""
        successful_articles = [article for article in articles if article.success]
        article_groups = self._group_articles(successful_articles)
        groups = [
            self._build_group(article_group) for article_group in article_groups
        ]
        duplicates_removed = len(successful_articles) - len(groups)
        logger.info(
            "Article deduplication complete: total=%d groups=%d duplicates_removed=%d",
            len(articles),
            len(groups),
            duplicates_removed,
        )
        return groups

    def _compute_similarity(
        self, first: ExtractedArticle, second: ExtractedArticle
    ) -> float:
        """Combine title and body similarity, prioritizing shared event titles."""
        title_score = token_sort_ratio(first.title, second.title)
        body_score = token_sort_ratio(first.body, second.body)
        return (
            TITLE_SIMILARITY_WEIGHT * title_score
            + BODY_SIMILARITY_WEIGHT * body_score
        )

    def _group_articles(
        self, articles: list[ExtractedArticle]
    ) -> list[list[ExtractedArticle]]:
        """Group articles whose pairwise similarity exceeds the threshold."""
        parents = list(range(len(articles)))

        def find(index: int) -> int:
            while parents[index] != index:
                parents[index] = parents[parents[index]]
                index = parents[index]
            return index

        def union(first_index: int, second_index: int) -> None:
            first_root = find(first_index)
            second_root = find(second_index)
            if first_root != second_root:
                parents[second_root] = first_root

        # This O(n^2) pass suits hackathon-sized batches; use blocking or LSH
        # before applying the same strategy to thousands of articles.
        for first_index, first in enumerate(articles):
            for second_index in range(first_index + 1, len(articles)):
                if (
                    self._compute_similarity(first, articles[second_index])
                    > self.similarity_threshold
                ):
                    union(first_index, second_index)

        grouped_indices: dict[int, list[ExtractedArticle]] = {}
        for index, article in enumerate(articles):
            grouped_indices.setdefault(find(index), []).append(article)
        return list(grouped_indices.values())

    def _pick_representative(
        self, articles: list[ExtractedArticle]
    ) -> ExtractedArticle:
        """Select the most complete article to represent a duplicate group."""
        longest_body_length = max(len(article.body) for article in articles)
        close_to_longest = [
            article
            for article in articles
            if len(article.body) >= longest_body_length * 0.95
        ]
        # When bodies are within 5% of the longest, prefer the earliest
        # publication date; otherwise the longest body is the representative.
        if len(close_to_longest) == 1:
            return close_to_longest[0]
        return min(
            close_to_longest,
            key=lambda article: (
                article.published_date is None,
                article.published_date or "",
                -len(article.body),
                article.url,
            ),
        )

    def _build_group(self, articles: list[ExtractedArticle]) -> DeduplicationGroup:
        """Convert one article group into its public deduplication schema."""
        representative = self._pick_representative(articles)
        return DeduplicationGroup(
            representative=DeduplicatedArticle(
                url=representative.url,
                title=representative.title,
                publisher=representative.publisher,
                published_date=representative.published_date,
                body=representative.body,
                duplicate_of=None,
            ),
            duplicates=[
                DeduplicatedArticle(
                    url=article.url,
                    title=article.title,
                    publisher=article.publisher,
                    published_date=article.published_date,
                    body=article.body,
                    duplicate_of=representative.url,
                )
                for article in articles
                if article is not representative
            ],
        )
