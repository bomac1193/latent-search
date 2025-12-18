"""
Audiomack integration.

Audiomack is huge in Africa (Nigeria, Ghana, Kenya) and has a strong
underground hip-hop scene. Great for discovering African artists
invisible to Western algorithms.

Note: Their official API requires OAuth 1.0a registration.
This uses their public web endpoints instead.
"""

import httpx
from dataclasses import dataclass
from typing import Optional
from bs4 import BeautifulSoup
import re
import json


@dataclass
class AudiomackTrack:
    id: str
    title: str
    artist: str
    url: str
    artwork_url: Optional[str]
    genre: Optional[str]
    plays: int
    country: Optional[str]  # Artist's country if available


# Audiomack genres with strong African presence
AFRICAN_GENRES = [
    "afrobeats",
    "afropop",
    "afro-house",
    "amapiano",
    "highlife",
    "afro-soul",
    "naija",
    "bongo-flava",
    "gqom",
    "gengetone",
    "afro-fusion",
]


async def search_audiomack(
    query: str,
    limit: int = 20
) -> list[AudiomackTrack]:
    """
    Search Audiomack for tracks.

    Args:
        query: Search query
        limit: Max results

    Returns:
        List of AudiomackTrack objects
    """
    tracks = []

    try:
        # Use Audiomack's web search
        search_url = f"https://audiomack.com/search?q={query}"

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(search_url, headers=headers)

            if resp.status_code != 200:
                print(f"[audiomack] Search failed: {resp.status_code}")
                return []

            soup = BeautifulSoup(resp.text, "html.parser")

            # Look for JSON data in script tags (Next.js/React apps often embed this)
            scripts = soup.find_all("script", type="application/json")
            for script in scripts:
                try:
                    data = json.loads(script.string)
                    # Try to extract track data from various possible structures
                    tracks.extend(_extract_tracks_from_json(data, limit))
                except (json.JSONDecodeError, TypeError):
                    continue

            # Also try parsing HTML directly
            if not tracks:
                tracks = _parse_audiomack_html(soup, limit)

        print(f"[audiomack] Found {len(tracks)} tracks for '{query}'")

    except Exception as e:
        print(f"[audiomack] Error searching: {e}")

    return tracks[:limit]


def _extract_tracks_from_json(data: dict, limit: int) -> list[AudiomackTrack]:
    """Extract tracks from Audiomack's embedded JSON data."""
    tracks = []

    def recurse(obj, depth=0):
        if depth > 10 or len(tracks) >= limit:
            return

        if isinstance(obj, dict):
            # Check if this looks like a track object
            if "title" in obj and ("artist" in obj or "uploader" in obj):
                track = _parse_track_object(obj)
                if track:
                    tracks.append(track)
            else:
                for v in obj.values():
                    recurse(v, depth + 1)
        elif isinstance(obj, list):
            for item in obj:
                recurse(item, depth + 1)

    recurse(data)
    return tracks


def _parse_track_object(obj: dict) -> Optional[AudiomackTrack]:
    """Parse a track object from Audiomack's JSON."""
    try:
        title = obj.get("title", "")
        if not title:
            return None

        artist = obj.get("artist", obj.get("uploader", {}).get("name", "Unknown"))
        if isinstance(artist, dict):
            artist = artist.get("name", "Unknown")

        url_slug = obj.get("url_slug", obj.get("slug", ""))
        artist_slug = obj.get("artist_url_slug", obj.get("uploader", {}).get("url_slug", ""))

        if url_slug and artist_slug:
            url = f"https://audiomack.com/{artist_slug}/song/{url_slug}"
        else:
            url = f"https://audiomack.com/search?q={title}"

        artwork = obj.get("image", obj.get("image_base", ""))
        if artwork and not artwork.startswith("http"):
            artwork = f"https://assets.audiomack.com/default-song-image.png"

        return AudiomackTrack(
            id=f"am_{obj.get('id', hash(title))}",
            title=title,
            artist=artist if isinstance(artist, str) else str(artist),
            url=url,
            artwork_url=artwork if artwork else None,
            genre=obj.get("genre", obj.get("genre_name")),
            plays=obj.get("plays", 0),
            country=obj.get("uploader", {}).get("country") if isinstance(obj.get("uploader"), dict) else None,
        )
    except Exception:
        return None


def _parse_audiomack_html(soup: BeautifulSoup, limit: int) -> list[AudiomackTrack]:
    """Parse tracks from Audiomack HTML as fallback."""
    tracks = []

    # Look for song links
    song_links = soup.find_all("a", href=re.compile(r"/[^/]+/song/[^/]+"))

    for link in song_links[:limit]:
        try:
            href = link.get("href", "")
            title_elem = link.find(class_=re.compile(r"title|name", re.I))
            artist_elem = link.find(class_=re.compile(r"artist|author", re.I))

            title = title_elem.get_text(strip=True) if title_elem else link.get_text(strip=True)
            artist = artist_elem.get_text(strip=True) if artist_elem else "Unknown"

            if not title or len(title) < 2:
                continue

            # Get artwork from nearby img
            img = link.find("img")
            artwork = img.get("src") if img else None

            tracks.append(AudiomackTrack(
                id=f"am_{hash(href)}",
                title=title,
                artist=artist,
                url=f"https://audiomack.com{href}" if href.startswith("/") else href,
                artwork_url=artwork,
                genre=None,
                plays=0,
                country=None,
            ))
        except Exception:
            continue

    return tracks


async def get_african_trending(limit: int = 20) -> list[AudiomackTrack]:
    """
    Get trending African music on Audiomack.
    Focuses on genres popular in Africa.
    """
    all_tracks = []

    for genre in AFRICAN_GENRES[:3]:  # Top 3 genres to avoid too many requests
        tracks = await search_audiomack(genre, limit=limit // 3)
        all_tracks.extend(tracks)

    # Remove duplicates by ID
    seen = set()
    unique = []
    for t in all_tracks:
        if t.id not in seen:
            seen.add(t.id)
            unique.append(t)

    return unique[:limit]


async def search_african_artists(
    query: str,
    limit: int = 20
) -> list[AudiomackTrack]:
    """
    Search specifically for African artists matching query.
    Combines query with African genre keywords.
    """
    # Add African genre context to search
    enhanced_queries = [
        f"{query} afrobeats",
        f"{query} amapiano",
        f"{query} african",
    ]

    all_tracks = []
    for q in enhanced_queries:
        tracks = await search_audiomack(q, limit=limit // 2)
        all_tracks.extend(tracks)

    # Remove duplicates
    seen = set()
    unique = []
    for t in all_tracks:
        if t.id not in seen:
            seen.add(t.id)
            unique.append(t)

    return unique[:limit]
