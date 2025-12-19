"""
NetEase Cloud Music (网易云音乐) Source.

One of China's largest music platforms with 800M+ users and 611K+ indie artists.
Uses the unofficial NeteaseCloudMusicApi endpoints.

This is a goldmine for Chinese indie, C-pop, and underground music.
"""

import aiohttp
import asyncio
from dataclasses import dataclass
from typing import Optional
import hashlib
import urllib.parse


@dataclass
class NetEaseTrack:
    id: str
    title: str
    artist: str
    url: str
    album: Optional[str]
    plays: Optional[int]
    duration: int
    genre: Optional[str]
    artwork_url: Optional[str] = None
    embed_url: Optional[str] = None
    source: str = "netease"


# NetEase API endpoints
# These mirror the unofficial NeteaseCloudMusicApi project
NETEASE_API_BASE = "https://music.163.com/api"
NETEASE_WEB_BASE = "https://music.163.com"

# Alternative API endpoints (community-hosted)
NETEASE_MIRRORS = [
    "https://netease-cloud-music-api-five-roan.vercel.app",
    "https://netease-cloud-music-api.vercel.app",
]


async def search_netease_web(query: str, limit: int = 20) -> list[NetEaseTrack]:
    """
    Search NetEase via web scraping.
    Works without any API but limited functionality.
    """
    tracks = []

    search_url = f"{NETEASE_WEB_BASE}/api/search/get"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://music.163.com/",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    data = {
        "s": query,
        "type": 1,  # 1 = songs
        "limit": limit,
        "offset": 0,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                search_url,
                headers=headers,
                data=data,
                timeout=15
            ) as resp:
                if resp.status != 200:
                    print(f"[netease] Search returned {resp.status}")
                    return []

                result = await resp.json()

                if result.get("code") != 200:
                    print(f"[netease] API error: {result.get('code')}")
                    return []

                songs = result.get("result", {}).get("songs", [])

                for song in songs[:limit]:
                    # Extract artist names
                    artists = song.get("artists", [])
                    artist_name = ", ".join([a.get("name", "") for a in artists])

                    # Extract album info
                    album = song.get("album", {})
                    album_name = album.get("name")
                    artwork = album.get("picUrl")

                    song_id = str(song.get("id"))

                    tracks.append(NetEaseTrack(
                        id=f"netease_{song_id}",
                        title=song.get("name", "Unknown"),
                        artist=artist_name or "Unknown Artist",
                        url=f"https://music.163.com/#/song?id={song_id}",
                        album=album_name,
                        plays=None,  # Need separate API call for play count
                        duration=song.get("duration", 0) // 1000,
                        genre=None,
                        artwork_url=artwork,
                        embed_url=f"https://music.163.com/outchain/player?type=2&id={song_id}&auto=0&height=66",
                    ))

    except Exception as e:
        print(f"[netease] Search error: {e}")

    return tracks


async def search_netease_mirror(query: str, limit: int = 20) -> list[NetEaseTrack]:
    """
    Search using community-hosted API mirrors.
    More reliable but depends on mirror availability.
    """
    tracks = []

    for mirror in NETEASE_MIRRORS:
        try:
            search_url = f"{mirror}/search"

            params = {
                "keywords": query,
                "limit": limit,
                "type": 1,
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    search_url,
                    params=params,
                    timeout=10
                ) as resp:
                    if resp.status != 200:
                        continue

                    result = await resp.json()

                    if result.get("code") != 200:
                        continue

                    songs = result.get("result", {}).get("songs", [])

                    for song in songs[:limit]:
                        artists = song.get("artists", []) or song.get("ar", [])
                        artist_name = ", ".join([a.get("name", "") for a in artists])

                        album = song.get("album", {}) or song.get("al", {})
                        album_name = album.get("name")
                        artwork = album.get("picUrl")

                        song_id = str(song.get("id"))

                        tracks.append(NetEaseTrack(
                            id=f"netease_{song_id}",
                            title=song.get("name", "Unknown"),
                            artist=artist_name or "Unknown Artist",
                            url=f"https://music.163.com/#/song?id={song_id}",
                            album=album_name,
                            plays=song.get("pop"),  # Popularity score
                            duration=song.get("duration", song.get("dt", 0)) // 1000,
                            genre=None,
                            artwork_url=artwork,
                            embed_url=f"https://music.163.com/outchain/player?type=2&id={song_id}&auto=0&height=66",
                        ))

                    if tracks:
                        print(f"[netease] Found {len(tracks)} tracks via {mirror}")
                        return tracks

        except Exception as e:
            print(f"[netease] Mirror {mirror} error: {e}")
            continue

    return tracks


