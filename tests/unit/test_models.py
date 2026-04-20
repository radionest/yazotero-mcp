"""Unit tests for Zotero write response models."""

from yazot.models import ZoteroFailedItem, ZoteroWriteResponse


class TestZoteroFailedItem:
    def test_failed_item_without_key(self) -> None:
        """HTTP 400 validation errors don't include a key field."""
        item = ZoteroFailedItem(code=400, message='"firstName" is required if "lastName" is set')

        assert item.key is None
        assert item.code == 400
        assert "firstName" in item.message

    def test_failed_item_with_key(self) -> None:
        """Standard failed items include a key field."""
        item = ZoteroFailedItem(key="ABC123", code=409, message="Item already exists")

        assert item.key == "ABC123"
        assert item.code == 409


class TestZoteroWriteResponse:
    def test_write_response_with_keyless_failure(self) -> None:
        """Response with failed items missing key parses correctly."""
        raw = {
            "successful": {},
            "unchanged": {},
            "failed": {
                "0": {"code": 400, "message": '"firstName" is required'},
            },
        }

        response = ZoteroWriteResponse.model_validate(raw)

        assert response.has_failures()
        assert response.failed["0"].code == 400
        assert response.failed["0"].key is None

    def test_write_response_mixed_success_and_failure(self) -> None:
        """Response with both successful and failed items."""
        raw = {
            "successful": {"0": {"key": "XYZ789", "data": {}}},
            "unchanged": {},
            "failed": {
                "1": {"code": 400, "message": "Validation error"},
            },
        }

        response = ZoteroWriteResponse.model_validate(raw)

        assert response.has_failures()
        assert response.get_successful_keys() == ["XYZ789"]
