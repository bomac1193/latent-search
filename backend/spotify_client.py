"""
Spotify API client for fetching user listening data.
Handles all communication with Spotify Web API.
"""
import httpx
from typing import Optional
from config import SPOTIFY_API_BASE, SPOTIFY_TOKEN_URL, SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REDIRECT_URI


class SpotifyClient:
    """Wrapper for Spotify Web API calls."""

    def __init__(self, access_token: str):
        self.access_token = access_token
        self.headers = {"Authorization": f"Bearer {access_token}"}

    async def _get(self, endpoint: str, params: Optional[dict] = None) -> dict:
        """Make authenticated GET request to Spotify API."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{SPOTIFY_API_BASE}{endpoint}",
                headers=self.headers,
                params=params or {}
            )
            response.raise_for_status()
            return response.json()

    # =========================================================================
    # USER LISTENING HISTORY
    # =========================================================================

    async def get_top_artists(self, time_range: str = "medium_term", limit: int = 50) -> dict:
        """
        Fetch user's top artists.

        time_range options:
        - short_term: ~4 weeks
        - medium_term: ~6 months
        - long_term: several years
        """
        return await self._get("/me/top/artists", {
            "time_range": time_range,
            "limit": limit
        })

    async def get_top_tracks(self, time_range: str = "medium_term", limit: int = 50) -> dict:
        """Fetch user's top tracks for a given time range."""
        return await self._get("/me/top/tracks", {
            "time_range": time_range,
            "limit": limit
        })

    async def get_recently_played(self, limit: int = 50) -> dict:
        """Fetch user's recently played tracks (last 50 max)."""
        return await self._get("/me/player/recently-played", {"limit": limit})

    async def get_saved_tracks(self, limit: int = 50, offset: int = 0) -> dict:
        """Fetch user's saved/liked tracks."""
        return await self._get("/me/tracks", {"limit": limit, "offset": offset})

    # =========================================================================
    # TRACK & ARTIST METADATA
    # =========================================================================

    async def get_audio_features(self, track_ids: list[str]) -> dict:
        """
        Fetch audio features for multiple tracks.
        Returns: tempo, energy, danceability, loudness, valence, acousticness, instrumentalness
        """
        # Spotify limits to 100 tracks per request
        ids = ",".join(track_ids[:100])
        return await self._get("/audio-features", {"ids": ids})

    async def get_artist(self, artist_id: str) -> dict:
        """Fetch single artist details including genres and popularity."""
        return await self._get(f"/artists/{artist_id}")

    async def get_artists(self, artist_ids: list[str]) -> dict:
        """Fetch multiple artists (max 50)."""
        ids = ",".join(artist_ids[:50])
        return await self._get("/artists", {"ids": ids})

    async def get_related_artists(self, artist_id: str) -> dict:
        """
        Fetch artists similar to given artist.
        This is Spotify's "fans also like" data.
        """
        return await self._get(f"/artists/{artist_id}/related-artists")

    async def get_artist_albums(self, artist_id: str, limit: int = 20) -> dict:
        """Fetch albums by an artist to determine release years."""
        return await self._get(f"/artists/{artist_id}/albums", {
            "include_groups": "album,single",
            "limit": limit
        })

    async def get_artist_top_tracks(self, artist_id: str, market: str = "US") -> dict:
        """Fetch an artist's top tracks for sampling."""
        return await self._get(f"/artists/{artist_id}/top-tracks", {"market": market})

    async def search_artists(self, query: str, limit: int = 50) -> dict:
        """Search for artists by query (name, genre, etc)."""
        return await self._get("/search", {
            "q": query,
            "type": "artist",
            "limit": limit
        })

    async def get_recommendations(self, seed_artists: list[str], limit: int = 50) -> dict:
        """
        Get track recommendations based on seed artists.
        May be restricted for new apps.
        """
        return await self._get("/recommendations", {
            "seed_artists": ",".join(seed_artists[:5]),  # Max 5 seeds
            "limit": limit
        })


async def exchange_code_for_token(code: str) -> dict:
    """
    Exchange OAuth authorization code for access token.
    Called after user authorizes via Spotify.
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(
            SPOTIFY_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": SPOTIFY_REDIRECT_URI,
                "client_id": SPOTIFY_CLIENT_ID,
                "client_secret": SPOTIFY_CLIENT_SECRET,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        response.raise_for_status()
        return response.json()


async def refresh_access_token(refresh_token: str) -> dict:
    """Refresh an expired access token."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            SPOTIFY_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": SPOTIFY_CLIENT_ID,
                "client_secret": SPOTIFY_CLIENT_SECRET,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        response.raise_for_status()
        return response.json()
