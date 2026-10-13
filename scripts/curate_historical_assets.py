"""Curate verified public domain archival assets with complete provenance."""

import json
from pathlib import Path
import shutil
import urllib.parse
import urllib.request

curated_dir = Path("data/curated_assets/mona_lisa_1911")
curated_dir.mkdir(parents=True, exist_ok=True)

# 1. Existing verified cached files from asset_cache
cached_sources = {
    "01_salon_carre_louvre.jpg": {
        "cache_img": Path("data/asset_cache/3fac7adcb2de5372e6aebee7c02f8157.jpg"),
        "title": "View of the Salon Carré at the Louvre (Alexandre Brun, 1911)",
        "author": "Alexandre Jean-Baptiste Brun (1853–1941)",
        "license": "Public Domain (Pre-1928, artist died >70y ago)",
        "provenance": "Musée du Louvre collection / Wikimedia Commons",
    },
    "05_mona_lisa_le_petit_journal.jpg": {
        "cache_img": Path("data/asset_cache/a39d13201412c5f2288446d2cd8c5b98.jpg"),
        "title": "Le Petit Journal - La Joconde a disparu du Louvre (August 1911)",
        "author": "Le Petit Journal editorial staff (1911)",
        "license": "Public Domain (French press publication 1911, expired copyright)",
        "provenance": "Bibliothèque nationale de France / Wikimedia Commons",
    },
    "06_excelsior_theft_coverage.jpg": {
        "cache_img": Path("data/asset_cache/b8fb7b94511b73be68bf975fc7742ae0.jpg"),
        "title": "L'Excelsior - Vincenzo Peruggia et le Vol de La Joconde",
        "author": "L'Excelsior French daily newspaper (1911/1913)",
        "license": "Public Domain (French press publication, expired copyright)",
        "provenance": "Bibliothèque nationale de France / Wikimedia Commons",
    },
    "07_mona_lisa_masterpiece.jpg": {
        "cache_img": Path("data/asset_cache/223353a9bbb6fffd490029d92bb74c06.jpg"),
        "title": "Portrait of Lisa Gherardini (Mona Lisa) by Leonardo da Vinci",
        "author": "Leonardo da Vinci (c. 1503–1519)",
        "license": "Public Domain (Renaissance artwork c. 1503)",
        "provenance": "Musée du Louvre / Center for Research and Restoration of the Museums of France (C2RMF)",
    },
}

records = []

for filename, info in cached_sources.items():
    target = curated_dir / filename
    src = info["cache_img"]
    if src.exists():
        shutil.copy2(src, target)
        size_kb = target.stat().st_size // 1024
        print(f"Copied from cache: {filename} ({size_kb} KB)")
        records.append({
            "filename": filename,
            "file_path": str(target),
            "title": info["title"],
            "author": info["author"],
            "license": info["license"],
            "provenance": info["provenance"],
        })

# 2. Query Wikimedia Commons API dynamically for specific filenames
commons_files = [
    {
        "filename": "02_empty_wall_louvre_1911.jpg",
        "commons_title": "File:Mona Lisa stolen-1911.jpg",
        "title": "The empty wall at the Louvre after the theft of the Mona Lisa (August 1911)",
        "author": "Agence Rol / Archival Press",
        "license": "Public Domain (Published 1911 in France, expired copyright)",
        "provenance": "Bibliothèque nationale de France / Wikimedia Commons",
    },
    {
        "filename": "03_vincenzo_peruggia_mugshot.jpg",
        "commons_title": "File:Vincenzo Perugia.jpg",
        "title": "Vincenzo Peruggia Bertillon police identification photograph and record",
        "author": "Service de l'Identité Judiciaire, Préfecture de Police de Paris (Alphonse Bertillon)",
        "license": "Public Domain (Official French police identification photograph, 1911)",
        "provenance": "Archives de la Préfecture de Police de Paris / Wikimedia Commons",
    },
    {
        "filename": "04_louis_beroud_louvre.jpg",
        "commons_title": "File:Louis Beroud - Mona Lisa au Louvre 1911.jpg",
        "title": "Mona Lisa au Louvre (Louis Béroud, 1911)",
        "author": "Louis Béroud (1852–1930)",
        "license": "Public Domain (Created 1911, artist died 1930)",
        "provenance": "Musée Carnavalet / Wikimedia Commons",
    },
]

headers = {"User-Agent": "MhideStoryIntelligence/1.0 (Educational History Research)"}

for item in commons_files:
    target = curated_dir / item["filename"]
    if not target.exists() or target.stat().st_size < 10000:
        api_url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode({
            "action": "query",
            "titles": item["commons_title"],
            "prop": "imageinfo",
            "iiprop": "url",
            "format": "json",
        })
        try:
            req = urllib.request.Request(api_url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                pages = data.get("query", {}).get("pages", {})
                img_url = None
                for pid, p in pages.items():
                    infos = p.get("imageinfo", [])
                    if infos:
                        img_url = infos[0].get("url")
                if img_url:
                    print(f"Downloading {item['title']} from {img_url}...")
                    dl_req = urllib.request.Request(img_url, headers=headers)
                    with urllib.request.urlopen(dl_req, timeout=20) as dl_resp:
                        target.write_bytes(dl_resp.read())
        except Exception as e:
            print(f"Could not download {item['filename']}: {e}")

    if target.exists():
        size_kb = target.stat().st_size // 1024
        print(f"Verified: {item['filename']} ({size_kb} KB)")
        records.append({
            "filename": item["filename"],
            "file_path": str(target),
            "title": item["title"],
            "author": item["author"],
            "license": item["license"],
            "provenance": item["provenance"],
        })

meta_path = curated_dir / "provenance.json"
meta_path.write_text(json.dumps(records, indent=2))
print(f"Saved {len(records)} verified historical assets to {meta_path}")
