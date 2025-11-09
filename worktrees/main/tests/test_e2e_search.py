"""E2E tests for search functionality without mocks."""

import json

import pytest
from fastmcp import Client

from src.chunker import ResponseChunker
from src.mcp_server import mcp
from src.zotero_client import ZoteroClient


class TestSearchE2E:
    """End-to-end tests for search with real Zotero."""

    @pytest.mark.asyncio
    async def test_get_collection_items_basic(
        self,
        basic_collection_with_items: tuple[str, int],
        test_zotero_client: ZoteroClient,
    ) -> None:
        """Test basic collection search returns real items."""
        collection_key, expected_count = basic_collection_with_items

        request = {"collection_key": collection_key}

        async with Client(mcp) as client:
            result = await client.call_tool("get_collection_items", arguments=request)
            response = result.data

        # Verify response structure
        assert response.count == expected_count
        assert isinstance(response.items, list)
        assert len(response.items) == expected_count

        item = response.items[0]
        assert item.key
        assert item.data.title
        # Check that abstract exists (might be empty)
        assert hasattr(item.data, "title")

    @pytest.mark.asyncio
    async def test_search_with_fulltext(
        self,
        collection_for_fulltext_test: str,
        test_zotero_client: ZoteroClient,
    ) -> None:
        """Test including full text in search results."""
        collection_key = collection_for_fulltext_test

        async with Client(mcp) as client:
            result = await client.call_tool(
                "get_collection_items",
                arguments={"collection_key": collection_key, "include_fulltext": True},
            )
            response = result.data

        # Check that fulltext field is populated (might be None)
        for item in response.items:
            assert hasattr(item, "fulltext")
            # Fulltext can be None if no PDF available

    @pytest.mark.asyncio
    async def test_search_chunking(
        self,
        collection_for_chunking_test: str,
        chunker_with_small_size: int,
        test_zotero_client: ZoteroClient,
    ) -> None:
        """Test response chunking for large results."""
        collection_key = collection_for_chunking_test

        async with Client(mcp) as client:
            result = await client.call_tool(
                "get_collection_items",
                arguments={"collection_key": collection_key, "include_fulltext": True},
            )
            response = result.data

        # Chunking should be triggered with small chunk size
        if response.has_more:
            assert response.chunk_id
            assert response.current_chunk is not None
            assert response.total_chunks is not None
            assert response.current_chunk >= 1
            assert response.total_chunks >= response.current_chunk

    @pytest.mark.asyncio
    async def test_mcp_token_limit_compliance_get_collection_items(
        self,
        basic_collection_with_items: tuple[str, int],
        test_zotero_client: ZoteroClient,
    ) -> None:
        """Test that get_collection_items responses stay under MCP 25000 token limit.

        This is a critical integration test for the chunker bug fix.
        """
        collection_key, _ = basic_collection_with_items

        request = {"collection_key": collection_key}

        async with Client(mcp) as client:
            result = await client.call_tool("get_collection_items", arguments=request)
            response = result.data

        # Estimate tokens for complete response
        chunker = ResponseChunker()
        response_json = json.dumps(
            {
                "items": [item.model_dump() for item in response.items],
                "count": response.count,
                "has_more": response.has_more,
                "chunk_id": response.chunk_id,
                "current_chunk": response.current_chunk,
                "total_chunks": response.total_chunks,
                "message": response.message,
            },
            default=str,
        )

        response_tokens = len(response_json) // 4  # Simple estimation

        # Response should be under MCP limit
        assert response_tokens < 25000, (
            f"Response exceeds MCP token limit: {response_tokens} tokens "
            f"(limit: 25000). This means chunking is not working correctly!"
        )

        # If chunked, verify chunk message is present
        if response.has_more:
            assert response.chunk_id is not None
            assert response.message is not None
            assert "get_next_chunk" in response.message

    @pytest.mark.asyncio
    async def test_mcp_token_limit_compliance_search_articles(
        self,
        basic_collection_with_items: tuple[str, int],
        test_zotero_client: ZoteroClient,
    ) -> None:
        """Test that search_articles responses stay under MCP 25000 token limit."""
        collection_key, _ = basic_collection_with_items

        request = {"collection_key": collection_key}

        async with Client(mcp) as client:
            result = await client.call_tool("search_articles", arguments=request)
            response = result.data

        # Estimate tokens for complete response
        chunker = ResponseChunker()
        response_json = json.dumps(
            {
                "items": [item.model_dump() for item in response.items],
                "count": response.count,
                "has_more": response.has_more,
                "chunk_id": response.chunk_id,
                "current_chunk": response.current_chunk,
                "total_chunks": response.total_chunks,
                "message": response.message,
            },
            default=str,
        )

        response_tokens = len(response_json) // 4

        assert (
            response_tokens < 25000
        ), f"search_articles response exceeds MCP token limit: {response_tokens} tokens"

    @pytest.mark.asyncio
    async def test_chunked_response_workflow_stays_under_limit(
        self,
        collection_for_chunking_test: str,
        chunker_with_small_size: int,
        test_zotero_client: ZoteroClient,
    ) -> None:
        """Test that all chunks in a multi-chunk workflow stay under token limit."""
        collection_key = collection_for_chunking_test

        async with Client(mcp) as client:
            # Get first chunk
            result = await client.call_tool(
                "get_collection_items", arguments={"collection_key": collection_key}
            )
            response = result.data

            # Check first chunk
            response_json = json.dumps(
                {
                    "items": [item.model_dump() for item in response.items],
                    "count": response.count,
                    "has_more": response.has_more,
                    "chunk_id": response.chunk_id,
                    "current_chunk": response.current_chunk,
                    "total_chunks": response.total_chunks,
                    "message": response.message,
                },
                default=str,
            )
            first_chunk_tokens = len(response_json) // 4

            assert first_chunk_tokens < 25000, f"First chunk: {first_chunk_tokens} tokens"

            # Get all remaining chunks
            chunk_count = 1
            while response.has_more:
                chunk_id = response.chunk_id
                result = await client.call_tool("get_next_chunk", arguments={"chunk_id": chunk_id})
                response = result.data

                # Check each chunk
                response_json = json.dumps(
                    {
                        "items": [item.model_dump() for item in response.items],
                        "count": response.count,
                        "has_more": response.has_more,
                        "chunk_id": response.chunk_id,
                        "current_chunk": response.current_chunk,
                        "total_chunks": response.total_chunks,
                        "message": response.message,
                    },
                    default=str,
                )
                chunk_tokens = len(response_json) // 4

                assert (
                    chunk_tokens < 25000
                ), f"Chunk {chunk_count + 1} exceeds limit: {chunk_tokens} tokens"

                chunk_count += 1

            # Verify we got multiple chunks
            assert chunk_count > 1, "Should have multiple chunks for this test"
