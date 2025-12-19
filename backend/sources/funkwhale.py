"""
Funkwhale Source.

Funkwhale is a federated, self-hosted music platform (like Mastodon for music).
It uses ActivityPub protocol, meaning multiple instances can share content.

This is truly underground - music hosted by individuals and small communities.
"""

import aiohttp
import asyncio
from dataclasses import dataclass
from typing import Optional
import hashlib


@dataclass
class FunkwhaleTrack:
    id: str
    title: str
    artist: str
    url: str
    instance: str
    album: Optional[str]
    plays: Optional[int]
    duration: int
    genre: Optional[str]
    artwork_url: Optional[str] = None
    embed_url: Optional[str] = None
    stream_url: Optional[str] = None
    source: str = "funkwhale"


# Known public Funkwhale instances
# These are community-run servers with public libraries
FUNKWHALE_INSTANCES = [
    "https://open.audio",           # Largest public instance
    "https://funkwhale.juniorjpdj.pl",
    "https://audio.liberta.vip",
    "https://funk.libraryofbabel.info",
    "https://audio.gafam.fr",
    "https://tanukitunes.com",
    "https://funkwhale.thurk.org",
    "https://music.chosto.me",
]


async def search_funkwhale_instance(
    instance: str,
    query: str,
    limit: int = 20
) -> list[FunkwhaleTrack]:
    """
    Search a single Funkwhale instance.
    """
    tracks = []

    # Funkwhale API endpoint
    search_url = f"{instance}/api/v1/tracks/"

    headers = {
        "User-Agent": "LatentSearch/1.0",
        "Accept": "application/json",
    }

    params = {
        "q": query,
        "page_size": limit,
        "ordering": "-creation_date",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                search_url,
                headers=headers,
                params=params,
                timeout=10
            ) as resp:
                if resp.status != 200:
                    return []

                data = await resp.json()
                results = data.get("results", [])

                for track in results:
                    track_id = track.get("id")
                    artist_info = track.get("artist", {})
                    album_info = track.get("album", {})

                    # Build URLs
                    track_url = f"{instance}/library/tracks/{track_id}"
                    listen_url = track.get("listen_url")

                    if listen_url and not listen_url.startswith("http"):
                        listen_url = f"{instance}{listen_url}"

                    # Get artwork
                    artwork = None
                    if album_info.get("cover"):
                        cover = album_info["cover"]
                        if isinstance(cover, dict):
                            artwork = cover.get("urls", {}).get("medium_square_crop")
                        elif isinstance(cover, str):
                            artwork = cover
                        if artwork and not artwork.startswith("http"):
                            artwork = f"{instance}{artwork}"

                    # Get embed URL
                    embed_url = f"{instance}/embed.html?&type=track&id={track_id}"

                    tracks.append(FunkwhaleTrack(
                        id=f"funkwhale_{instance.split('//')[1].split('.')[0]}_{track_id}",
                        title=track.get("title", "Unknown"),
                        artist=artist_info.get("name", "Unknown Artist"),
                        url=track_url,
                        instance=instance,
                        album=album_info.get("title"),
                        plays=track.get("downloads_count", 0),
                        duration=track.get("duration", 0),
                        genre=None,  # Funkwhale uses tags, will extract below
                        artwork_url=artwork,
                        embed_url=embed_url,
                        stream_url=listen_url,
                    ))

    except asyncio.TimeoutError:
        print(f"[funkwhale] Timeout for {instance}")
    except Exception as e:
        print(f"[funkwhale] Error searching {instance}: {e}")

    return tracks


async def search_funkwhale_by_tag(
    instance: str,
    tag: str,
    limit: int = 20
) -> list[FunkwhaleTrack]:
    """
    Search a Funkwhale instance by tag/genre.
    """
    tracks = []

    # Tag-based search
    search_url = f"{instance}/api/v1/tracks/"

    headers = {
        "User-Agent": "LatentSearch/1.0",
        "Accept": "application/json",
    }

    params = {
        "tag": tag,
        "page_size": limit,
        "ordering": "-creation_date",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                search_url,
                headers=headers,
                params=params,
                timeout=10
            ) as resp:
                if resp.status != 200:
                    return []

                data = await resp.json()
                results = data.get("results", [])

                for track in results:
                    track_id = track.get("id")
                    artist_info = track.get("artist", {})
                    album_info = track.get("album", {})

                    track_url = f"{instance}/library/tracks/{track_id}"
                    listen_url = track.get("listen_url")

                    if listen_url and not listen_url.startswith("http"):
                        listen_url = f"{instance}{listen_url}"

                    artwork = None
                    if album_info.get("cover"):
                        cover = album_info["cover"]
                        if isinstance(cover, dict):
                            artwork = cover.get("urls", {}).get("medium_square_crop")
                        elif isinstance(cover, str):
                            artwork = cover
                        if artwork and not artwork.startswith("http"):
                            artwork = f"{instance}{artwork}"

                    embed_url = f"{instance}/embed.html?&type=track&id={track_id}"

                    tracks.append(FunkwhaleTrack(
                        id=f"funkwhale_{instance.split('//')[1].split('.')[0]}_{track_id}",
                        title=track.get("title", "Unknown"),
                        artist=artist_info.get("name", "Unknown Artist"),
                        url=track_url,
                        instance=instance,
                        album=album_info.get("title"),
                        plays=track.get("downloads_count", 0),
                        duration=track.get("duration", 0),
                        genre=tag,
                        artwork_url=artwork,
                        embed_url=embed_url,
                        stream_url=listen_url,
                    ))

    except Exception as e:
        print(f"[funkwhale] Tag search error for {instance}: {e}")

    return tracks


