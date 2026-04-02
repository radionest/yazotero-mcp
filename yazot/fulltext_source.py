"""Fulltext source plugin protocol and discovery via entry_points."""

import importlib.metadata
import logging
from collections.abc import Mapping
from typing import Protocol, overload, runtime_checkable

logger = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "yazot.fulltext_sources"


@runtime_checkable
class FulltextSource(Protocol):
    """Protocol for fulltext PDF sources (built-in and plugins).

    Each source searches for a PDF URL given a DOI and/or title.
    At least one of doi or title must be provided (enforced via overloads).
    """

    @property
    def name(self) -> str: ...

    @property
    def description(self) -> str: ...

    @overload
    async def find_pdf_url(self, *, doi: str, title: str | None = ...) -> str | None: ...
    @overload
    async def find_pdf_url(self, *, doi: None = ..., title: str) -> str | None: ...

    async def aclose(self) -> None: ...


def discover_sources(env: Mapping[str, str]) -> list[FulltextSource]:
    """Load fulltext source plugins registered via entry_points.

    Each entry point must be a factory: (env: Mapping[str, str]) -> FulltextSource | None.
    Returns None if not configured (e.g. missing required env vars).
    """
    sources: list[FulltextSource] = []
    eps = importlib.metadata.entry_points(group=ENTRY_POINT_GROUP)
    for ep in eps:
        try:
            factory = ep.load()
            source = factory(env)
            if source is not None:
                if (
                    not isinstance(getattr(source, "name", None), str)
                    or not isinstance(getattr(source, "description", None), str)
                    or not callable(getattr(source, "find_pdf_url", None))
                    or not callable(getattr(source, "aclose", None))
                ):
                    raise TypeError(f"Plugin {ep.name} returned an invalid fulltext source")
                sources.append(source)
                logger.info("Loaded fulltext source plugin: %s", source.name)
            else:
                logger.debug("Plugin %s returned None (not configured)", ep.name)
        except Exception:
            logger.warning("Failed to load fulltext source plugin: %s", ep.name, exc_info=True)
    return sources
