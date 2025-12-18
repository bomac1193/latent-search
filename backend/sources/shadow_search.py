"""
Taste-Matched Shadow Search.

This is the core algorithm for finding music that:
1. Matches the user's taste profile (from Spotify genres)
2. Exists completely outside mainstream algorithms
3. Prioritizes the most obscure/underground sources

The "shadow score" represents how invisible a track is to mainstream discovery.
Higher = more underground = better for latent discovery.
"""

import asyncio
from dataclasses import dataclass
from typing import Optional
import math

from .audius import search_audius, get_underground_audius, AudiusTrack
from .audiomack import search_audiomack, search_african_artists, AudiomackTrack
from .archive_org import search_archive, get_netlabel_releases, get_underground_by_genre, ArchiveTrack
from .bandcamp import search_bandcamp, BandcampTrack
from .reddit import search_reddit, RedditTrack
from .soundcloud import search_soundcloud, SoundCloudTrack


@dataclass
class ShadowTrack:
    """Unified track format with shadow scoring."""
    id: str
    title: str
    artist: str
    source: str
    url: str
    artwork_url: Optional[str]
    genre: Optional[str]
    plays: Optional[int]
    shadow_score: float  # 0-1, higher = more underground
    taste_match: float   # 0-1, higher = better genre match
    combined_score: float  # shadow_score * taste_match
    region: Optional[str]  # Geographic region if known


# Genre synonyms for better matching
GENRE_SYNONYMS = {
    "hip hop": ["hip-hop", "hiphop", "rap", "trap"],
    "electronic": ["electronica", "edm", "dance", "techno", "house"],
    "rock": ["alternative", "indie rock", "punk", "metal"],
    "r&b": ["rnb", "soul", "neo-soul", "r and b"],
    "jazz": ["bebop", "fusion", "smooth jazz"],
    "classical": ["orchestral", "symphony", "chamber"],
    "afrobeats": ["afrobeat", "afro", "naija", "afropop"],
    "amapiano": ["piano", "south african house"],
    "ambient": ["atmospheric", "drone", "soundscape"],
    "experimental": ["avant-garde", "noise", "art music"],
}


def calculate_shadow_score(
    plays: Optional[int],
    source: str,
    is_downloadable: bool = False
) -> float:
    """
    Calculate how "underground" a track is.

    Factors:
    - Play count (lower = higher shadow)
    - Source credibility for underground (Audius > Bandcamp > SoundCloud)
    - Downloadable = artist wants free distribution = more underground ethos
    """
    base_score = 0.5

    # Play count factor (0-0.4)
    if plays is not None:
        if plays < 100:
            play_factor = 0.4
        elif plays < 1000:
            play_factor = 0.35
        elif plays < 10000:
            play_factor = 0.25
        elif plays < 100000:
            play_factor = 0.15
        elif plays < 1000000:
            play_factor = 0.05
        else:
            play_factor = 0.0
    else:
        play_factor = 0.3  # Unknown = assume somewhat underground

    # Source factor (0-0.3)
    source_scores = {
        "audius": 0.3,      # Decentralized = most underground
        "archive": 0.28,    # Free archive = very underground
        "netlabels": 0.3,   # Netlabels are extremely underground
        "bandcamp": 0.25,   # Indie-focused
        "reddit": 0.2,      # Community-curated
        "audiomack": 0.18,  # African underground
        "soundcloud": 0.15, # More mainstream now
    }
    source_factor = source_scores.get(source, 0.15)

    # Downloadable bonus (0-0.1)
    download_factor = 0.1 if is_downloadable else 0.0

    shadow = base_score + play_factor + source_factor + download_factor

    return min(1.0, max(0.0, shadow))


def calculate_taste_match(
    track_genre: Optional[str],
    user_genres: list[str]
) -> float:
    """
    Calculate how well a track matches user's taste profile.

    Uses fuzzy matching with genre synonyms.
    """
    if not track_genre or not user_genres:
        return 0.3  # Neutral score for unknown

    track_genre_lower = track_genre.lower()

    # Direct match
    for ug in user_genres:
        ug_lower = ug.lower()
        if ug_lower in track_genre_lower or track_genre_lower in ug_lower:
            return 1.0

    # Synonym match
    for ug in user_genres:
        ug_lower = ug.lower()
        # Check if user genre has synonyms that match
        for base_genre, synonyms in GENRE_SYNONYMS.items():
            if ug_lower in base_genre or base_genre in ug_lower:
                for syn in synonyms:
                    if syn in track_genre_lower:
                        return 0.8

            # Check track genre synonyms
            if any(syn in track_genre_lower for syn in synonyms):
                if ug_lower in base_genre or base_genre in ug_lower:
                    return 0.8

    # Partial word match
    for ug in user_genres:
        words = ug.lower().split()
        for word in words:
            if len(word) > 3 and word in track_genre_lower:
                return 0.5

    return 0.2  # Low match


