"""Reference database and large scientific asset lifecycle management."""

from .manager import (
    AssetRecord,
    ReferenceAssetRegistry,
    download_asset,
    import_local_asset,
    safe_extract_archive,
)

__all__ = [
    "AssetRecord",
    "ReferenceAssetRegistry",
    "download_asset",
    "import_local_asset",
    "safe_extract_archive",
]
