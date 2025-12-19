"""
Mixcloud Source.

Mixcloud is THE platform for DJ mixes, radio shows, and long-form audio.
Unlike Spotify/SoundCloud, it's designed for continuous mixes.

Great for discovering underground DJ sets and curated music selections.
"""

import aiohttp
import asyncio
from dataclasses import dataclass
from typing import Optional
import re


@dataclass
class MixcloudTrack:
    id: str
    title: str
    artist: str  # The DJ/uploader
    url: str
    plays: Optional[int]
    favorites: Optional[int]
    duration: int
    genre: Optional[str]
    tags: list[str]
    artwork_url: Optional[str] = None
    embed_url: Optional[str] = None
    source: str = "mixcloud"


# Mixcloud API (they have a public API!)
MIXCLOUD_API = "https://api.mixcloud.com"


async def search_mixcloud(query: str, limit: int = 20) -> list[MixcloudTrack]:
    """
    Search Mixcloud for mixes/shows.
    Uses Mixcloud's public API.
    """
    tracks = []

    search_url = f"{MIXCLOUD_API}/search/"

    params = {
        "q": query,
        "type": "cloudcast",  # Mixes/shows
        "limit": limit,
    }

    headers = {
        "User-Agent": "LatentSearch/1.0",
        "Accept": "application/json",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                search_url,
                params=params,
                headers=headers,
                timeout=15
            ) as resp:
                if resp.status != 200:
                    print(f"[mixcloud] Search returned {resp.status}")
                    return []

                data = await resp.json()
                results = data.get("data", [])

                for item in results:
                    # Extract key from URL
                    key = item.get("key", "")
                    if not key:
                        continue

                    # Get user/DJ info
                    user = item.get("user", {})
                    dj_name = user.get("name") or user.get("username", "Unknown DJ")

                    # Get pictures
                    pictures = item.get("pictures", {})
                    artwork = (
                        pictures.get("large") or
                        pictures.get("medium") or
                        pictures.get("small")
                    )

                    # Get tags
                    tags = [t.get("name", "") for t in item.get("tags", [])]

                    # Build embed URL
                    # Mixcloud widget: https://www.mixcloud.com/widget/iframe/?hide_cover=1&feed=KEY
                    embed_url = f"https://www.mixcloud.com/widget/iframe/?hide_cover=1&mini=1&feed={key}"

                    tracks.append(MixcloudTrack(
                        id=f"mixcloud_{key.replace('/', '_')}",
                        title=item.get("name", "Unknown Mix"),
                        artist=dj_name,
                        url=f"https://www.mixcloud.com{key}",
                        plays=item.get("play_count"),
                        favorites=item.get("favorite_count"),
                        duration=item.get("audio_length", 0),
                        genre=tags[0] if tags else None,
                        tags=tags,
                        artwork_url=artwork,
                        embed_url=embed_url,
                    ))

    except Exception as e:
        print(f"[mixcloud] Search error: {e}")

    return tracks


async def search_mixcloud_by_tag(tag: str, limit: int = 20) -> list[MixcloudTrack]:
    """
    Search Mixcloud by tag/genre.
    """
    tracks = []

    # Tag endpoint
    tag_url = f"{MIXCLOUD_API}/discover/{tag}/"

    params = {
        "limit": limit,
    }

    headers = {
        "User-Agent": "LatentSearch/1.0",
        "Accept": "application/json",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                tag_url,
                params=params,
                headers=headers,
                timeout=15
            ) as resp:
                if resp.status != 200:
                    # Try search instead
                    return await search_mixcloud(tag, limit)

                data = await resp.json()
                results = data.get("data", [])

                for item in results:
                    key = item.get("key", "")
                    if not key:
                        continue

                    user = item.get("user", {})
                    dj_name = user.get("name") or user.get("username", "Unknown DJ")

                    pictures = item.get("pictures", {})
                    artwork = pictures.get("large") or pictures.get("medium")

                    tags = [t.get("name", "") for t in item.get("tags", [])]

                    embed_url = f"https://www.mixcloud.com/widget/iframe/?hide_cover=1&mini=1&feed={key}"

                    tracks.append(MixcloudTrack(
                        id=f"mixcloud_{key.replace('/', '_')}",
                        title=item.get("name", "Unknown Mix"),
                        artist=dj_name,
                        url=f"https://www.mixcloud.com{key}",
                        plays=item.get("play_count"),
                        favorites=item.get("favorite_count"),
                        duration=item.get("audio_length", 0),
                        genre=tag,
                        tags=tags,
                        artwork_url=artwork,
                        embed_url=embed_url,
                    ))

    except Exception as e:
        print(f"[mixcloud] Tag search error: {e}")
        return await search_mixcloud(tag, limit)

    return tracks


