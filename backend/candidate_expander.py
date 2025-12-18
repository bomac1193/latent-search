"""
Candidate Expansion Module.

Generates candidate artists/tracks that the user has NOT listened to,
but are contextually adjacent to their listening history.

Uses genre-based search since related-artists API is restricted for new apps.
"""
from dataclasses import dataclass
from typing import Optional
from spotify_client import SpotifyClient
from context_builder import UserContext
from config import RECENCY_CUTOFF_YEAR


@dataclass
class CandidateArtist:
    """A candidate artist for potential recommendation."""
    id: str
    name: str
    genres: list[str]
    popularity: int
    # How the candidate was discovered
    source: str  # "genre_search", "recommendation"
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


async def expand_candidates(
    client: SpotifyClient,
    context: UserContext,
    max_candidates: int = 100,
    min_popularity: int = 5,
    max_popularity: int = 60
) -> list[CandidateArtist]:
    """
    Generate candidate artists from user's context using genre search.

    Strategy:
    1. Get user's top genres
    2. Search for artists in those genres
    3. Filter out known artists
    4. Score by genre overlap

    min_popularity/max_popularity: Filter artists by popularity range
    """
    candidates: dict[str, CandidateArtist] = {}

    # Get top genres from user's profile
    top_genres = sorted(
        context.genre_weights.items(),
        key=lambda x: x[1],
        reverse=True
    )[:10]  # Top 10 genres

    print(f"[DEBUG] Top genres: {[g[0] for g in top_genres]}")

    # =========================================================================
    # STEP 1: Search for artists by genre
    # =========================================================================
    for genre, weight in top_genres:
        if len(candidates) >= max_candidates:
            break

        try:
            # Search for artists in this genre
            query = f'genre:"{genre}"'
            results = await client.search_artists(query, limit=50)
            artists = results.get("artists", {}).get("items", [])

            skipped_known = 0
            skipped_pop = 0
            for artist in artists:
                artist_id = artist.get("id")
                if not artist_id:
                    continue

                # Skip known artists
                if artist_id in context.known_artist_ids:
                    skipped_known += 1
                    continue

                # Skip if already added
                if artist_id in candidates:
                    continue

                # Filter by popularity range
                popularity = artist.get("popularity", 0)
                if popularity < min_popularity or popularity > max_popularity:
                    skipped_pop += 1
                    continue

                artist_genres = artist.get("genres", [])

                candidates[artist_id] = CandidateArtist(
                    id=artist_id,
                    name=artist.get("name", "Unknown"),
                    genres=artist_genres,
                    popularity=popularity,
                    source="genre_search",
                    source_genre=genre,
                    genre_overlap=_compute_genre_overlap(artist_genres, context.genre_weights)
                )

                if len(candidates) >= max_candidates:
                    break

            print(f"[DEBUG] Genre '{genre}': {len(artists)} found, {skipped_known} known, {skipped_pop} outside popularity range, {len(candidates)} total candidates")

        except Exception as e:
            print(f"[DEBUG] Genre search failed for '{genre}': {e}")
            continue

    # =========================================================================
    # STEP 2: Try recommendations endpoint as fallback
    # =========================================================================
    if len(candidates) < 20:
        try:
            seed_artists = list(context.artists.keys())[:5]
            recs = await client.get_recommendations(seed_artists, limit=50)
            tracks = recs.get("tracks", [])

            print(f"[DEBUG] Recommendations: got {len(tracks)} tracks")

            # Extract unique artists from recommended tracks
            for track in tracks:
                for artist in track.get("artists", []):
                    artist_id = artist.get("id")
                    if not artist_id:
                        continue
                    if artist_id in context.known_artist_ids:
                        continue
                    if artist_id in candidates:
                        continue

                    # Fetch full artist details
                    try:
                        full_artist = await client.get_artist(artist_id)
                        candidates[artist_id] = CandidateArtist(
                            id=artist_id,
                            name=full_artist.get("name", artist.get("name", "Unknown")),
                            genres=full_artist.get("genres", []),
                            popularity=full_artist.get("popularity", 50),
                            source="recommendation",
                            sample_track_id=track.get("id"),
                            sample_track_name=track.get("name"),
                            genre_overlap=_compute_genre_overlap(
                                full_artist.get("genres", []),
                                context.genre_weights
                            )
                        )
                    except Exception:
                        continue

                    if len(candidates) >= max_candidates:
                        break

                if len(candidates) >= max_candidates:
                    break

        except Exception as e:
            print(f"[DEBUG] Recommendations failed: {e}")

    # =========================================================================
    # STEP 3: Fetch sample tracks for candidates without them
    # =========================================================================
    candidates_list = list(candidates.values())

    # Sort by genre overlap to prioritize best matches
    candidates_list.sort(key=lambda c: c.genre_overlap, reverse=True)
    top_candidates = candidates_list[:50]

    for candidate in top_candidates:
        if candidate.sample_track_name:
            continue  # Already has a sample

        try:
            top_tracks = await client.get_artist_top_tracks(candidate.id)
            tracks = top_tracks.get("tracks", [])
            if tracks:
                candidate.sample_track_id = tracks[0].get("id")
                candidate.sample_track_name = tracks[0].get("name")
        except Exception:
            continue

    # =========================================================================
    # STEP 4: Fetch album years for recency scoring
    # =========================================================================
    for candidate in top_candidates[:30]:
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

    print(f"[DEBUG] Final candidates: {len(candidates)}")
    return candidates_list


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
