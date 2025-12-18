"""
Multi-source aggregator for Latent Search.

Combines results from Bandcamp, Reddit, and SoundCloud
into a unified format for the search API.
"""
import asyncio
from dataclasses import dataclass, field
from typing import Optional
from .bandcamp import search_bandcamp, BandcampTrack
from .reddit import search_reddit, RedditTrack
from .soundcloud import search_soundcloud, SoundCloudTrack, compute_shadow_score


@dataclass
class ExternalTrack:
    """Unified track format from external sources."""
    id: str
    title: str
    artist: str
    source: str  # "bandcamp", "reddit", "soundcloud"
    url: str
    artwork_url: Optional[str] = None
    embed_url: Optional[str] = None
    genre: Optional[str] = None

    # Metrics (where available)
    plays: Optional[int] = None
    upvotes: Optional[int] = None
    shadow_score: float = 0.8  # Default high shadow for external sources

    # Source-specific metadata
    meta: dict = field(default_factory=dict)


def _bandcamp_to_external(track: BandcampTrack) -> ExternalTrack:
    """Convert BandcampTrack to ExternalTrack."""
    return ExternalTrack(
        id=track.id,
        title=track.title,
        artist=track.artist,
        source="bandcamp",
        url=track.url,
        artwork_url=track.artwork_url,
        shadow_score=0.85,  # Bandcamp artists are typically underground
        meta={"album": track.album} if track.album else {},
    )


def _reddit_to_external(track: RedditTrack) -> ExternalTrack:
    """Convert RedditTrack to ExternalTrack."""
    # Higher upvotes = slightly lower shadow (more discovered)
    shadow = 0.75 - (min(track.upvotes, 1000) / 2000)  # 0.75 to 0.25

    return ExternalTrack(
        id=track.id,
        title=track.title,
        artist=track.artist,
        source="reddit",
        url=track.url,
        artwork_url=track.artwork_url,
        embed_url=track.embed_url,
        genre=track.genre,
        upvotes=track.upvotes,
        shadow_score=max(0.3, shadow),
        meta={
            "subreddit": track.subreddit,
            "comments": track.comments,
        },
    )


def _soundcloud_to_external(track: SoundCloudTrack) -> ExternalTrack:
    """Convert SoundCloudTrack to ExternalTrack."""
    return ExternalTrack(
        id=track.id,
        title=track.title,
        artist=track.artist,
        source="soundcloud",
        url=track.url,
        artwork_url=track.artwork_url,
        embed_url=track.embed_url,
        genre=track.genre,
        plays=track.plays,
        shadow_score=compute_shadow_score(track),
        meta={
            "bpm": track.bpm,
            "duration": track.duration,
            "likes": track.likes,
        },
    )


async def search_all_sources(
    query: str,
    sources: Optional[list[str]] = None,
    limit_per_source: int = 20
) -> list[ExternalTrack]:
    """
    Search all external sources concurrently.

    Args:
        query: Search term (genre, artist, etc.)
        sources: List of sources to search ("bandcamp", "reddit", "soundcloud")
                 Defaults to all sources.
        limit_per_source: Maximum results per source

    Returns:
        Combined list of ExternalTrack objects, sorted by shadow_score
    """
    if sources is None:
        sources = ["bandcamp", "reddit", "soundcloud"]

    tasks = []

    if "bandcamp" in sources:
        tasks.append(("bandcamp", search_bandcamp(query, limit=limit_per_source)))

    if "reddit" in sources:
        tasks.append(("reddit", search_reddit(query, limit=limit_per_source)))

    if "soundcloud" in sources:
        tasks.append(("soundcloud", search_soundcloud(query, limit=limit_per_source)))

    # Run all searches concurrently with timeout
    all_tracks: list[ExternalTrack] = []

    results = await asyncio.gather(
        *[t[1] for t in tasks],
        return_exceptions=True
    )

    for (source_name, _), result in zip(tasks, results):
        if isinstance(result, Exception):
            print(f"[DEBUG] {source_name} search failed: {result}")
            continue

        for track in result:
            if source_name == "bandcamp":
                all_tracks.append(_bandcamp_to_external(track))
            elif source_name == "reddit":
                all_tracks.append(_reddit_to_external(track))
            elif source_name == "soundcloud":
                all_tracks.append(_soundcloud_to_external(track))

    # Sort by shadow score (highest first = most underground)
    all_tracks.sort(key=lambda t: t.shadow_score, reverse=True)

    # Deduplicate by artist+title similarity
    seen = set()
    unique_tracks = []
    for track in all_tracks:
        key = f"{track.artist.lower()}:{track.title.lower()}"
        if key not in seen:
            seen.add(key)
            unique_tracks.append(track)

    return unique_tracks


async def search_by_genre(
    genre: str,
    sources: Optional[list[str]] = None,
    limit: int = 30
) -> list[ExternalTrack]:
    """
    Search external sources by genre.

    This is the recommended entry point for latent search -
    find underground tracks in genres the user likes.
    """
    # Enhance query for better underground results
    queries = [
        genre,
        f"{genre} underground",
        f"{genre} rare",
    ]

    all_results: list[ExternalTrack] = []

    for q in queries:
        results = await search_all_sources(
            q,
            sources=sources,
            limit_per_source=limit // len(queries)
        )
        all_results.extend(results)

        if len(all_results) >= limit:
            break

    # Deduplicate
    seen = set()
    unique = []
    for track in all_results:
        if track.id not in seen:
            seen.add(track.id)
            unique.append(track)

    # Sort by shadow score
    unique.sort(key=lambda t: t.shadow_score, reverse=True)

    return unique[:limit]
