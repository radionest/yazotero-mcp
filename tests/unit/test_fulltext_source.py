"""Tests for fulltext source protocol and plugin discovery."""

from unittest.mock import MagicMock, patch

from yazot.fulltext_source import ENTRY_POINT_GROUP, FulltextSource, discover_sources


def _make_entry_point(name: str, factory_return: FulltextSource | None) -> MagicMock:
    """Create a mock entry point."""
    ep = MagicMock()
    ep.name = name
    ep.load.return_value = MagicMock(return_value=factory_return)
    return ep


def _make_source(name: str = "test", description: str = "Test source") -> MagicMock:
    source = MagicMock(spec=FulltextSource)
    source.name = name
    source.description = description
    return source


class TestDiscoverSources:
    def test_no_plugins(self) -> None:
        with patch("yazot.fulltext_source.importlib.metadata.entry_points", return_value=[]):
            sources = discover_sources({})
        assert sources == []

    def test_loads_configured_plugin(self) -> None:
        source = _make_source("libgen", "Libgen source")
        ep = _make_entry_point("libgen", source)

        with patch(
            "yazot.fulltext_source.importlib.metadata.entry_points", return_value=[ep]
        ) as mock_ep:
            sources = discover_sources({"FULLTEXT_LIBGEN_MIRROR": "https://libgen.is"})

        mock_ep.assert_called_once_with(group=ENTRY_POINT_GROUP)
        assert len(sources) == 1
        assert sources[0].name == "libgen"

    def test_skips_unconfigured_plugin(self) -> None:
        ep = _make_entry_point("libgen", None)

        with patch("yazot.fulltext_source.importlib.metadata.entry_points", return_value=[ep]):
            sources = discover_sources({})

        assert sources == []

    def test_skips_broken_plugin(self) -> None:
        ep = MagicMock()
        ep.name = "broken"
        ep.load.side_effect = ImportError("missing dependency")

        with patch("yazot.fulltext_source.importlib.metadata.entry_points", return_value=[ep]):
            sources = discover_sources({})

        assert sources == []

    def test_skips_plugin_with_raising_factory(self) -> None:
        def broken_factory(env: dict) -> None:  # type: ignore[type-arg]
            raise RuntimeError("plugin factory failed")

        ep = MagicMock()
        ep.name = "broken"
        ep.load.return_value = broken_factory

        with patch("yazot.fulltext_source.importlib.metadata.entry_points", return_value=[ep]):
            sources = discover_sources({})

        assert sources == []

    def test_multiple_plugins(self) -> None:
        s1 = _make_source("libgen")
        s2 = _make_source("zlibrary")
        ep1 = _make_entry_point("libgen", s1)
        ep2 = _make_entry_point("zlibrary", s2)

        with patch(
            "yazot.fulltext_source.importlib.metadata.entry_points", return_value=[ep1, ep2]
        ):
            sources = discover_sources({})

        assert len(sources) == 2

    def test_factory_receives_env(self) -> None:
        source = _make_source("test")
        ep = MagicMock()
        ep.name = "test"
        factory = MagicMock(return_value=source)
        ep.load.return_value = factory

        env = {"FULLTEXT_TEST_KEY": "secret"}
        with patch("yazot.fulltext_source.importlib.metadata.entry_points", return_value=[ep]):
            discover_sources(env)

        factory.assert_called_once_with(env)
