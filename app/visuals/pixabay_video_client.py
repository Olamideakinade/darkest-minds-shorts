"""Pixabay Video Client for discovering and caching high-definition moving video footage."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from app.config import config
from app.utils.logger import logger


class PixabayVideoClient:
    """Fetches and caches real moving stock footage from Pixabay Video API."""

    API_URL = "https://pixabay.com/api/videos/"

    def __init__(self, api_key: Optional[str] = None, cache_dir: Optional[Path] = None) -> None:
        self.api_key = api_key or getattr(config, "pixabay_api_key", "")
        self.cache_dir = cache_dir or (config.data_dir / "video_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.used_pexels_urls: set = set()
        self.used_video_ids: set = set()

    def reset_session(self) -> None:
        """Clear session tracking sets for a new video production run."""
        self.used_pexels_urls.clear()
        self.used_video_ids.clear()
        logger.debug("Pixabay video client session tracking reset.")

    def search_and_download_video(
        self,
        query: str,
        target_duration: float = 4.0,
        min_width: int = 1080,
    ) -> Optional[Path]:
        """Search Pixabay for real moving video clips matching query and download the best match."""
        if not self.api_key:
            logger.warning("Pixabay API key not configured; skipping stock video search.")
            return None

        clean_query = query.strip()
        if not clean_query:
            return None

        # Check local search cache only if not already used in this video run
        cache_key = hashlib.md5(clean_query.lower().encode("utf-8")).hexdigest()
        meta_file = self.cache_dir / f"{cache_key}.json"

        if meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
                video_file = Path(meta.get("file_path", ""))
                v_id = meta.get("video_id")
                page_url = meta.get("page_url", "")
                if video_file.exists() and video_file.stat().st_size > 10000:
                    if v_id not in self.used_video_ids and page_url not in self.used_pexels_urls:
                        self.used_video_ids.add(v_id)
                        if page_url:
                            self.used_pexels_urls.add(page_url)
                        logger.debug(f"Loaded cached moving video for '{clean_query}': {video_file.name}")
                        return video_file
            except Exception as e:
                logger.debug(f"Failed to read cached video metadata: {e}")

        # Query Pixabay Video API
        params = {
            "key": self.api_key,
            "q": clean_query,
            "video_type": "all",
            "per_page": 10,
        }
        url = f"{self.API_URL}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"User-Agent": "MhideVideoIntelligence/2.0"})

        try:
            with urllib.request.urlopen(req, timeout=12.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.warning(f"Pixabay video search error for query '{clean_query}': {e}")
            return None

        hits = data.get("hits", [])
        if not hits:
            logger.info(f"No Pixabay videos found for query: '{clean_query}'")
            return None

        # Find best resolution video that has not been used yet in this run
        best_hit = None
        best_video_url = None
        best_res_name = "large"

        for hit in hits:
            h_id = hit.get("id")
            if h_id in self.used_video_ids:
                continue
            vids = hit.get("videos", {})
            # Prefer large (4k or 1080p), fallback to medium (720p/1080p)
            for res_name in ("large", "medium", "small"):
                v_info = vids.get(res_name)
                if v_info and v_info.get("url"):
                    u = v_info["url"]
                    if u not in self.used_pexels_urls:
                        best_hit = hit
                        best_video_url = u
                        best_res_name = res_name
                        break
            if best_video_url:
                break

        if not best_video_url or not best_hit:
            logger.info(f"All video hits for '{clean_query}' have already been used in this video. Routing to alternative visual.")
            return None

        video_id = best_hit.get("id")
        self.used_video_ids.add(video_id)
        self.used_pexels_urls.add(best_video_url)
        if best_hit.get("pageURL"):
            self.used_pexels_urls.add(best_hit.get("pageURL"))

        out_filename = f"pixabay_{video_id}_{best_res_name}.mp4"
        out_path = self.cache_dir / out_filename

        # Download if not present
        if not out_path.exists() or out_path.stat().st_size < 10000:
            logger.info(f"Downloading moving video for '{clean_query}' ({best_hit.get('tags')}) -> {out_filename}...")
            dl_req = urllib.request.Request(best_video_url, headers={"User-Agent": "Mozilla/5.0"})
            try:
                with urllib.request.urlopen(dl_req, timeout=30.0) as dl_resp, open(out_path, "wb") as f:
                    f.write(dl_resp.read())
            except Exception as e:
                logger.warning(f"Failed to download video from {best_video_url}: {e}")
                return None

        # Save metadata cache
        meta_data = {
            "query": clean_query,
            "video_id": video_id,
            "file_path": str(out_path),
            "tags": best_hit.get("tags", ""),
            "duration": best_hit.get("duration", 0),
            "page_url": best_hit.get("pageURL", ""),
            "attribution": f"Pixabay Video #{video_id} by {best_hit.get('user', 'Pixabay Creator')} (Pixabay License / Free for Commercial Use)",
        }
        meta_file.write_text(json.dumps(meta_data, indent=2), encoding="utf-8")
        logger.info(f"Moving video acquired successfully for '{clean_query}': {out_path.name} ({meta_data['duration']}s)")
        return out_path

    def search_and_download_photo(
        self,
        query: str,
        orientation: str = "vertical",
    ) -> Optional[Path]:
        """Search Pixabay for high-resolution photo with negative keyword filtering."""
        if not self.api_key:
            return None

        clean_query = query.strip()
        if not clean_query:
            return None

        cache_key = hashlib.md5(f"photo_{clean_query.lower()}_{orientation}".encode("utf-8")).hexdigest()
        out_path = self.cache_dir / f"pixabay_photo_{cache_key}.jpg"
        if out_path.exists() and out_path.stat().st_size > 10000:
            return out_path

        params = {
            "key": self.api_key,
            "q": clean_query,
            "image_type": "photo",
            "orientation": orientation,
            "per_page": 10,
        }
        url = f"https://pixabay.com/api/?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"User-Agent": "MhidePhotoIntelligence/2.0"})

        try:
            with urllib.request.urlopen(req, timeout=12.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.warning(f"Pixabay photo search error for query '{clean_query}': {e}")
            return None

        hits = data.get("hits", [])
        if not hits:
            # Fallback to any orientation
            if orientation == "vertical":
                return self.search_and_download_photo(query=query, orientation="all")
            return None

        forbidden_terms = {"city", "resort", "cars", "tourists", "hotel", "happy"}
        best_hit = None
        for hit in hits:
            tags = (hit.get("tags") or "").lower()
            if not any(f in tags for f in forbidden_terms):
                best_hit = hit
                break

        if not best_hit:
            best_hit = hits[0]

        img_url = best_hit.get("largeImageURL") or best_hit.get("webformatURL")
        if not img_url:
            return None

        dl_req = urllib.request.Request(img_url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(dl_req, timeout=20.0) as dl_resp, open(out_path, "wb") as f:
                f.write(dl_resp.read())
            if out_path.exists() and out_path.stat().st_size > 5000:
                logger.info(f"Photo acquired successfully for '{clean_query}': {out_path.name}")
                return out_path
        except Exception as e:
            logger.warning(f"Failed to download photo from {img_url}: {e}")

        return None


# Global client singleton
pixabay_video_client = PixabayVideoClient()
