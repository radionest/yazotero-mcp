"""Unit tests for Crossref metadata conversion."""

from yazot.crossref_client import CrossrefClient, CrossrefWork
from yazot.models import ItemCreate


class TestCrossrefClient:
    """Unit tests for Crossref metadata conversion."""

    def test_crossref_to_zotero_journal_article(self) -> None:
        """Test conversion of journal article metadata."""
        crossref_data = CrossrefWork(
            type="journal-article",
            DOI="10.1234/example",
            title=["Test Article Title"],
            author=[
                {"given": "John", "family": "Doe"},
                {"given": "Jane", "family": "Smith"},
            ],
            **{
                "container-title": ["Nature"],
                "volume": "500",
                "issue": "7462",
                "page": "123-456",
                "ISSN": ["0028-0836"],
                "published-print": {"date-parts": [[2023, 8, 15]]},
                "abstract": "This is a test abstract.",
            },
        )

        client = CrossrefClient()
        zotero_item = client.crossref_to_zotero(crossref_data)

        assert isinstance(zotero_item, ItemCreate)
        assert zotero_item.item_type == "journalArticle"

        item_dict = zotero_item.model_dump(by_alias=True, exclude_none=True)
        assert item_dict["itemType"] == "journalArticle"
        assert item_dict["title"] == "Test Article Title"
        assert item_dict["DOI"] == "10.1234/example"
        assert len(item_dict["creators"]) == 2
        assert item_dict["creators"][0]["firstName"] == "John"
        assert item_dict["creators"][0]["lastName"] == "Doe"
        assert item_dict["publicationTitle"] == "Nature"
        assert item_dict["volume"] == "500"
        assert item_dict["issue"] == "7462"
        assert item_dict["pages"] == "123-456"
        assert item_dict["ISSN"] == "0028-0836"
        assert item_dict["date"] == "2023-08-15"
        assert item_dict["abstractNote"] == "This is a test abstract."

    def test_crossref_to_zotero_organization_author(self) -> None:
        """Author with family but no given name uses Zotero 'name' field."""
        crossref_data = CrossrefWork(
            type="journal-article",
            DOI="10.1234/org",
            title=["Consortium Study"],
            author=[{"family": "WHO Research Consortium"}],
            **{"container-title": ["Lancet"], "published-print": {"date-parts": [[2024]]}},
        )

        client = CrossrefClient()
        item = client.crossref_to_zotero(crossref_data)
        item_dict = item.model_dump(by_alias=True, exclude_none=True)

        assert len(item_dict["creators"]) == 1
        creator = item_dict["creators"][0]
        assert creator["name"] == "WHO Research Consortium"
        assert "firstName" not in creator
        assert "lastName" not in creator

    def test_crossref_to_zotero_mixed_authors(self) -> None:
        """Mix of individual and organizational authors produces correct formats."""
        crossref_data = CrossrefWork(
            type="journal-article",
            DOI="10.1234/mixed",
            title=["Mixed Authors"],
            author=[
                {"given": "Alice", "family": "Chen"},
                {"family": "ECOG-ACRIN Cancer Research Group"},
                {"given": "Bob", "family": "Smith"},
            ],
            **{"container-title": ["JAMA"], "published-print": {"date-parts": [[2024]]}},
        )

        client = CrossrefClient()
        item = client.crossref_to_zotero(crossref_data)
        item_dict = item.model_dump(by_alias=True, exclude_none=True)

        assert len(item_dict["creators"]) == 3
        assert item_dict["creators"][0]["firstName"] == "Alice"
        assert item_dict["creators"][0]["lastName"] == "Chen"
        assert item_dict["creators"][1]["name"] == "ECOG-ACRIN Cancer Research Group"
        assert "firstName" not in item_dict["creators"][1]
        assert item_dict["creators"][2]["firstName"] == "Bob"
        assert item_dict["creators"][2]["lastName"] == "Smith"

    def test_crossref_to_zotero_given_only_author(self) -> None:
        """Author with only given name (no family) uses 'name' field."""
        crossref_data = CrossrefWork(
            type="journal-article",
            DOI="10.1234/given",
            title=["Single Name"],
            author=[{"given": "Sukarno"}],
            **{"container-title": ["Journal"], "published-print": {"date-parts": [[2024]]}},
        )

        client = CrossrefClient()
        item = client.crossref_to_zotero(crossref_data)
        item_dict = item.model_dump(by_alias=True, exclude_none=True)

        assert len(item_dict["creators"]) == 1
        assert item_dict["creators"][0]["name"] == "Sukarno"
        assert "firstName" not in item_dict["creators"][0]
        assert "lastName" not in item_dict["creators"][0]