async def get_mixcloud_underground(genre: str, limit: int = 20) -> list[MixcloudTrack]:
    """
    Find underground DJ mixes by genre.
    """
    # Map to Mixcloud tag slugs
    genre_tags = {
        "electronic": ["electronic", "electronica", "synth"],
        "house": ["deep-house", "house", "tech-house"],
        "techno": ["techno", "minimal-techno", "industrial-techno"],
        "ambient": ["ambient", "chillout", "downtempo"],
        "hip hop": ["hip-hop", "beats", "instrumental-hip-hop"],
        "dnb": ["drum-and-bass", "dnb", "jungle"],
        "dubstep": ["dubstep", "bass-music", "uk-bass"],
        "experimental": ["experimental", "avant-garde", "noise"],
        "disco": ["disco", "nu-disco", "italo-disco"],
        "jazz": ["jazz", "nu-jazz", "jazz-fusion"],
        "soul": ["soul", "funk", "neo-soul"],
        "african": ["afrobeats", "afro-house", "amapiano"],
        "latin": ["latin", "reggaeton", "salsa"],
        "world": ["world-music", "global-beats"],
    }

    genre_lower = genre.lower()
    search_tags = [genre_lower.replace(" ", "-")]

    for key, tags in genre_tags.items():
        if key in genre_lower or genre_lower in key:
            search_tags.extend(tags)

    search_tags = list(set(search_tags))[:3]

    print(f"[mixcloud] Searching tags: {search_tags}")

    all_tracks = []

    for tag in search_tags:
        tracks = await search_mixcloud_by_tag(tag, limit // len(search_tags) + 2)
        all_tracks.extend(tracks)
        await asyncio.sleep(0.3)

    # Sort by underground-ness (fewer plays = more underground)
    # But filter out zero plays (might be broken)
    underground = [t for t in all_tracks if t.plays and t.plays > 10]
    underground.sort(key=lambda t: t.plays or 0)

    # Deduplicate
    seen = set()
    unique = []
    for t in underground:
        if t.id not in seen:
            seen.add(t.id)
            if not t.genre:
                t.genre = genre
            unique.append(t)

    return unique[:limit]


async def get_mixcloud_new(limit: int = 20) -> list[MixcloudTrack]:
    """
    Get newly uploaded mixes.
    Fresh uploads are often more underground.
    """
    tracks = []

    # New uploads endpoint
    new_url = f"{MIXCLOUD_API}/new/"

    params = {
        "limit": limit,
    }

    headers = {
        "User-Agent": "LatentSearch/1.0",
        "Accept": "application/json",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                new_url,
                params=params,
                headers=headers,
                timeout=15
            ) as resp:
                if resp.status != 200:
                    return []

                data = await resp.json()
                results = data.get("data", [])

                for item in results:
                    key = item.get("key", "")
                    if not key:
                        continue

                    user = item.get("user", {})
                    dj_name = user.get("name") or user.get("username", "Unknown DJ")

                    pictures = item.get("pictures", {})
                    artwork = pictures.get("large") or pictures.get("medium")

                    tags = [t.get("name", "") for t in item.get("tags", [])]

                    embed_url = f"https://www.mixcloud.com/widget/iframe/?hide_cover=1&mini=1&feed={key}"

                    tracks.append(MixcloudTrack(
                        id=f"mixcloud_{key.replace('/', '_')}",
                        title=item.get("name", "Unknown Mix"),
                        artist=dj_name,
                        url=f"https://www.mixcloud.com{key}",
                        plays=item.get("play_count"),
                        favorites=item.get("favorite_count"),
                        duration=item.get("audio_length", 0),
                        genre=tags[0] if tags else None,
                        tags=tags,
                        artwork_url=artwork,
                        embed_url=embed_url,
                    ))

    except Exception as e:
        print(f"[mixcloud] New mixes error: {e}")

    return tracks


async def get_user_mixes(username: str, limit: int = 20) -> list[MixcloudTrack]:
    """
    Get mixes from a specific DJ/user.
    """
    tracks = []

    user_url = f"{MIXCLOUD_API}/{username}/cloudcasts/"

    params = {
        "limit": limit,
    }

    headers = {
        "User-Agent": "LatentSearch/1.0",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                user_url,
                params=params,
                headers=headers,
                timeout=15
            ) as resp:
                if resp.status != 200:
                    return []

                data = await resp.json()
                results = data.get("data", [])

                for item in results:
                    key = item.get("key", "")
                    if not key:
                        continue

                    user = item.get("user", {})
                    dj_name = user.get("name") or username

                    pictures = item.get("pictures", {})
                    artwork = pictures.get("large") or pictures.get("medium")

                    tags = [t.get("name", "") for t in item.get("tags", [])]

                    embed_url = f"https://www.mixcloud.com/widget/iframe/?hide_cover=1&mini=1&feed={key}"

                    tracks.append(MixcloudTrack(
                        id=f"mixcloud_{key.replace('/', '_')}",
                        title=item.get("name", "Unknown Mix"),
                        artist=dj_name,
                        url=f"https://www.mixcloud.com{key}",
                        plays=item.get("play_count"),
                        favorites=item.get("favorite_count"),
                        duration=item.get("audio_length", 0),
                        genre=tags[0] if tags else None,
                        tags=tags,
                        artwork_url=artwork,
                        embed_url=embed_url,
                    ))

    except Exception as e:
        print(f"[mixcloud] User mixes error: {e}")

    return tracks
