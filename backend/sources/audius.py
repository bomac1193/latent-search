"""
Audius API integration.

Audius is a decentralized music streaming platform - great for Web3/underground artists.
API is free with no rate limits.
"""

import httpx
from dataclasses import dataclass
from typing import Optional
import random


@dataclass
class AudiusTrack:
    id: str
    title: str
    artist: str
    url: str
    artwork_url: Optional[str]
    genre: Optional[str]
    plays: int
    duration: int  # seconds
    is_downloadable: bool


# Audius API hosts - select one at random for load balancing
AUDIUS_API_HOSTS = [
    "https://discoveryprovider.audius.co",
    "https://discoveryprovider2.audius.co",
    "https://discoveryprovider3.audius.co",
    "https://dn1.monophonic.digital",
    "https://audius-dp.amsterdam.creatorseed.com",
]

APP_NAME = "latent-search"


async def get_api_host() -> str:
    """Get a working Audius API host."""
    # Try the official endpoint first to get recommended hosts
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get("https://api.audius.co")
            if resp.status_code == 200:
                data = resp.json()
                if data.get("data"):
                    return random.choice(data["data"])
    except Exception:
        pass

    # Fallback to hardcoded hosts
    return random.choice(AUDIUS_API_HOSTS)


async def search_audius(
    query: str,
    limit: int = 20,
    genre_filter: Optional[str] = None
) -> list[AudiusTrack]:
    """
    Search Audius for tracks.

    Args:
        query: Search query (artist, genre, track name)
        limit: Max results to return
        genre_filter: Optional genre to filter by

    Returns:
        List of AudiusTrack objects
    """
    tracks = []

    try:
        host = await get_api_host()

        params = {
            "query": query,
            "app_name": APP_NAME,
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            url = f"{host}/v1/tracks/search"
            resp = await client.get(url, params=params)

            if resp.status_code != 200:
                print(f"[audius] Search failed: {resp.status_code}")
                return []

            data = resp.json()
            results = data.get("data", [])

            for item in results[:limit]:
                # Extract artist info
                user = item.get("user", {})
                artist_name = user.get("name", "Unknown Artist")
                artist_handle = user.get("handle", "")

                # Build track URL
                track_url = f"https://audius.co/{artist_handle}/{item.get('permalink', item.get('id'))}"

                # Get artwork
                artwork = None
                if item.get("artwork", {}).get("480x480"):
                    artwork = item["artwork"]["480x480"]
                elif item.get("artwork", {}).get("150x150"):
                    artwork = item["artwork"]["150x150"]

                # Genre filtering
                track_genre = item.get("genre", "")
                if genre_filter and genre_filter.lower() not in track_genre.lower():
                    continue

                track = AudiusTrack(
                    id=f"audius_{item.get('id', '')}",
                    title=item.get("title", "Untitled"),
                    artist=artist_name,
                    url=track_url,
                    artwork_url=artwork,
                    genre=track_genre if track_genre else None,
                    plays=item.get("play_count", 0),
                    duration=item.get("duration", 0),
                    is_downloadable=item.get("downloadable", False),
                )
                tracks.append(track)

        print(f"[audius] Found {len(tracks)} tracks for '{query}'")

    except Exception as e:
        print(f"[audius] Error searching: {e}")

    return tracks


async def get_trending_audius(
    genre: Optional[str] = None,
    limit: int = 20
) -> list[AudiusTrack]:
    """
    Get trending tracks on Audius.
    Great for discovering what's hot in the decentralized music scene.
    """
    tracks = []

    try:
        host = await get_api_host()

        params = {
            "app_name": APP_NAME,
            "limit": limit,
        }
        if genre:
            params["genre"] = genre

        async with httpx.AsyncClient(timeout=15.0) as client:
            url = f"{host}/v1/tracks/trending"
            resp = await client.get(url, params=params)

            if resp.status_code != 200:
                return []

            data = resp.json()
            results = data.get("data", [])

            for item in results:
                user = item.get("user", {})
                artist_name = user.get("name", "Unknown Artist")
                artist_handle = user.get("handle", "")

                track_url = f"https://audius.co/{artist_handle}/{item.get('permalink', item.get('id'))}"

                artwork = None
                if item.get("artwork", {}).get("480x480"):
                    artwork = item["artwork"]["480x480"]

                track = AudiusTrack(
                    id=f"audius_{item.get('id', '')}",
                    title=item.get("title", "Untitled"),
                    artist=artist_name,
                    url=track_url,
                    artwork_url=artwork,
                    genre=item.get("genre"),
                    plays=item.get("play_count", 0),
                    duration=item.get("duration", 0),
                    is_downloadable=item.get("downloadable", False),
                )
                tracks.append(track)

        print(f"[audius] Got {len(tracks)} trending tracks")

    except Exception as e:
        print(f"[audius] Error getting trending: {e}")

    return tracks


async def get_underground_audius(
    query: str,
    limit: int = 20,
    max_plays: int = 1000
) -> list[AudiusTrack]:
    """
    Get underground tracks - low play counts but matching query.
    These are the true shadow artists on Audius.
    """
    all_tracks = await search_audius(query, limit=limit * 3)

    # Filter to low-play tracks
    underground = [t for t in all_tracks if t.plays < max_plays]

    # Sort by plays ascending (lowest first = most underground)
    underground.sort(key=lambda t: t.plays)

    print(f"[audius] Found {len(underground)} underground tracks (< {max_plays} plays)")

    return underground[:limit]
