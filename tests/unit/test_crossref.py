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
