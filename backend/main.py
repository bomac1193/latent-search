"""
Latent Search - FastAPI Backend

A research MVP for music discovery that surfaces contextually relevant
but systematically excluded artists from a user's Spotify history.
"""
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import urllib.parse

from config import (
    SPOTIFY_CLIENT_ID,
    SPOTIFY_AUTH_URL,
    SPOTIFY_REDIRECT_URI,
    SPOTIFY_SCOPES,
    MAX_RESULTS
)
from spotify_client import SpotifyClient, exchange_code_for_token
from context_builder import build_user_context
from candidate_expander import expand_candidates
from omission_scorer import get_top_recommendations
import database as db
from sources import search_all_sources, ExternalTrack, shadow_search, deep_shadow_search, ShadowTrack


app = FastAPI(
    title="Latent Search",
    description="Music discovery through omission scoring",
    version="0.1.0"
)

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================================================
# RESPONSE MODELS
# =========================================================================

class RecommendationItem(BaseModel):
    """A single recommendation result."""
    artist_id: str
    artist_name: str
    sample_track_name: Optional[str] = None
    genres: list[str]
    popularity: int
    omission_score: float
    explanation: str
    # Source attribution
    found_via_artist: Optional[str] = None


class LatentSearchResponse(BaseModel):
    """Response from the latent search endpoint."""
    recommendations: list[RecommendationItem]
    context_summary: dict


class AuthUrlResponse(BaseModel):
    """Spotify authorization URL."""
    auth_url: str


class LikeRequest(BaseModel):
    """Request to like an artist."""
    user_id: str
    artist_id: str
    artist_name: str
    genres: list[str]
    popularity: int
    source_genre: Optional[str] = None
    omission_score: float


class LikeResponse(BaseModel):
    """Response from like/unlike."""
    success: bool
    liked: bool


class LikeStatsResponse(BaseModel):
    """User's like statistics."""
    total_likes: int
    avg_popularity: float
    min_popularity: int
    max_popularity: int
    avg_omission_score: float
    top_genres: list


class ExternalTrackResponse(BaseModel):
    """A track from external sources."""
    id: str
    title: str
    artist: str
    source: str
    url: str
    artwork_url: Optional[str] = None
    embed_url: Optional[str] = None
    genre: Optional[str] = None
    plays: Optional[int] = None
    upvotes: Optional[int] = None
    shadow_score: float


class ExternalSearchResponse(BaseModel):
    """Response from external source search."""
    tracks: list[ExternalTrackResponse]
    sources_searched: list[str]
    total_found: int


class ShadowTrackResponse(BaseModel):
    """A track from shadow search with taste matching."""
    id: str
    title: str
    artist: str
    source: str
    url: str
    artwork_url: Optional[str] = None
    genre: Optional[str] = None
    plays: Optional[int] = None
    shadow_score: float
    taste_match: float
    combined_score: float
    region: Optional[str] = None


class ShadowSearchResponse(BaseModel):
    """Response from taste-matched shadow search."""
    tracks: list[ShadowTrackResponse]
    genres_searched: list[str]
    sources_searched: list[str]
    total_found: int


class TokenResponse(BaseModel):
    """OAuth token exchange response."""
    access_token: str
    refresh_token: str
    expires_in: int


# =========================================================================
# AUTH ENDPOINTS
# =========================================================================

@app.get("/auth/spotify/url", response_model=AuthUrlResponse)
def get_spotify_auth_url():
    """
    Generate Spotify OAuth authorization URL.
    Frontend redirects user here to authorize.
    """
    if not SPOTIFY_CLIENT_ID:
        raise HTTPException(status_code=500, detail="Spotify client ID not configured")

    params = {
        "client_id": SPOTIFY_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": SPOTIFY_REDIRECT_URI,
        "scope": " ".join(SPOTIFY_SCOPES),
        "show_dialog": "true"  # Always show auth dialog
    }

    auth_url = f"{SPOTIFY_AUTH_URL}?{urllib.parse.urlencode(params)}"
    return AuthUrlResponse(auth_url=auth_url)