def convert_to_shadow_track(
    track,
    source: str,
    user_genres: list[str]
) -> ShadowTrack:
    """Convert any source track to unified ShadowTrack format."""

    # Extract common fields based on source type
    if isinstance(track, AudiusTrack):
        plays = track.plays
        genre = track.genre
        artwork = track.artwork_url
        is_downloadable = track.is_downloadable
        region = None
    elif isinstance(track, AudiomackTrack):
        plays = track.plays
        genre = track.genre
        artwork = track.artwork_url
        is_downloadable = False
        region = track.country
    elif isinstance(track, ArchiveTrack):
        plays = track.downloads
        genre = None  # Archive doesn't have genre
        artwork = track.artwork_url
        is_downloadable = True  # Archive is all free
        region = None
    elif isinstance(track, BandcampTrack):
        plays = None  # Bandcamp doesn't expose plays
        genre = track.genre
        artwork = track.artwork_url
        is_downloadable = False
        region = None
    elif isinstance(track, RedditTrack):
        plays = None
        genre = track.genre
        artwork = track.thumbnail
        is_downloadable = False
        region = None
    elif isinstance(track, SoundCloudTrack):
        plays = track.plays
        genre = track.genre
        artwork = track.artwork_url
        is_downloadable = False
        region = None
    else:
        # Generic fallback
        plays = getattr(track, 'plays', None)
        genre = getattr(track, 'genre', None)
        artwork = getattr(track, 'artwork_url', None)
        is_downloadable = False
        region = None

    shadow_score = calculate_shadow_score(plays, source, is_downloadable)
    taste_match = calculate_taste_match(genre, user_genres)
    combined = shadow_score * taste_match

    return ShadowTrack(
        id=track.id,
        title=track.title,
        artist=track.artist,
        source=source,
        url=track.url,
        artwork_url=artwork,
        genre=genre,
        plays=plays,
        shadow_score=round(shadow_score, 3),
        taste_match=round(taste_match, 3),
        combined_score=round(combined, 3),
        region=region,
    )


async def shadow_search(
    user_genres: list[str],
    limit: int = 30,
    sources: Optional[list[str]] = None,
    include_african: bool = True
) -> list[ShadowTrack]:
    """
    Main shadow search - finds taste-matched underground music.

    Args:
        user_genres: List of genres from user's Spotify profile
        limit: Max results per source
        sources: Which sources to search (default: all)
        include_african: Whether to boost African sources

    Returns:
        List of ShadowTracks sorted by combined score
    """
    if sources is None:
        sources = ["audius", "audiomack", "archive", "bandcamp", "reddit", "soundcloud"]

    all_tracks: list[ShadowTrack] = []

    # Build search queries from genres
    # Use top 3 genres for focused search
    search_genres = user_genres[:3] if user_genres else ["electronic", "experimental"]

    # Create search tasks
    tasks = []

    for genre in search_genres:
        if "audius" in sources:
            tasks.append(("audius", get_underground_audius(genre, limit=limit // 2)))
            tasks.append(("audius", search_audius(genre, limit=limit // 2)))

        if "audiomack" in sources:
            tasks.append(("audiomack", search_audiomack(genre, limit=limit // 2)))
            if include_african:
                tasks.append(("audiomack", search_african_artists(genre, limit=limit // 2)))

        if "archive" in sources:
            tasks.append(("archive", get_underground_by_genre(genre, limit=limit // 2)))
            tasks.append(("archive", get_netlabel_releases(genre, limit=limit // 2)))

        if "bandcamp" in sources:
            tasks.append(("bandcamp", search_bandcamp(genre, limit=limit // 2)))

        if "reddit" in sources:
            tasks.append(("reddit", search_reddit(genre, limit=limit // 2)))

        if "soundcloud" in sources:
            tasks.append(("soundcloud", search_soundcloud(genre, limit=limit // 2)))

    # Execute all searches concurrently
    print(f"[shadow] Searching {len(tasks)} endpoints for genres: {search_genres}")

    results = await asyncio.gather(
        *[task for _, task in tasks],
        return_exceptions=True
    )

    # Process results
    for i, result in enumerate(results):
        source = tasks[i][0]
        if isinstance(result, Exception):
            print(f"[shadow] Error from {source}: {result}")
            continue

        if not result:
            continue

        for track in result:
            shadow_track = convert_to_shadow_track(track, source, user_genres)
            all_tracks.append(shadow_track)

    # Deduplicate by artist + title similarity
    unique_tracks = deduplicate_tracks(all_tracks)

    # Sort by combined score (shadow * taste match)
    unique_tracks.sort(key=lambda t: t.combined_score, reverse=True)

    print(f"[shadow] Found {len(unique_tracks)} unique tracks")

    return unique_tracks[:limit * 2]  # Return more since we deduplicated


def deduplicate_tracks(tracks: list[ShadowTrack]) -> list[ShadowTrack]:
    """Remove duplicate tracks based on artist + title similarity."""
    seen = set()
    unique = []

    for track in tracks:
        # Create a normalized key
        key = f"{track.artist.lower().strip()}|{track.title.lower().strip()}"
        # Also check without common suffixes
        key_simple = key.replace("(official)", "").replace("(audio)", "").strip()

        if key not in seen and key_simple not in seen:
            seen.add(key)
            seen.add(key_simple)
            unique.append(track)

    return unique


async def deep_shadow_search(
    user_genres: list[str],
    limit: int = 50
) -> list[ShadowTrack]:
    """
    Deep shadow search - prioritizes the most obscure sources.
    For users who want to go really underground.
    """
    # Focus on the most underground sources
    deep_sources = ["audius", "archive", "bandcamp"]

    tracks = await shadow_search(
        user_genres=user_genres,
        limit=limit,
        sources=deep_sources,
        include_african=True
    )

    # Further filter to only truly underground tracks
    deep_tracks = [t for t in tracks if t.shadow_score > 0.7]

    print(f"[shadow] Deep search found {len(deep_tracks)} truly underground tracks")

    return deep_tracks
