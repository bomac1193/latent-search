"""
Telegram Music Source.

Scrapes public Telegram music channels for unreleased/underground tracks.
Uses web preview of public channels (t.me) to avoid needing full API auth.

Popular music channels include leak channels, indie promoters, and genre-specific groups.
"""

import aiohttp
import asyncio
import re
from dataclasses import dataclass
from typing import Optional
import hashlib


@dataclass
class TelegramTrack:
    id: str
    title: str
    artist: str
    url: str
    channel: str
    message_id: int
    plays: Optional[int]
    genre: Optional[str]
    artwork_url: Optional[str] = None
    embed_url: Optional[str] = None
    source: str = "telegram"


# Public music channels to scrape
# These are legitimate music sharing/promotion channels
MUSIC_CHANNELS = {
    # Genre-specific channels
    "electronic": [
        "electronic_music_world",
        "deephouse_music",
        "techno_live",
        "ambient_music_channel",
    ],
    "hip hop": [
        "hiphopheadz",
        "rap_music_world",
        "underground_hiphop",
    ],
    "indie": [
        "indiemusic",
        "alternativerock",
        "indiepop_music",
    ],
    "experimental": [
        "experimental_music",
        "noise_music_channel",
        "avantgarde_sounds",
    ],
    "african": [
        "afrobeats_music",
        "amapiano_sa",
        "african_music_world",
    ],
    "russian": [
        "russianmusic",
        "russian_rap",
        "ru_electronic",
    ],
    "japanese": [
        "jpop_music",
        "japanese_underground",
        "citypop_channel",
    ],
    # General underground
    "underground": [
        "undergroundmusic",
        "rare_music_finds",
        "musicleaks",
    ],
}

# Fallback channels for any genre
GENERAL_CHANNELS = [
    "musiccloud",
    "freemusic",
    "music_sharing",
]


async def scrape_telegram_channel(channel: str, limit: int = 10) -> list[TelegramTrack]:
    """
    Scrape a public Telegram channel's web preview for audio posts.
    """
    tracks = []
    url = f"https://t.me/s/{channel}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=15) as resp:
                if resp.status != 200:
                    print(f"[telegram] Channel {channel} returned {resp.status}")
                    return []

                html = await resp.text()

                # Find message blocks with audio
                # Telegram web preview has specific HTML structure

                # Pattern for messages
                message_pattern = r'data-post="([^"]+)"'
                messages = re.findall(message_pattern, html)

                # Pattern for audio files
                audio_pattern = r'class="tgme_widget_message_document_title[^"]*"[^>]*>([^<]+)</div>'
                audio_titles = re.findall(audio_pattern, html)

                # Pattern for audio artist/extra info
                extra_pattern = r'class="tgme_widget_message_document_extra"[^>]*>([^<]+)</div>'
                audio_extras = re.findall(extra_pattern, html)

                # Pattern for message text (often contains track info)
                text_pattern = r'class="tgme_widget_message_text[^"]*"[^>]*>(.+?)</div>'
                message_texts = re.findall(text_pattern, html, re.DOTALL)

                # Process found audio
                for i, title in enumerate(audio_titles[:limit]):
                    # Clean HTML entities
                    import html as html_module
                    title = html_module.unescape(title.strip())

                    # Try to parse artist - title format
                    artist = "Unknown Artist"
                    if " - " in title:
                        parts = title.split(" - ", 1)
                        artist = parts[0].strip()
                        title = parts[1].strip()
                    elif i < len(audio_extras):
                        artist = html_module.unescape(audio_extras[i].strip())

                    # Get message ID for link
                    msg_id = i + 1
                    if i < len(messages):
                        try:
                            msg_id = int(messages[i].split("/")[-1])
                        except:
                            pass

                    track_id = hashlib.md5(f"{channel}_{msg_id}_{title}".encode()).hexdigest()[:12]

                    tracks.append(TelegramTrack(
                        id=f"tg_{track_id}",
                        title=title,
                        artist=artist,
                        url=f"https://t.me/{channel}/{msg_id}",
                        channel=channel,
                        message_id=msg_id,
                        plays=None,
                        genre=None,
                    ))

    except Exception as e:
        print(f"[telegram] Error scraping {channel}: {e}")

    return tracks