async def search_netease(query: str, limit: int = 20) -> list[NetEaseTrack]:
    """
    Main NetEase search function.
    Tries multiple methods for reliability.
    """
    # Try mirror API first (more reliable)
    tracks = await search_netease_mirror(query, limit)

    if tracks:
        return tracks

    # Fall back to direct web API
    return await search_netease_web(query, limit)


async def get_netease_indie(genre: str, limit: int = 20) -> list[NetEaseTrack]:
    """
    Find indie/underground Chinese music.
    Uses genre-specific search terms.
    """
    # Map genres to Chinese search terms for better results
    genre_mapping = {
        "electronic": ["电子", "synthwave", "电子音乐"],
        "hip hop": ["说唱", "嘻哈", "中国说唱"],
        "indie": ["独立", "indie", "独立音乐"],
        "rock": ["摇滚", "rock", "中国摇滚"],
        "jazz": ["爵士", "jazz"],
        "experimental": ["实验", "前卫", "experimental"],
        "ambient": ["氛围", "ambient", "环境音乐"],
        "folk": ["民谣", "folk", "中国民谣"],
        "r&b": ["节奏布鲁斯", "r&b", "华语r&b"],
        "metal": ["金属", "metal", "中国金属"],
    }

    genre_lower = genre.lower()
    search_terms = []

    # Find matching Chinese terms
    for key, terms in genre_mapping.items():
        if key in genre_lower or genre_lower in key:
            search_terms.extend(terms)

    if not search_terms:
        search_terms = [genre, f"{genre} 独立", f"indie {genre}"]

    all_tracks = []

    # Search with different terms
    for term in search_terms[:2]:  # Limit to avoid rate limits
        tracks = await search_netease(term, limit // 2)
        all_tracks.extend(tracks)
        await asyncio.sleep(0.3)

    # Deduplicate
    seen = set()
    unique = []
    for t in all_tracks:
        if t.id not in seen:
            seen.add(t.id)
            t.genre = genre  # Tag with original genre
            unique.append(t)

    return unique[:limit]


async def get_netease_new_artists(limit: int = 20) -> list[NetEaseTrack]:
    """
    Get tracks from new/emerging Chinese artists.
    """
    # Search for new artist playlists/tags
    search_terms = [
        "新人推荐",      # New artist recommendations
        "独立音乐人",    # Independent musicians
        "原创",         # Original/self-produced
        "小众",         # Niche/underground
    ]

    all_tracks = []

    for term in search_terms:
        tracks = await search_netease(term, limit // 4)
        all_tracks.extend(tracks)
        await asyncio.sleep(0.3)

    return all_tracks[:limit]


async def get_netease_by_playlist(playlist_id: str, limit: int = 50) -> list[NetEaseTrack]:
    """
    Get tracks from a specific NetEase playlist.
    Useful for curated underground playlists.
    """
    tracks = []

    for mirror in NETEASE_MIRRORS:
        try:
            url = f"{mirror}/playlist/detail"
            params = {"id": playlist_id}

            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=10) as resp:
                    if resp.status != 200:
                        continue

                    result = await resp.json()

                    if result.get("code") != 200:
                        continue

                    playlist = result.get("playlist", {})
                    track_ids = [str(t.get("id")) for t in playlist.get("trackIds", [])]

                    # Get track details
                    if track_ids:
                        detail_url = f"{mirror}/song/detail"
                        detail_params = {"ids": ",".join(track_ids[:limit])}

                        async with session.get(detail_url, params=detail_params, timeout=10) as detail_resp:
                            if detail_resp.status != 200:
                                continue

                            detail_result = await detail_resp.json()
                            songs = detail_result.get("songs", [])

                            for song in songs:
                                artists = song.get("ar", [])
                                artist_name = ", ".join([a.get("name", "") for a in artists])

                                album = song.get("al", {})
                                song_id = str(song.get("id"))

                                tracks.append(NetEaseTrack(
                                    id=f"netease_{song_id}",
                                    title=song.get("name", "Unknown"),
                                    artist=artist_name or "Unknown",
                                    url=f"https://music.163.com/#/song?id={song_id}",
                                    album=album.get("name"),
                                    plays=song.get("pop"),
                                    duration=song.get("dt", 0) // 1000,
                                    genre=None,
                                    artwork_url=album.get("picUrl"),
                                    embed_url=f"https://music.163.com/outchain/player?type=2&id={song_id}&auto=0&height=66",
                                ))

                    if tracks:
                        return tracks

        except Exception as e:
            print(f"[netease] Playlist error: {e}")
            continue

    return tracks
