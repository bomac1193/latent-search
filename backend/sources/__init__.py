"""
External music sources for Latent Search.

These sources find music OUTSIDE Spotify's algorithm:
- Bandcamp: Underground/indie artists
- Reddit: Community-curated discoveries
- SoundCloud: Unreleased/emerging artists
- Audius: Decentralized Web3 music platform
- Audiomack: African music & underground hip-hop
- Archive.org: Netlabels, live recordings, free music

Shadow Search provides taste-matched discovery across all sources.
"""
from .bandcamp import search_bandcamp
from .reddit import search_reddit
from .soundcloud import search_soundcloud
from .audius import search_audius, get_underground_audius, get_trending_audius
from .audiomack import search_audiomack, search_african_artists
from .archive_org import search_archive, get_netlabel_releases, get_underground_by_genre
from .aggregator import search_all_sources, ExternalTrack
from .shadow_search import shadow_search, deep_shadow_search, ShadowTrack

__all__ = [
    # Original sources
    "search_bandcamp",
    "search_reddit",
    "search_soundcloud",
    # New sources
    "search_audius",
    "get_underground_audius",
    "get_trending_audius",
    "search_audiomack",
    "search_african_artists",
    "search_archive",
    "get_netlabel_releases",
    "get_underground_by_genre",
    # Aggregators
    "search_all_sources",
    "ExternalTrack",
    # Shadow search
    "shadow_search",
    "deep_shadow_search",
    "ShadowTrack",
]
