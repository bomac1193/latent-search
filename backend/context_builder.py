"""
Longitudinal Context Profile Builder.

Aggregates user listening history across time windows to build
a stable representation of listening context (not just "taste").

Key metrics:
- Recurring artists across time periods
- Stable audio feature ranges
- Artists returned to after gaps
- Collaborator networks
"""
from dataclasses import dataclass, field
from typing import Optional
from spotify_client import SpotifyClient


@dataclass
class AudioFeatureProfile:
    """Aggregated audio feature ranges from user's listening history."""
    tempo_range: tuple[float, float] = (0, 200)
    energy_range: tuple[float, float] = (0, 1)
    danceability_range: tuple[float, float] = (0, 1)
    valence_range: tuple[float, float] = (0, 1)
    acousticness_range: tuple[float, float] = (0, 1)
    instrumentalness_range: tuple[float, float] = (0, 1)
    loudness_range: tuple[float, float] = (-60, 0)

    # Central tendencies (for similarity scoring)
    tempo_center: float = 120
    energy_center: float = 0.5
    danceability_center: float = 0.5
    valence_center: float = 0.5
    acousticness_center: float = 0.5
    instrumentalness_center: float = 0.5
    loudness_center: float = -10


@dataclass
class ArtistContext:
    """Context data for a single artist in user's history."""
    id: str
    name: str
    genres: list[str]
    popularity: int
    # Presence across time windows
    in_short_term: bool = False
    in_medium_term: bool = False
    in_long_term: bool = False
    # Calculated metrics
    recurrence_score: float = 0.0  # How often they appear across windows
    position_avg: float = 0.0      # Average position in top lists


@dataclass
class UserContext:
    """
    Complete longitudinal context profile for a user.
    This represents stable listening patterns, not momentary preferences.
    """
    # Core artist data
    artists: dict[str, ArtistContext] = field(default_factory=dict)

    # Recurring artists (appear in multiple time windows)
    recurring_artist_ids: list[str] = field(default_factory=list)

    # All genres from user's artists, weighted by frequency
    genre_weights: dict[str, float] = field(default_factory=dict)

    # Audio feature profile
    audio_profile: AudioFeatureProfile = field(default_factory=AudioFeatureProfile)

    # Track IDs the user has listened to (for exposure checking)
    known_track_ids: set[str] = field(default_factory=set)

    # Artist IDs the user has listened to
    known_artist_ids: set[str] = field(default_factory=set)


async def build_user_context(client: SpotifyClient, time_range: str = "all") -> UserContext:
    """
    Build a comprehensive longitudinal context profile from user's Spotify data.

    Fetches data across time ranges and aggregates into stable patterns.

    time_range: "short", "medium", "long", or "all"
    """
    context = UserContext()

    # =========================================================================
    # STEP 1: Fetch top artists based on selected time window(s)
    # =========================================================================
    if time_range == "short":
        short_artists = await client.get_top_artists("short_term", 50)
        _process_artists(context, short_artists.get("items", []), "short")
    elif time_range == "medium":
        medium_artists = await client.get_top_artists("medium_term", 50)
        _process_artists(context, medium_artists.get("items", []), "medium")
    elif time_range == "long":
        long_artists = await client.get_top_artists("long_term", 50)
        _process_artists(context, long_artists.get("items", []), "long")
    else:  # "all"
        short_artists = await client.get_top_artists("short_term", 50)
        medium_artists = await client.get_top_artists("medium_term", 50)
        long_artists = await client.get_top_artists("long_term", 50)
        _process_artists(context, short_artists.get("items", []), "short")
        _process_artists(context, medium_artists.get("items", []), "medium")
        _process_artists(context, long_artists.get("items", []), "long")

    # =========================================================================
    # STEP 2: Identify recurring artists (appear in 2+ time windows)
    # =========================================================================
    for artist_id, artist_ctx in context.artists.items():
        windows_present = sum([
            artist_ctx.in_short_term,
            artist_ctx.in_medium_term,
            artist_ctx.in_long_term
        ])
        artist_ctx.recurrence_score = windows_present / 3.0

        if windows_present >= 2:
            context.recurring_artist_ids.append(artist_id)

    context.known_artist_ids = set(context.artists.keys())

    # =========================================================================
    # STEP 3: Fetch top tracks and audio features
    # =========================================================================
    all_tracks = []
    if time_range == "short":
        short_tracks = await client.get_top_tracks("short_term", 50)
        all_tracks.extend(short_tracks.get("items", []))
    elif time_range == "medium":
        medium_tracks = await client.get_top_tracks("medium_term", 50)
        all_tracks.extend(medium_tracks.get("items", []))
    elif time_range == "long":
        long_tracks = await client.get_top_tracks("long_term", 50)
        all_tracks.extend(long_tracks.get("items", []))
    else:  # "all"
        short_tracks = await client.get_top_tracks("short_term", 50)
        medium_tracks = await client.get_top_tracks("medium_term", 50)
        long_tracks = await client.get_top_tracks("long_term", 50)
        all_tracks.extend(short_tracks.get("items", []))
        all_tracks.extend(medium_tracks.get("items", []))
        all_tracks.extend(long_tracks.get("items", []))

    # Deduplicate tracks
    track_ids = list({t["id"] for t in all_tracks if t.get("id")})
    context.known_track_ids = set(track_ids)

    # =========================================================================
    # STEP 4: Build audio feature profile (optional - may fail for new apps)
    # =========================================================================
    if track_ids:
        try:
            all_features = []
            for i in range(0, len(track_ids), 100):
                batch = track_ids[i:i+100]
                features_response = await client.get_audio_features(batch)
                features = features_response.get("audio_features", [])
                all_features.extend([f for f in features if f])
            context.audio_profile = _compute_audio_profile(all_features)
        except Exception:
            # Audio features API may be restricted for new apps
            # Continue without audio features - use genre matching only
            pass

    # =========================================================================
    # STEP 5: Compute genre weights
    # =========================================================================
    context.genre_weights = _compute_genre_weights(context.artists)

    return context