async def search_funkwhale(query: str, limit: int = 20) -> list[FunkwhaleTrack]:
    """
    Search across all known Funkwhale instances.
    """
    # Search multiple instances concurrently
    tasks = [
        search_funkwhale_instance(instance, query, limit // len(FUNKWHALE_INSTANCES) + 2)
        for instance in FUNKWHALE_INSTANCES[:5]  # Limit to top 5 instances
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_tracks = []
    for result in results:
        if isinstance(result, list):
            all_tracks.extend(result)

    # Sort by recency/plays
    all_tracks.sort(key=lambda t: t.plays or 0, reverse=True)

    print(f"[funkwhale] Found {len(all_tracks)} tracks across instances")

    return all_tracks[:limit]


async def get_funkwhale_underground(genre: str, limit: int = 20) -> list[FunkwhaleTrack]:
    """
    Find underground music on Funkwhale by genre.
    Uses both search and tag-based discovery.
    """
    # Map common genres to Funkwhale tags
    genre_tags = {
        "electronic": ["electronic", "synth", "edm", "techno", "house"],
        "ambient": ["ambient", "drone", "atmospheric"],
        "experimental": ["experimental", "noise", "avantgarde"],
        "hip hop": ["hiphop", "rap", "beats"],
        "rock": ["rock", "indie", "alternative"],
        "jazz": ["jazz", "fusion"],
        "folk": ["folk", "acoustic"],
        "metal": ["metal", "heavy"],
    }

    genre_lower = genre.lower()
    tags = [genre_lower]

    # Find matching tags
    for key, tag_list in genre_tags.items():
        if key in genre_lower or genre_lower in key:
            tags.extend(tag_list)

    tags = list(set(tags))[:3]

    print(f"[funkwhale] Searching with tags: {tags}")

    all_tracks = []

    # Search by tags across instances
    for tag in tags:
        for instance in FUNKWHALE_INSTANCES[:3]:
            tracks = await search_funkwhale_by_tag(instance, tag, limit // (len(tags) * 3) + 1)
            all_tracks.extend(tracks)
            await asyncio.sleep(0.2)

    # Also do text search
    text_tracks = await search_funkwhale(genre, limit // 2)
    all_tracks.extend(text_tracks)

    # Deduplicate
    seen = set()
    unique = []
    for t in all_tracks:
        key = f"{t.artist.lower()}|{t.title.lower()}"
        if key not in seen:
            seen.add(key)
            if not t.genre:
                t.genre = genre
            unique.append(t)

    return unique[:limit]


async def get_instance_library(instance: str, limit: int = 50) -> list[FunkwhaleTrack]:
    """
    Get all tracks from a specific Funkwhale instance.
    Useful for exploring what a community has uploaded.
    """
    tracks = []

    url = f"{instance}/api/v1/tracks/"

    headers = {
        "User-Agent": "LatentSearch/1.0",
        "Accept": "application/json",
    }

    params = {
        "page_size": limit,
        "ordering": "-creation_date",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params, timeout=15) as resp:
                if resp.status != 200:
                    return []

                data = await resp.json()
                results = data.get("results", [])

                for track in results:
                    track_id = track.get("id")
                    artist_info = track.get("artist", {})
                    album_info = track.get("album", {})

                    track_url = f"{instance}/library/tracks/{track_id}"
                    listen_url = track.get("listen_url")
                    if listen_url and not listen_url.startswith("http"):
                        listen_url = f"{instance}{listen_url}"

                    artwork = None
                    if album_info.get("cover"):
                        cover = album_info["cover"]
                        if isinstance(cover, dict):
                            artwork = cover.get("urls", {}).get("medium_square_crop")
                        if artwork and not artwork.startswith("http"):
                            artwork = f"{instance}{artwork}"

                    embed_url = f"{instance}/embed.html?&type=track&id={track_id}"

                    # Get tags
                    tags = track.get("tags", [])
                    genre = tags[0] if tags else None

                    tracks.append(FunkwhaleTrack(
                        id=f"funkwhale_{instance.split('//')[1].split('.')[0]}_{track_id}",
                        title=track.get("title", "Unknown"),
                        artist=artist_info.get("name", "Unknown Artist"),
                        url=track_url,
                        instance=instance,
                        album=album_info.get("title"),
                        plays=track.get("downloads_count", 0),
                        duration=track.get("duration", 0),
                        genre=genre,
                        artwork_url=artwork,
                        embed_url=embed_url,
                        stream_url=listen_url,
                    ))

    except Exception as e:
        print(f"[funkwhale] Library fetch error: {e}")

    return tracks
