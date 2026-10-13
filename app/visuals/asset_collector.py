"""Public-domain visual asset collector querying Wikimedia Commons with local caching."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from app.config import config
from app.utils.logger import logger


@dataclass
class CollectedAsset:
    """Public domain or appropriately licensed visual asset."""
    file_path: Path
    title: str
    source_url: str
    author: str
    license_name: str
    attribution_text: str
    is_public_domain: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": str(self.file_path),
            "title": self.title,
            "source_url": self.source_url,
            "author": self.author,
            "license_name": self.license_name,
            "attribution_text": self.attribution_text,
            "is_public_domain": self.is_public_domain,
        }


class AssetCollector:
    """Discovers and caches public-domain and CC-licensed historical imagery from Wikimedia Commons."""

    COMMONS_API_URL = "https://commons.wikimedia.org/w/api.php"

    def __init__(self, cache_dir: Optional[Path] = None) -> None:
        self.cache_dir = cache_dir or (config.data_dir / "asset_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def search_public_domain_image(self, query: str) -> Optional[CollectedAsset]:
        """Search Wikimedia Commons for public-domain historical images matching the query.

        Returns None if offline or no suitable high-resolution public asset is found.
        """
        # Clean query for search
        clean_query = self._sanitize_query(query)
        if not clean_query:
            return None

        # Check local cache first
        cache_key = hashlib.md5(clean_query.lower().encode("utf-8")).hexdigest()
        meta_cache_file = self.cache_dir / f"{cache_key}.json"
        if meta_cache_file.exists():
            try:
                with open(meta_cache_file, "r", encoding="utf-8") as f:
                    cached_data = json.load(f)
                img_path = Path(cached_data["file_path"])
                if img_path.exists() and img_path.stat().st_size > 5000:
                    logger.debug(f"Loaded cached public asset for query '{clean_query}': {img_path.name}")
                    return CollectedAsset(
                        file_path=img_path,
                        title=cached_data["title"],
                        source_url=cached_data["source_url"],
                        author=cached_data["author"],
                        license_name=cached_data["license_name"],
                        attribution_text=cached_data["attribution_text"],
                        is_public_domain=cached_data.get("is_public_domain", True),
                    )
            except Exception as e:
                logger.debug(f"Error reading asset cache for '{clean_query}': {e}")

        # Query Wikimedia Commons API
        params = {
            "action": "query",
            "generator": "search",
            "gsrsearch": f"{clean_query} filetype:bitmap",
            "gsrnamespace": "6",  # File: namespace
            "gsrlimit": "3",
            "prop": "imageinfo",
            "iiprop": "url|size|extmetadata|mime",
            "iiurlwidth": "1080",
            "format": "json",
        }

        try:
            url = f"{self.COMMONS_API_URL}?{urllib.parse.urlencode(params)}"
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "MhideStoryIntelligence/1.0 (Autonomous Educational History Research)"},
            )
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                if resp.status != 200:
                    return None
                data = json.loads(resp.read().decode("utf-8"))

            pages = data.get("query", {}).get("pages", {})
            if not pages:
                return None

            for page_id, page in pages.items():
                imageinfo_list = page.get("imageinfo", [])
                if not imageinfo_list:
                    continue
                info = imageinfo_list[0]
                mime = info.get("mime", "")
                if mime not in ("image/jpeg", "image/png", "image/webp"):
                    continue

                thumb_url = info.get("thumburl") or info.get("url")
                if not thumb_url:
                    continue

                metadata = info.get("extmetadata", {})
                artist = self._clean_html(metadata.get("Artist", {}).get("value", "Public Domain / Unknown"))
                license_short = metadata.get("LicenseShortName", {}).get("value", "Public Domain")
                source_desc = self._clean_html(metadata.get("ObjectName", {}).get("value", page.get("title", "Historical Archive")))

                # Download image
                ext = "jpg" if "jpeg" in mime or "jpg" in mime else ("png" if "png" in mime else "webp")
                dest_file = self.cache_dir / f"{cache_key}.{ext}"

                img_req = urllib.request.Request(
                    thumb_url,
                    headers={"User-Agent": "MhideStoryIntelligence/1.0 (Educational Archival Download)"},
                )
                with urllib.request.urlopen(img_req, timeout=8.0) as img_resp:
                    content = img_resp.read()
                    if len(content) < 5000:
                        continue
                    with open(dest_file, "wb") as f_out:
                        f_out.write(content)

                attribution = f"Source: Wikimedia Commons | Artist: {artist[:60]} | License: {license_short}"
                asset = CollectedAsset(
                    file_path=dest_file,
                    title=source_desc[:100],
                    source_url=info.get("descriptionurl", thumb_url),
                    author=artist[:80],
                    license_name=license_short,
                    attribution_text=attribution,
                    is_public_domain="public domain" in license_short.lower() or "cc0" in license_short.lower(),
                )

                # Save metadata cache
                with open(meta_cache_file, "w", encoding="utf-8") as f_meta:
                    json.dump(asset.to_dict(), f_meta, indent=2)

                logger.info(f"Discovered public-domain historical image for '{clean_query}': {dest_file.name} ({license_short})")
                return asset

        except Exception as e:
            logger.debug(f"Wikimedia Commons search skipped/unavailable for '{clean_query}': {e}")

        return None

    @staticmethod
    def _sanitize_query(query: str) -> str:
        """Strip filler words to create concise historical search keywords."""
        # Remove common visual prompt adjectives
        cleaned = re.sub(
            r"\b(cinematic|vertical|9:16|shot|dramatic|lighting|moody|realistic|textures|high|resolution|photo|image)\b",
            "",
            query,
            flags=re.IGNORECASE,
        )
        words = [w.strip() for w in cleaned.split() if len(w.strip()) > 2]
        return " ".join(words[:4])

    @staticmethod
    def _clean_html(raw_html: str) -> str:
        """Strip HTML tags from metadata fields."""
        clean = re.sub(r"<[^>]+>", "", raw_html)
        return " ".join(clean.split()).strip()


# Global asset collector singleton
asset_collector = AssetCollector()
