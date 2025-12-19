"""
Candidate Expansion Module.

Generates candidate artists that the user has NOT listened to,
but are STRUCTURALLY connected to their listening history.

Key constraint: A candidate must appear as related to at least 2
different recurring seed artists to be eligible. This ensures
structural omission, not random adjacency.
"""
from dataclasses import dataclass, field
from typing import Optional
from spotify_client import SpotifyClient
from context_builder import UserContext
from config import RECENCY_CUTOFF_YEAR, MIN_SEED_SUPPORT


@dataclass
class CandidateArtist:
    """A candidate artist for potential recommendation."""
    id: str
    name: str
    genres: list[str]
    popularity: int
    # How the candidate was discovered
    source: str  # "related_artist", "genre_search"
    # Which genre led to this candidate
    source_genre: Optional[str] = None
    # Earliest album year (for recency scoring)
    earliest_release_year: Optional[int] = None
    # Sample track for display
    sample_track_id: Optional[str] = None
    sample_track_name: Optional[str] = None
    # Audio features of sample track (may be unavailable)
    audio_features: Optional[dict] = None
    # Genre overlap score
    genre_overlap: float = 0.0
    # STRUCTURAL SUPPORT: which seed artists link to this candidate
    seed_artist_ids: list[str] = field(default_factory=list)
    seed_artist_names: list[str] = field(default_factory=list)
    # Count of seed artists that support this candidate
    seed_support_count: int = 0


async def expand_candidates(
    client: SpotifyClient,
    context: UserContext,
    max_candidates: int = 100,
    min_popularity: int = 5,
    max_popularity: int = 60
) -> list[CandidateArtist]:
    """
    Generate candidate artists from user's context.

    STRATEGY:
    1. Use recurring artists as seeds (appear in 2+ time windows)
    2. Get related artists for each seed
    3. Track which seeds link to each candidate
    4. REQUIRE: candidate must be linked by 2+ seeds (structural omission)
    5. Filter out known artists
    6. Score by genre overlap
    """
    # Track candidates and their seed support
    candidate_support: dict[str, dict] = {}  # artist_id -> {data, seed_ids, seed_names}

    # Use recurring artists as seeds (these are the user's stable preferences)
    seed_artist_ids = context.recurring_artist_ids

    # If not enough recurring artists, use top artists by position
    if len(seed_artist_ids) < 5:
        sorted_artists = sorted(
            context.artists.values(),
            key=lambda a: a.position_avg
        )
        seed_artist_ids = [a.id for a in sorted_artists[:10]]

    print(f"[expand] Using {len(seed_artist_ids)} seed artists")

    # =========================================================================
    # STEP 1: Get related artists for each seed
    # =========================================================================
    for seed_id in seed_artist_ids[:15]:  # Limit API calls
        seed_artist = context.artists.get(seed_id)
        seed_name = seed_artist.name if seed_artist else "Unknown"

        try:
            related = await client.get_related_artists(seed_id)
            related_artists = related.get("artists", [])

            for artist in related_artists:
                artist_id = artist.get("id")
                if not artist_id:
                    continue

                # Skip known artists
                if artist_id in context.known_artist_ids:
                    continue

                # Initialize or update candidate support
                if artist_id not in candidate_support:
                    popularity = artist.get("popularity", 0)

                    # Skip if outside popularity range
                    if popularity < min_popularity or popularity > max_popularity:
                        continue

                    artist_genres = artist.get("genres", [])

                    candidate_support[artist_id] = {
                        "id": artist_id,
                        "name": artist.get("name", "Unknown"),
                        "genres": artist_genres,
                        "popularity": popularity,
                        "genre_overlap": _compute_genre_overlap(artist_genres, context.genre_weights),
                        "seed_ids": [],
                        "seed_names": [],
                    }

                # Add this seed as support
                if seed_id not in candidate_support[artist_id]["seed_ids"]:
                    candidate_support[artist_id]["seed_ids"].append(seed_id)
                    candidate_support[artist_id]["seed_names"].append(seed_name)

        except Exception as e:
            print(f"[expand] Related artists failed for {seed_id}: {e}")
            continue

    # =========================================================================
    # STEP 2: Filter to candidates with seed support (STRUCTURAL OMISSION)
    # =========================================================================
    candidates: list[CandidateArtist] = []

    # Dynamic threshold: if few recurring artists, accept 1+ seed support
    effective_min_support = MIN_SEED_SUPPORT if len(seed_artist_ids) >= 3 else 1

    for artist_id, data in candidate_support.items():
        seed_count = len(data["seed_ids"])

        # REQUIRE: at least effective_min_support seeds must link to this candidate
        if seed_count < effective_min_support:
            continue

        candidates.append(CandidateArtist(
            id=data["id"],
            name=data["name"],
            genres=data["genres"],
            popularity=data["popularity"],
            source="related_artist",
            genre_overlap=data["genre_overlap"],
            seed_artist_ids=data["seed_ids"],
            seed_artist_names=data["seed_names"],
            seed_support_count=seed_count,
        ))

    print(f"[expand] {len(candidate_support)} candidates found, {len(candidates)} have {effective_min_support}+ seed support")

    # =========================================================================
    # STEP 3: If insufficient candidates, fall back to genre search
    # =========================================================================
    if len(candidates) < 10:
        print("[expand] Insufficient related candidates, trying genre search...")
        genre_candidates = await _expand_by_genre(
            client, context,
            existing_ids=set(c.id for c in candidates),
            min_popularity=min_popularity,
            max_popularity=max_popularity,
            limit=max_candidates - len(candidates)
        )
        candidates.extend(genre_candidates)

    # =========================================================================
    # STEP 4: Sort by seed support * genre overlap, then fetch details
    # =========================================================================
    candidates.sort(
        key=lambda c: (c.seed_support_count * c.genre_overlap),
        reverse=True
    )

    # Limit to top candidates
    top_candidates = candidates[:max_candidates]

    # Fetch sample tracks for top candidates
    for candidate in top_candidates[:30]:
        try:
            top_tracks = await client.get_artist_top_tracks(candidate.id)
            tracks = top_tracks.get("tracks", [])
            if tracks:
                candidate.sample_track_id = tracks[0].get("id")
                candidate.sample_track_name = tracks[0].get("name")
        except Exception:
            continue

    # Fetch album years for recency scoring
    for candidate in top_candidates[:20]:
        try:
            albums = await client.get_artist_albums(candidate.id, limit=5)
            album_items = albums.get("items", [])

            years = []
            for album in album_items:
                release_date = album.get("release_date", "")
                if release_date:
                    try:
                        year = int(release_date[:4])
                        years.append(year)
                    except ValueError:
                        continue
            if years:
                candidate.earliest_release_year = min(years)
        except Exception:
            continue

    print(f"[expand] Final candidates: {len(top_candidates)}")
    return top_candidates