@app.get("/auth/spotify/callback", response_model=TokenResponse)
async def spotify_callback(code: str = Query(...)):
    """
    Exchange authorization code for access token.
    Called after user authorizes on Spotify.
    """
    try:
        token_data = await exchange_code_for_token(code)
        return TokenResponse(
            access_token=token_data["access_token"],
            refresh_token=token_data.get("refresh_token", ""),
            expires_in=token_data.get("expires_in", 3600)
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Token exchange failed: {str(e)}")


# =========================================================================
# CORE SEARCH ENDPOINT
# =========================================================================

@app.get("/search", response_model=LatentSearchResponse)
async def run_latent_search(
    access_token: str = Query(..., description="Spotify access token"),
    min_popularity: int = Query(5, ge=0, le=100, description="Minimum artist popularity"),
    max_popularity: int = Query(60, ge=0, le=100, description="Maximum artist popularity"),
    time_range: str = Query("all", description="Time range: short, medium, long, or all"),
    max_results: int = Query(7, ge=1, le=20, description="Maximum results to return")
):
    """
    Run Latent Search algorithm.

    1. Fetches user's Spotify listening history
    2. Builds longitudinal context profile
    3. Expands candidates from related artists
    4. Scores candidates by omission score
    5. Returns top 5-7 recommendations

    The omission score identifies artists that SHOULD be relevant
    but are systematically excluded by standard recommendation systems.
    """
    try:
        client = SpotifyClient(access_token)

        # Step 1: Build user context from listening history
        context = await build_user_context(client, time_range=time_range)

        # Step 2: Expand candidates from context
        candidates = await expand_candidates(
            client, context,
            max_candidates=100,
            min_popularity=min_popularity,
            max_popularity=max_popularity
        )

        if not candidates:
            # Debug info: show which artists we tried to expand from
            source_artists = []
            if len(context.recurring_artist_ids) >= 5:
                source_artists = [context.artists[aid].name for aid in context.recurring_artist_ids[:5] if aid in context.artists]
            else:
                source_artists = [a.name for a in list(context.artists.values())[:5]]

            return LatentSearchResponse(
                recommendations=[],
                context_summary={
                    "artists_analyzed": len(context.artists),
                    "recurring_artists": len(context.recurring_artist_ids),
                    "genres_found": len(context.genre_weights),
                    "source_artists": source_artists,
                    "message": "No new artists found. You may already know all related artists, or try listening to more variety."
                }
            )

        # Step 3: Score and rank candidates
        top_recommendations = get_top_recommendations(
            candidates, context, limit=max_results
        )

        # Step 4: Format response
        recommendations = []
        for scored in top_recommendations:
            c = scored.candidate
            # Show source (genre or recommendation)
            found_via = c.source_genre if c.source_genre else c.source
            recommendations.append(RecommendationItem(
                artist_id=c.id,
                artist_name=c.name,
                sample_track_name=c.sample_track_name,
                genres=c.genres[:3],  # Limit genres shown
                popularity=c.popularity,
                omission_score=round(scored.omission_score, 3),
                explanation=scored.explanation,
                found_via_artist=found_via
            ))

        context_summary = {
            "artists_analyzed": len(context.artists),
            "recurring_artists": len(context.recurring_artist_ids),
            "genres_found": len(context.genre_weights),
            "top_genres": _get_top_genres(context.genre_weights, 5),
            "candidates_evaluated": len(candidates)
        }

        return LatentSearchResponse(
            recommendations=recommendations,
            context_summary=context_summary
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


def _get_top_genres(genre_weights: dict[str, float], limit: int) -> list[str]:
    """Get top N genres by weight."""
    sorted_genres = sorted(
        genre_weights.items(),
        key=lambda x: x[1],
        reverse=True
    )
    return [g[0] for g in sorted_genres[:limit]]


# =========================================================================
# EXTERNAL SOURCES ENDPOINT
# =========================================================================

@app.get("/search/external", response_model=ExternalSearchResponse)
async def search_external_sources(
    query: str = Query(..., description="Search query (genre, artist, etc.)"),
    sources: str = Query("bandcamp,reddit,soundcloud", description="Comma-separated sources"),
    limit: int = Query(30, ge=1, le=100, description="Maximum results")
):
    """
    Search external sources for underground/latent music.

    Sources:
    - bandcamp: Underground/indie artists
    - reddit: Community-curated discoveries from r/listentothis, r/under10k, etc.
    - soundcloud: Unreleased/emerging artists

    Results are sorted by "shadow score" - higher = more underground/rare.
    """
    source_list = [s.strip() for s in sources.split(",") if s.strip()]

    try:
        tracks = await search_all_sources(
            query=query,
            sources=source_list,
            limit_per_source=limit // max(len(source_list), 1)
        )

        response_tracks = [
            ExternalTrackResponse(
                id=t.id,
                title=t.title,
                artist=t.artist,
                source=t.source,
                url=t.url,
                artwork_url=t.artwork_url,
                embed_url=t.embed_url,
                genre=t.genre,
                plays=t.plays,
                upvotes=t.upvotes,
                shadow_score=round(t.shadow_score, 3),
            )
            for t in tracks[:limit]
        ]

        return ExternalSearchResponse(
            tracks=response_tracks,
            sources_searched=source_list,
            total_found=len(response_tracks),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"External search failed: {str(e)}")


# =========================================================================
# SHADOW SEARCH - TASTE MATCHED UNDERGROUND DISCOVERY
# =========================================================================

@app.get("/search/shadow", response_model=ShadowSearchResponse)
async def run_shadow_search(
    genres: str = Query(..., description="Comma-separated genres from user's taste profile"),
    sources: str = Query(
        "audius,audiomack,archive,bandcamp,reddit,soundcloud",
        description="Comma-separated sources to search"
    ),
    limit: int = Query(30, ge=1, le=100, description="Maximum results"),
    deep: bool = Query(False, description="Deep search - only truly underground sources")
):
    """
    Taste-matched shadow search.

    Searches underground sources for music that:
    1. Matches the user's genre preferences (from Spotify)
    2. Is invisible to mainstream algorithms
    3. Prioritizes obscurity (high shadow score)

    Results are ranked by combined score = shadow_score * taste_match

    Sources:
    - audius: Decentralized Web3 music platform
    - audiomack: Strong African music presence
    - archive: Internet Archive (netlabels, live recordings)
    - bandcamp: Underground/indie artists
    - reddit: Community-curated discoveries
    - soundcloud: Emerging artists
    """
    genre_list = [g.strip() for g in genres.split(",") if g.strip()]
    source_list = [s.strip() for s in sources.split(",") if s.strip()]

    if not genre_list:
        raise HTTPException(status_code=400, detail="At least one genre is required")

    try:
        if deep:
            tracks = await deep_shadow_search(
                user_genres=genre_list,
                limit=limit
            )
        else:
            tracks = await shadow_search(
                user_genres=genre_list,
                limit=limit,
                sources=source_list,
                include_african=True
            )

        response_tracks = [
            ShadowTrackResponse(
                id=t.id,
                title=t.title,
                artist=t.artist,
                source=t.source,
                url=t.url,
                artwork_url=t.artwork_url,
                genre=t.genre,
                plays=t.plays,
                shadow_score=t.shadow_score,
                taste_match=t.taste_match,
                combined_score=t.combined_score,
                region=t.region,
            )
            for t in tracks[:limit]
        ]

        return ShadowSearchResponse(
            tracks=response_tracks,
            genres_searched=genre_list,
            sources_searched=source_list,
            total_found=len(response_tracks),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Shadow search failed: {str(e)}")


@app.get("/search/shadow/spotify", response_model=ShadowSearchResponse)
async def run_shadow_search_with_spotify(
    access_token: str = Query(..., description="Spotify access token"),
    sources: str = Query(
        "audius,audiomack,archive,bandcamp,reddit,soundcloud",
        description="Comma-separated sources to search"
    ),
    limit: int = Query(30, ge=1, le=100, description="Maximum results"),
    deep: bool = Query(False, description="Deep search - only truly underground")
):
    """
    Shadow search using Spotify listening history to determine taste.

    Automatically extracts genres from your Spotify profile and searches
    underground sources for matching music.
    """
    source_list = [s.strip() for s in sources.split(",") if s.strip()]

    try:
        # Build user context from Spotify
        client = SpotifyClient(access_token)
        context = await build_user_context(client, time_range="all")

        # Get top genres from context
        sorted_genres = sorted(
            context.genre_weights.items(),
            key=lambda x: x[1],
            reverse=True
        )
        top_genres = [g[0] for g in sorted_genres[:5]]

        if not top_genres:
            top_genres = ["electronic", "experimental"]  # Fallback

        # Run shadow search with user's genres
        if deep:
            tracks = await deep_shadow_search(
                user_genres=top_genres,
                limit=limit
            )
        else:
            tracks = await shadow_search(
                user_genres=top_genres,
                limit=limit,
                sources=source_list,
                include_african=True
            )

        response_tracks = [
            ShadowTrackResponse(
                id=t.id,
                title=t.title,
                artist=t.artist,
                source=t.source,
                url=t.url,
                artwork_url=t.artwork_url,
                genre=t.genre,
                plays=t.plays,
                shadow_score=t.shadow_score,
                taste_match=t.taste_match,
                combined_score=t.combined_score,
                region=t.region,
            )
            for t in tracks[:limit]
        ]

        return ShadowSearchResponse(
            tracks=response_tracks,
            genres_searched=top_genres,
            sources_searched=source_list,
            total_found=len(response_tracks),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Shadow search failed: {str(e)}")


# =========================================================================
# LIKES ENDPOINTS
# =========================================================================

@app.post("/like", response_model=LikeResponse)
def like_artist(request: LikeRequest):
    """Like an artist recommendation."""
    success = db.add_like(
        user_id=request.user_id,
        artist_id=request.artist_id,
        artist_name=request.artist_name,
        genres=request.genres,
        popularity=request.popularity,
        source_genre=request.source_genre,
        omission_score=request.omission_score
    )
    return LikeResponse(success=success, liked=True)


@app.delete("/like", response_model=LikeResponse)
def unlike_artist(user_id: str = Query(...), artist_id: str = Query(...)):
    """Remove a like from an artist."""
    success = db.remove_like(user_id, artist_id)
    return LikeResponse(success=success, liked=False)


@app.get("/likes")
def get_likes(user_id: str = Query(...)):
    """Get all liked artists for a user."""
    likes = db.get_user_likes(user_id)
    return {"likes": likes}


@app.get("/likes/check")
def check_like(user_id: str = Query(...), artist_id: str = Query(...)):
    """Check if a user has liked an artist."""
    return {"liked": db.is_liked(user_id, artist_id)}


@app.get("/likes/stats", response_model=LikeStatsResponse)
def get_like_stats(user_id: str = Query(...)):
    """Get aggregate statistics from user's likes."""
    stats = db.get_like_stats(user_id)
    return LikeStatsResponse(**stats)


# =========================================================================
# HEALTH CHECK
# =========================================================================

@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "latent-search"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