async def search_telegram(query: str, limit: int = 20) -> list[TelegramTrack]:
    """
    Search for music across Telegram channels.
    Maps query to relevant channels and scrapes them.
    """
    query_lower = query.lower()

    # Find relevant channels based on query
    channels_to_search = []

    for genre, channels in MUSIC_CHANNELS.items():
        if genre in query_lower or query_lower in genre:
            channels_to_search.extend(channels)

    # Add general channels if no specific match
    if not channels_to_search:
        channels_to_search = GENERAL_CHANNELS.copy()
        # Also check if query matches any genre keywords
        for genre, channels in MUSIC_CHANNELS.items():
            if any(word in query_lower for word in genre.split()):
                channels_to_search.extend(channels[:2])

    # Limit channels to avoid too many requests
    channels_to_search = list(set(channels_to_search))[:5]

    print(f"[telegram] Searching channels: {channels_to_search}")

    # Scrape channels concurrently
    tasks = [
        scrape_telegram_channel(channel, limit // len(channels_to_search) + 1)
        for channel in channels_to_search
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_tracks = []
    for result in results:
        if isinstance(result, list):
            all_tracks.extend(result)

    # Tag tracks with genre hint from query
    for track in all_tracks:
        if not track.genre:
            track.genre = query

    return all_tracks[:limit]


async def get_telegram_underground(genre: str, limit: int = 20) -> list[TelegramTrack]:
    """
    Find underground tracks from Telegram music channels.
    Prioritizes leak/rare music channels.
    """
    genre_lower = genre.lower()

    # Get genre-specific channels
    channels = MUSIC_CHANNELS.get(genre_lower, [])

    # Also add underground/general channels
    channels.extend(MUSIC_CHANNELS.get("underground", []))

    # Deduplicate
    channels = list(set(channels))[:6]

    if not channels:
        channels = GENERAL_CHANNELS

    print(f"[telegram] Underground search in: {channels}")

    tasks = [
        scrape_telegram_channel(channel, limit // len(channels) + 1)
        for channel in channels
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_tracks = []
    for result in results:
        if isinstance(result, list):
            all_tracks.extend(result)

    # Tag with genre
    for track in all_tracks:
        track.genre = genre

    return all_tracks[:limit]


async def get_channel_latest(channel: str, limit: int = 20) -> list[TelegramTrack]:
    """
    Get latest posts from a specific Telegram channel.
    Useful for checking specific music channels.
    """
    return await scrape_telegram_channel(channel, limit)


# For when Telethon is available (requires user authentication)
async def search_telegram_api(query: str, limit: int = 20) -> list[TelegramTrack]:
    """
    Search using Telegram API via Telethon.
    Requires TELEGRAM_API_ID and TELEGRAM_API_HASH environment variables.

    This is more powerful but requires user authentication.
    """
    import os

    api_id = os.environ.get("TELEGRAM_API_ID")
    api_hash = os.environ.get("TELEGRAM_API_HASH")

    if not api_id or not api_hash:
        print("[telegram] No API credentials, falling back to web scraping")
        return await search_telegram(query, limit)

    try:
        from telethon import TelegramClient
        from telethon.tl.functions.messages import SearchGlobalRequest
        from telethon.tl.types import InputMessagesFilterMusic

        # This would require an authenticated session
        # For now, fall back to web scraping
        print("[telegram] Telethon search not implemented, using web scraping")
        return await search_telegram(query, limit)

    except ImportError:
        print("[telegram] Telethon not installed, using web scraping")
        return await search_telegram(query, limit)