def _process_artists(
    context: UserContext,
    artists: list[dict],
    time_window: str
) -> None:
    """Process artists from a single time window into context."""
    for idx, artist in enumerate(artists):
        artist_id = artist.get("id")
        if not artist_id:
            continue

        if artist_id not in context.artists:
            context.artists[artist_id] = ArtistContext(
                id=artist_id,
                name=artist.get("name", "Unknown"),
                genres=artist.get("genres", []),
                popularity=artist.get("popularity", 50)
            )

        artist_ctx = context.artists[artist_id]

        # Mark presence in time window
        if time_window == "short":
            artist_ctx.in_short_term = True
        elif time_window == "medium":
            artist_ctx.in_medium_term = True
        else:
            artist_ctx.in_long_term = True

        # Update average position (lower = more prominent)
        position = idx + 1
        if artist_ctx.position_avg == 0:
            artist_ctx.position_avg = position
        else:
            artist_ctx.position_avg = (artist_ctx.position_avg + position) / 2


def _compute_audio_profile(features: list[dict]) -> AudioFeatureProfile:
    """Compute aggregated audio feature ranges and centers from track features."""
    if not features:
        return AudioFeatureProfile()

    # Extract feature arrays
    tempos = [f["tempo"] for f in features if f.get("tempo")]
    energies = [f["energy"] for f in features if f.get("energy") is not None]
    danceabilities = [f["danceability"] for f in features if f.get("danceability") is not None]
    valences = [f["valence"] for f in features if f.get("valence") is not None]
    acousticnesses = [f["acousticness"] for f in features if f.get("acousticness") is not None]
    instrumentalnesses = [f["instrumentalness"] for f in features if f.get("instrumentalness") is not None]
    loudnesses = [f["loudness"] for f in features if f.get("loudness") is not None]

    def safe_range(values: list, default_min: float, default_max: float) -> tuple[float, float]:
        if not values:
            return (default_min, default_max)
        return (min(values), max(values))

    def safe_mean(values: list, default: float) -> float:
        if not values:
            return default
        return sum(values) / len(values)

    return AudioFeatureProfile(
        tempo_range=safe_range(tempos, 60, 180),
        energy_range=safe_range(energies, 0, 1),
        danceability_range=safe_range(danceabilities, 0, 1),
        valence_range=safe_range(valences, 0, 1),
        acousticness_range=safe_range(acousticnesses, 0, 1),
        instrumentalness_range=safe_range(instrumentalnesses, 0, 1),
        loudness_range=safe_range(loudnesses, -60, 0),
        tempo_center=safe_mean(tempos, 120),
        energy_center=safe_mean(energies, 0.5),
        danceability_center=safe_mean(danceabilities, 0.5),
        valence_center=safe_mean(valences, 0.5),
        acousticness_center=safe_mean(acousticnesses, 0.5),
        instrumentalness_center=safe_mean(instrumentalnesses, 0.5),
        loudness_center=safe_mean(loudnesses, -10),
    )


def _compute_genre_weights(artists: dict[str, ArtistContext]) -> dict[str, float]:
    """
    Compute genre weights based on frequency across user's artists.
    More common genres get higher weights.
    """
    genre_counts: dict[str, int] = {}

    for artist_ctx in artists.values():
        # Weight by recurrence score
        weight = 1 + artist_ctx.recurrence_score
        for genre in artist_ctx.genres:
            genre_counts[genre] = genre_counts.get(genre, 0) + weight

    if not genre_counts:
        return {}

    # Normalize to 0-1 range
    max_count = max(genre_counts.values())
    return {genre: count / max_count for genre, count in genre_counts.items()}