async def _expand_by_genre(
    client: SpotifyClient,
    context: UserContext,
    existing_ids: set[str],
    min_popularity: int,
    max_popularity: int,
    limit: int
) -> list[CandidateArtist]:
    """
    Fallback: expand candidates by searching top genres.
    These candidates won't have seed support, so they're lower priority.
    """
    candidates = []

    top_genres = sorted(
        context.genre_weights.items(),
        key=lambda x: x[1],
        reverse=True
    )[:5]

    for genre, weight in top_genres:
        if len(candidates) >= limit:
            break

        try:
            query = f'genre:"{genre}"'
            results = await client.search_artists(query, limit=30)
            artists = results.get("artists", {}).get("items", [])

            for artist in artists:
                artist_id = artist.get("id")
                if not artist_id:
                    continue

                if artist_id in context.known_artist_ids:
                    continue
                if artist_id in existing_ids:
                    continue

                popularity = artist.get("popularity", 0)
                if popularity < min_popularity or popularity > max_popularity:
                    continue

                artist_genres = artist.get("genres", [])

                candidates.append(CandidateArtist(
                    id=artist_id,
                    name=artist.get("name", "Unknown"),
                    genres=artist_genres,
                    popularity=popularity,
                    source="genre_search",
                    source_genre=genre,
                    genre_overlap=_compute_genre_overlap(artist_genres, context.genre_weights),
                    seed_support_count=0,  # No seed support for genre search
                ))

                existing_ids.add(artist_id)

                if len(candidates) >= limit:
                    break

        except Exception as e:
            print(f"[expand] Genre search failed for '{genre}': {e}")
            continue

    return candidates


def _compute_genre_overlap(
    candidate_genres: list[str],
    user_genre_weights: dict[str, float]
) -> float:
    """
    Compute how much a candidate's genres overlap with user's genre profile.
    Returns 0-1 score.
    """
    if not candidate_genres or not user_genre_weights:
        return 0.0

    overlap_score = 0.0
    for genre in candidate_genres:
        # Direct match
        if genre in user_genre_weights:
            overlap_score += user_genre_weights[genre]
        else:
            # Partial match (e.g., "indie rock" matches "rock")
            for user_genre, weight in user_genre_weights.items():
                if genre in user_genre or user_genre in genre:
                    overlap_score += weight * 0.5
                    break

    # Normalize by number of candidate genres
    return min(1.0, overlap_score / max(len(candidate_genres), 1))
