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
    access_token: str = Query(..., description="Spotify access token")
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
        context = await build_user_context(client)

        # Step 2: Expand candidates from context
        candidates = await expand_candidates(client, context, max_candidates=100)

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
            candidates, context, limit=MAX_RESULTS
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
# HEALTH CHECK
# =========================================================================

@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "latent-search"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
