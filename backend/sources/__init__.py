"""
External music sources for Latent Search.

These sources find music OUTSIDE Spotify's algorithm:
- Bandcamp: Underground/indie artists
- Reddit: Community-curated discoveries
- SoundCloud: Unreleased/emerging artists
"""
from .bandcamp import search_bandcamp
from .reddit import search_reddit
from .soundcloud import search_soundcloud
from .aggregator import search_all_sources, ExternalTrack

__all__ = [
    "search_bandcamp",
    "search_reddit",
    "search_soundcloud",
    "search_all_sources",
    "ExternalTrack",
]
