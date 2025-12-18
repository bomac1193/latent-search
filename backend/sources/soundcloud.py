"""
SoundCloud integration for emerging/unreleased music.

Requires SOUNDCLOUD_CLIENT_ID environment variable.
SoundCloud is excellent for finding:
- Unreleased tracks
- Bedroom producers
- Pre-fame artists
- Remixes and bootlegs
"""
import os
import httpx
from dataclasses import dataclass
from typing import Optional


@dataclass
class SoundCloudTrack:
    """A track found on SoundCloud."""
    id: str
    title: str
    artist: str
    url: str
    plays: int
    likes: int
    duration: int  # seconds
    genre: Optional[str] = None
    bpm: Optional[float] = None
    artwork_url: Optional[str] = None
    embed_url: Optional[str] = None
    source: str = "soundcloud"


# Get client ID from environment
SOUNDCLOUD_CLIENT_ID = os.getenv("SOUNDCLOUD_CLIENT_ID", "")


async def search_soundcloud(
    query: str,
    limit: int = 20,
    client_id: Optional[str] = None
) -> list[SoundCloudTrack]:
    """
    Search SoundCloud for tracks.

    Args:
        query: Search term
        limit: Maximum results (max 50 per API)
        client_id: Optional client ID override

    Returns:
        List of SoundCloudTrack objects
    """
    cid = client_id or SOUNDCLOUD_CLIENT_ID
    if not cid:
        print("[DEBUG] SoundCloud: No client ID configured")
        return []

    tracks: list[SoundCloudTrack] = []

    try:
        url = "https://api-v2.soundcloud.com/search/tracks"
        params = {
            "q": query,
            "limit": min(limit, 50),
            "client_id": cid,
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, timeout=5.0)
            response.raise_for_status()
            data = response.json()

        for item in data.get("collection", []):
            # Get high-res artwork
            artwork_url = None
            if item.get("artwork_url"):
                artwork_url = item["artwork_url"].replace("-large", "-t500x500")

            # Create embed URL
            permalink = item.get("permalink_url", "")
            embed_url = None
            if permalink:
                embed_url = f"https://w.soundcloud.com/player/?url={permalink}&auto_play=false&hide_related=true"

            track = SoundCloudTrack(
                id=f"sc_{item.get('id', '')}",
                title=item.get("title", "Unknown"),
                artist=item.get("user", {}).get("username", "Unknown Artist"),
                url=permalink,
                plays=item.get("playback_count", 0),
                likes=item.get("likes_count", 0),
                duration=item.get("duration", 0) // 1000,
                genre=item.get("genre"),
                bpm=item.get("bpm"),
                artwork_url=artwork_url,
                embed_url=embed_url,
            )
            tracks.append(track)

    except Exception as e:
        print(f"[DEBUG] SoundCloud search failed: {e}")

    return tracks


async def get_soundcloud_underground(
    genre: str,
    limit: int = 20,
    max_plays: int = 10000,
    client_id: Optional[str] = None
) -> list[SoundCloudTrack]:
    """
    Find underground tracks on SoundCloud.

    Filters for low play counts to find undiscovered music.

    Args:
        genre: Genre to search
        limit: Maximum results
        max_plays: Maximum play count (lower = more underground)
        client_id: Optional client ID override

    Returns:
        List of SoundCloudTrack objects with low play counts
    """
    # Search with genre-specific terms
    search_terms = [
        f"{genre} underground",
        f"{genre} bedroom",
        f"{genre} demo",
        f"{genre} unreleased",
    ]

    all_tracks: list[SoundCloudTrack] = []

    for term in search_terms:
        tracks = await search_soundcloud(term, limit=limit, client_id=client_id)
        # Filter by play count
        underground = [t for t in tracks if t.plays <= max_plays]
        all_tracks.extend(underground)

        if len(all_tracks) >= limit:
            break

    # Deduplicate by ID
    seen = set()
    unique_tracks = []
    for t in all_tracks:
        if t.id not in seen:
            seen.add(t.id)
            unique_tracks.append(t)

    return unique_tracks[:limit]


def compute_shadow_score(track: SoundCloudTrack) -> float:
    """
    Compute shadow/rarity score for a SoundCloud track.

    Lower plays = higher shadow score.
    """
    import math

    if track.plays <= 0:
        return 1.0

    # Log scale: 1M plays = ~0.14, 1K plays = ~0.57, 100 plays = ~0.71
    log_plays = math.log10(track.plays + 1)
    shadow = 1.0 - (log_plays / 7.0)  # 7 = log10(10M)

    return max(0.0, min(1.0, shadow))
