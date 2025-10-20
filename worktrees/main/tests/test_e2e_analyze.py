"""E2E tests for text analysis functionality."""

import pytest
from fastmcp import Context

from src.mcp_server import analyze_fulltext
from src.models import AnalysisType, AnalyzeFulltextRequest
from src.zotero_client import ZoteroClient


class TestAnalyzeE2E:
    """End-to-end tests for text analysis with real data."""
    
    @pytest.mark.asyncio
    async def test_analyze_summary(
        self,
        mcp_context: Context,
        test_item_with_pdf: str,
        real_zotero_client: ZoteroClient,
    ) -> None:
        """Test summary analysis on real item."""
        import src.mcp_server
        src.mcp_server._client = real_zotero_client
        
        request = AnalyzeFulltextRequest(
            item_key=test_item_with_pdf,
            analysis_type=AnalysisType.SUMMARY,
        )
        
        response = await analyze_fulltext(mcp_context, request)
        
        assert response.item_key == test_item_with_pdf
        assert response.title
        assert response.analysis_type == AnalysisType.SUMMARY
        
        # Result can be empty list if no fulltext
        if response.result and not response.error:
            assert isinstance(response.result, (dict, list))
    
    @pytest.mark.asyncio
    async def test_analyze_without_fulltext(
        self,
        mcp_context: Context,
        test_item_without_pdf: str,
        real_zotero_client: ZoteroClient,
    ) -> None:
        """Test analysis handles missing fulltext gracefully."""
        import src.mcp_server
        src.mcp_server._client = real_zotero_client
        
        request = AnalyzeFulltextRequest(
            item_key=test_item_without_pdf,
            analysis_type=AnalysisType.KEY_POINTS,
        )
        
        response = await analyze_fulltext(mcp_context, request)
        
        assert response.item_key == test_item_without_pdf
        # Should have error message about missing fulltext
        if not await real_zotero_client.get_fulltext(test_item_without_pdf):
            assert response.error or response.result == []
    
    @pytest.mark.asyncio
    async def test_analyze_methods(
        self,
        mcp_context: Context,
        test_item_with_pdf: str,
        real_zotero_client: ZoteroClient,
    ) -> None:
        """Test methods extraction from real article."""
        import src.mcp_server
        src.mcp_server._client = real_zotero_client
        
        request = AnalyzeFulltextRequest(
            item_key=test_item_with_pdf,
            analysis_type=AnalysisType.METHODS,
        )
        
        response = await analyze_fulltext(mcp_context, request)
        
        assert response.analysis_type == AnalysisType.METHODS
        
        if response.result and not response.error:
            # Check structure for methods analysis
            assert isinstance(response.result, (dict, list))
    
    @pytest.mark.asyncio  
    async def test_analyze_all_types(
        self,
        mcp_context: Context,
        test_item_with_pdf: str,
        real_zotero_client: ZoteroClient,
    ) -> None:
        """Test all analysis types work without errors."""
        import src.mcp_server
        src.mcp_server._client = real_zotero_client
        
        for analysis_type in AnalysisType:
            request = AnalyzeFulltextRequest(
                item_key=test_item_with_pdf,
                analysis_type=analysis_type,
            )
            
            response = await analyze_fulltext(mcp_context, request)
            
            # Should not raise exceptions
            assert response.item_key == test_item_with_pdf
            assert response.analysis_type == analysis_type
            # Either has result or error
            assert response.result is not None or response.error