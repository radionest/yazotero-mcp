#!/usr/bin/env python3
"""Script to cleanup entire Zotero library.

WARNING: This will delete ALL items and collections in your library!
"""

import sys

from tests.test_helpers import ZoteroTestDataManager
from yazot.zotero_client import ZoteroClient


def main() -> None:
    """Clean up entire Zotero library."""
    print("=" * 60)
    print("ZOTERO LIBRARY CLEANUP")
    print("=" * 60)

    print("\nInitializing Zotero client...")
    try:
        client = ZoteroClient()
    except ValueError as e:
        print(f"Error: {e}")
        print("Make sure ZOTERO_API_KEY and ZOTERO_LIBRARY_ID are set")
        sys.exit(1)

    if client.mode != "web":
        print("Error: Cleanup only works in web mode (not local mode)")
        print("Make sure ZOTERO_API_KEY and ZOTERO_LIBRARY_ID are set")
        sys.exit(1)

    # Show statistics
    print("\nFetching library statistics...")
    try:
        total_items = len(client.items)
        total_collections = len(client.collections)

        print("\nLibrary statistics:")
        print(f"  Total items:       {total_items:,}")
        print(f"  Total collections: {total_collections:,}")
    except Exception as e:
        print(f"Warning: Could not fetch statistics: {e}")

    print("\n" + "=" * 60)
    print("WARNING: This will delete ALL items and collections!")
    print("=" * 60)

    print("\nStarting cleanup...")
    manager = ZoteroTestDataManager(client)

    result = manager.cleanup_entire_library()

    print(f"\n{'=' * 60}")
    print("Cleanup complete!")
    print(f"{'=' * 60}")
    print(f"  Items deleted:       {result['items']:,}")
    print(f"  Collections deleted: {result['collections']:,}")


if __name__ == "__main__":
    main()
