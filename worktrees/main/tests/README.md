# E2E Testing Strategy for Zotero MCP Server

## Overview
This test suite implements true end-to-end testing without mocks, using real Zotero instances.

## Setup

### Option 1: Test Zotero Account
1. Create a test Zotero account at https://www.zotero.org
2. Create a test library with sample data
3. Generate API key at https://www.zotero.org/settings/keys
4. Copy `.env.test.example` to `.env.test` and fill credentials

### Option 2: Local Zotero Database
1. Install Zotero locally
2. Create test library with sample data
3. Configure `TEST_ZOTERO_LOCAL=true` in `.env.test`

## Test Data Preparation

Create the following in your test library:

1. **Test Collection** (`TEST_COLLECTION_KEY`)
   - Add 5-10 research articles
   - Mix of items with and without PDFs
   - Various metadata (tags, abstracts)

2. **Test Item with PDF** (`TEST_ITEM_WITH_PDF`)
   - Upload article with full PDF
   - Ensure PDF is accessible

3. **Test Item without PDF** (`TEST_ITEM_NO_PDF`)
   - Article with only metadata
   - No attachments

## Running Tests

```bash
# Run all E2E tests
pytest tests/test_e2e_*.py -v

# Run specific test module
pytest tests/test_e2e_search.py -v

# Run with coverage
pytest tests/test_e2e_*.py --cov=src --cov-report=html

# Run integration tests only
pytest tests/test_e2e_integration.py -v
```

## Test Architecture

### No Mocks Approach
- All tests use real Zotero API or local database
- Test fixtures manage real data lifecycle
- Cleanup happens automatically after tests

### Test Categories

1. **Search Tests** (`test_e2e_search.py`)
   - Collection browsing
   - Query filtering
   - Full-text inclusion
   - Response chunking
   - Cache behavior

2. **Analysis Tests** (`test_e2e_analyze.py`)
   - Text summarization
   - Key points extraction
   - Methods analysis
   - Error handling for missing PDFs

3. **Notes Tests** (`test_e2e_notes.py`)
   - CRUD operations
   - Batch note management
   - Search functionality
   - Parent-child relationships

4. **Integration Tests** (`test_e2e_integration.py`)
   - Complete research workflows
   - Batch processing
   - Cross-collection operations
   - Performance validation

### Benefits of This Approach

1. **Real-world validation** - Tests actual Zotero API behavior
2. **Integration confidence** - Catches real integration issues
3. **Performance testing** - Measures actual API latency
4. **Data consistency** - Verifies real data relationships
5. **Error handling** - Tests real error scenarios

### Considerations

1. **Test isolation** - Each test cleans up its data
2. **Network dependency** - Tests require internet for Web API
3. **Rate limiting** - Zotero API has rate limits
4. **Test data stability** - Keep test library consistent
5. **Credentials security** - Never commit `.env.test`

## CI/CD Integration

For GitHub Actions:

```yaml
- name: Run E2E Tests
  env:
    TEST_ZOTERO_LIBRARY_ID: ${{ secrets.TEST_ZOTERO_LIBRARY_ID }}
    TEST_ZOTERO_API_KEY: ${{ secrets.TEST_ZOTERO_API_KEY }}
    TEST_COLLECTION_KEY: ${{ secrets.TEST_COLLECTION_KEY }}
  run: pytest tests/test_e2e_*.py
```

## Debugging

Enable verbose output:
```bash
pytest tests/test_e2e_*.py -v -s --log-cli-level=DEBUG
```

Check Zotero API responses:
```python
# In tests, add logging
import logging
logging.basicConfig(level=logging.DEBUG)
```