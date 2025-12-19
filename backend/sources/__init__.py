"""
External music sources for Latent Search.

These sources find music OUTSIDE Spotify's algorithm:
- Bandcamp: Underground/indie artists
- Reddit: Community-curated discoveries
- SoundCloud: Unreleased/emerging artists
- Audius: Decentralized Web3 music platform
- Audiomack: African music & underground hip-hop
- Archive.org: Netlabels, live recordings, free music

NEW - Global Underground Sources:
- VK Music: Russian underground (390M users, massive catalog)
- Telegram: Music channels, leaks, unreleased tracks
- NetEase: Chinese indie scene (611K+ independent artists)
- Funkwhale: Federated self-hosted music (truly underground)
- Mixcloud: DJ mixes and radio shows

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

# New global underground sources
from .vk import search_vk, get_vk_underground, VKTrack
from .telegram_music import search_telegram, get_telegram_underground, TelegramTrack
from .netease import search_netease, get_netease_indie, NetEaseTrack
from .funkwhale import search_funkwhale, get_funkwhale_underground, FunkwhaleTrack
from .mixcloud import search_mixcloud, get_mixcloud_underground, MixcloudTrack

__all__ = [
    # Original sources
    "search_bandcamp",
    "search_reddit",
    "search_soundcloud",
    # Web3/Alternative sources
    "search_audius",
    "get_underground_audius",
    "get_trending_audius",
    "search_audiomack",
    "search_african_artists",
    "search_archive",
    "get_netlabel_releases",
    "get_underground_by_genre",
    # NEW: Global underground sources
    "search_vk",
    "get_vk_underground",
    "VKTrack",
    "search_telegram",
    "get_telegram_underground",
    "TelegramTrack",
    "search_netease",
    "get_netease_indie",
    "NetEaseTrack",
    "search_funkwhale",
    "get_funkwhale_underground",
    "FunkwhaleTrack",
    "search_mixcloud",
    "get_mixcloud_underground",
    "MixcloudTrack",
    # Aggregators
    "search_all_sources",
    "ExternalTrack",
    # Shadow search
    "shadow_search",
    "deep_shadow_search",
    "ShadowTrack",
]
