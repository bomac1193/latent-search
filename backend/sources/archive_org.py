"""
Internet Archive (archive.org) integration.

The Internet Archive has a massive collection of free, legal music including:
- Free Music Archive collection
- Live concert recordings (etree)
- Netlabels and underground releases
- Historical recordings

No API key required - completely open.
"""

import httpx
from dataclasses import dataclass
from typing import Optional
import urllib.parse


@dataclass
class ArchiveTrack:
    id: str
    title: str
    artist: str
    url: str
    artwork_url: Optional[str]
    collection: str  # Which archive collection (etree, audio, netlabels, etc.)
    year: Optional[int]
    downloads: int  # Number of downloads
    description: Optional[str]
    embed_url: Optional[str] = None  # Archive.org embed player URL


# Collections with underground/experimental music
MUSIC_COLLECTIONS = [
    "audio",                    # General audio
    "etree",                    # Live concert recordings
    "netlabels",                # Netlabel releases (very underground)
    "opensource_audio",         # Open source music
    "audio_music",              # Music specifically
    "electronicmusic",          # Electronic music
    "freemusicarchive",         # Free Music Archive
]


async def search_archive(
    query: str,
    limit: int = 20,
    collection: Optional[str] = None
) -> list[ArchiveTrack]:
    """
    Search Internet Archive for music.

    Args:
        query: Search query
        limit: Max results
        collection: Specific collection to search (or None for all music)

    Returns:
        List of ArchiveTrack objects
    """
    tracks = []

    try:
        # Build the search query
        # mediatype:audio ensures we get audio files
        search_parts = [f"({query})", "mediatype:audio"]

        if collection:
            search_parts.append(f"collection:{collection}")
        else:
            # Search across multiple music collections
            collections_query = " OR ".join([f"collection:{c}" for c in MUSIC_COLLECTIONS])
            search_parts.append(f"({collections_query})")

        full_query = " AND ".join(search_parts)

        params = {
            "q": full_query,
            "output": "json",
            "rows": limit,
            "fl[]": ["identifier", "title", "creator", "collection", "year", "downloads", "description"],
            "sort[]": "downloads desc",  # Sort by popularity
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            url = "https://archive.org/advancedsearch.php"
            resp = await client.get(url, params=params)

            if resp.status_code != 200:
                print(f"[archive] Search failed: {resp.status_code}")
                return []

            data = resp.json()
            docs = data.get("response", {}).get("docs", [])

            for doc in docs:
                identifier = doc.get("identifier", "")
                if not identifier:
                    continue

                # Build URLs
                item_url = f"https://archive.org/details/{identifier}"
                # Archive.org thumbnail format
                artwork_url = f"https://archive.org/services/img/{identifier}"

                # Get collection (might be a list)
                collection_val = doc.get("collection", [])
                if isinstance(collection_val, list):
                    collection_str = collection_val[0] if collection_val else "audio"
                else:
                    collection_str = collection_val

                # Parse year
                year = doc.get("year")
                if isinstance(year, list):
                    year = year[0] if year else None
                try:
                    year = int(year) if year else None
                except (ValueError, TypeError):
                    year = None

                # Archive.org embed player URL
                embed_url = f"https://archive.org/embed/{identifier}"

                track = ArchiveTrack(
                    id=f"archive_{identifier}",
                    title=doc.get("title", "Untitled"),
                    artist=doc.get("creator", "Unknown Artist"),
                    url=item_url,
                    artwork_url=artwork_url,
                    collection=collection_str,
                    year=year,
                    downloads=doc.get("downloads", 0),
                    description=doc.get("description", "")[:200] if doc.get("description") else None,
                    embed_url=embed_url,
                )
                tracks.append(track)

        print(f"[archive] Found {len(tracks)} items for '{query}'")

    except Exception as e:
        print(f"[archive] Error searching: {e}")

    return tracks


async def get_netlabel_releases(
    query: str = "",
    limit: int = 20
) -> list[ArchiveTrack]:
    """
    Get releases from netlabels - truly underground electronic music.
    Netlabels are internet-based record labels that release music for free.
    """
    search_query = query if query else "*"
    return await search_archive(search_query, limit=limit, collection="netlabels")


async def get_live_recordings(
    artist: str,
    limit: int = 20
) -> list[ArchiveTrack]:
    """
    Get live concert recordings from the etree collection.
    Huge archive of live shows, often from underground/jam bands.
    """
    return await search_archive(artist, limit=limit, collection="etree")


async def get_experimental_music(
    query: str = "experimental",
    limit: int = 20
) -> list[ArchiveTrack]:
    """
    Search for experimental/avant-garde music.
    """
    enhanced_query = f"{query} (experimental OR avant-garde OR noise OR ambient OR drone)"
    return await search_archive(enhanced_query, limit=limit)


async def get_underground_by_genre(
    genre: str,
    limit: int = 20,
    max_downloads: int = 1000
) -> list[ArchiveTrack]:
    """
    Get underground tracks by genre - low download counts = more obscure.
    """
    # Search for genre
    tracks = await search_archive(genre, limit=limit * 3)

    # Filter to low-download items
    underground = [t for t in tracks if t.downloads < max_downloads]

    # Sort by downloads ascending (most obscure first)
    underground.sort(key=lambda t: t.downloads)

    print(f"[archive] Found {len(underground)} underground tracks (< {max_downloads} downloads)")

    return underground[:limit]


async def get_african_archive(
    query: str = "",
    limit: int = 20
) -> list[ArchiveTrack]:
    """
    Search for African music in the archive.
    """
    african_terms = "african OR africa OR afrobeat OR highlife OR mbira OR kora OR congo OR ethiopian OR malian"
    if query:
        search_query = f"({query}) AND ({african_terms})"
    else:
        search_query = african_terms

    return await search_archive(search_query, limit=limit)
