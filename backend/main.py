"""
Latent Search - FastAPI Backend

A diagnostic instrument for music discovery through omission scoring.
NOT a general search tool.

Flow:
1. Connect Spotify
2. Run Diagnosis (see your listening profile)
3. Run Omission Scan (max 5 results, heavily justified)
4. Provide Feedback (accept/reject to improve)
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
from context_builder import build_user_context, UserContext
from candidate_expander import expand_candidates
from omission_scorer import get_top_recommendations
import database as db


app = FastAPI(
    title="Latent Search",
    description="Diagnosis + Omission Scan instrument. Not a search tool.",
    version="0.2.0"
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

class AuthUrlResponse(BaseModel):
    """Spotify authorization URL."""
    auth_url: str


class TokenResponse(BaseModel):
    """OAuth token exchange response."""
    access_token: str
    refresh_token: str
    expires_in: int


class RecurringArtist(BaseModel):
    """An artist that appears across multiple time windows."""
    id: str
    name: str
    genres: list[str]
    popularity: int
    in_short_term: bool
    in_medium_term: bool
    in_long_term: bool
    recurrence_score: float


class GenreWeight(BaseModel):
    """A genre with its weight in the user's profile."""
    genre: str
    weight: float


class AudioFeatureStats(BaseModel):
    """Audio feature statistics from user's listening."""
    energy: dict  # {mean, std, min, max}
    danceability: dict
    valence: dict
    tempo: dict
    acousticness: dict
    instrumentalness: dict


class DiagnosisResponse(BaseModel):
    """Complete diagnosis of user's listening profile."""
    recurring_artists: list[RecurringArtist]
    top_genres: list[GenreWeight]
    audio_feature_profile: dict
    notes: list[str]  # Template-based observations
    total_artists_analyzed: int
    total_tracks_analyzed: int


class EvidenceItem(BaseModel):
    """Evidence for why a candidate was surfaced."""
    seed_artists: list[str]
    genre_overlap_count: int
    audio_similarity_score: float
    popularity: int
    earliest_album_year: Optional[int] = None


class OmissionResultItem(BaseModel):
    """A single omission scan result with full justification."""
    artist_id: str
    artist_name: str
    sample_track_name: Optional[str] = None
    genres: list[str]
    omission_score: float
    explanation: str
    evidence: EvidenceItem


class OmissionScanResponse(BaseModel):
    """Response from omission scan. Max 5 results."""
    results: list[OmissionResultItem]
    diagnosis_summary: str  # One-line summary of context
    candidates_evaluated: int
    confidence_threshold_used: float


class FeedbackRequest(BaseModel):
    """Request to submit feedback on a result."""
    candidate_artist_id: str
    verdict: str  # "accept" or "reject"
    seed_artists: Optional[list[str]] = None
    omission_score: Optional[float] = None


class FeedbackResponse(BaseModel):
    """Response from feedback submission."""
    success: bool
    message: str


class FeedbackStatsResponse(BaseModel):
    """Aggregate feedback statistics."""
    total_feedback: int
    accepts: int
    rejects: int
    unique_artists: int
    accept_rate: float


# =========================================================================
# AUTH ENDPOINTS
# =========================================================================

@app.get("/auth/spotify/url", response_model=AuthUrlResponse)
def get_spotify_auth_url():
    """Generate Spotify OAuth authorization URL."""
    if not SPOTIFY_CLIENT_ID:
        raise HTTPException(status_code=500, detail="Spotify client ID not configured")

    params = {
        "client_id": SPOTIFY_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": SPOTIFY_REDIRECT_URI,
        "scope": " ".join(SPOTIFY_SCOPES),
        "show_dialog": "true"
    }

    auth_url = f"{SPOTIFY_AUTH_URL}?{urllib.parse.urlencode(params)}"
    return AuthUrlResponse(auth_url=auth_url)


@app.get("/auth/spotify/callback", response_model=TokenResponse)
async def spotify_callback(code: str = Query(...)):
    """Exchange authorization code for access token."""
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
# DIAGNOSIS ENDPOINT (STEP 1)
# =========================================================================

@app.get("/diagnosis", response_model=DiagnosisResponse)
async def run_diagnosis(
    access_token: str = Query(..., description="Spotify access token")
):
    """
    Run a diagnosis of the user's listening profile.

    This is REQUIRED before running an omission scan.
    Shows:
    - Recurring artists across time windows
    - Top genres (weighted)
    - Audio feature profile
    - Template-based observations
    """
    try:
        client = SpotifyClient(access_token)

        # Build full context across all time windows
        context = await build_user_context(client, time_range="all")

        # Format recurring artists
        recurring_artists = []
        for artist_id in context.recurring_artist_ids[:15]:
            if artist_id in context.artists:
                a = context.artists[artist_id]
                recurring_artists.append(RecurringArtist(
                    id=a.id,
                    name=a.name,
                    genres=a.genres[:5],
                    popularity=a.popularity,
                    in_short_term=a.in_short_term,
                    in_medium_term=a.in_medium_term,
                    in_long_term=a.in_long_term,
                    recurrence_score=a.recurrence_score,
                ))

        # Format top genres
        sorted_genres = sorted(
            context.genre_weights.items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]
        top_genres = [
            GenreWeight(genre=g, weight=round(w, 3))
            for g, w in sorted_genres
        ]

        # Format audio feature profile
        ap = context.audio_profile
        audio_profile = {
            "energy": {"center": round(ap.energy_center, 3)},
            "danceability": {"center": round(ap.danceability_center, 3)},
            "valence": {"center": round(ap.valence_center, 3)},
            "tempo": {"center": round(ap.tempo_center, 1)},
            "acousticness": {"center": round(ap.acousticness_center, 3)},
            "instrumentalness": {"center": round(ap.instrumentalness_center, 3)},
        }

        # Generate template-based notes
        notes = _generate_diagnosis_notes(context, recurring_artists, top_genres)

        return DiagnosisResponse(
            recurring_artists=recurring_artists,
            top_genres=top_genres,
            audio_feature_profile=audio_profile,
            notes=notes,
            total_artists_analyzed=len(context.artists),
            total_tracks_analyzed=len(context.known_track_ids),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Diagnosis failed: {str(e)}")


def _generate_diagnosis_notes(
    context: UserContext,
    recurring_artists: list[RecurringArtist],
    top_genres: list[GenreWeight]
) -> list[str]:
    """Generate template-based observations. No AI."""
    notes = []

    # Cluster summary
    if top_genres:
        genre_names = [g.genre for g in top_genres[:3]]
        notes.append(f"Your listening clusters around: {', '.join(genre_names)}.")

    # Recurring artists summary
    if recurring_artists:
        artist_names = [a.name for a in recurring_artists[:3]]
        notes.append(f"Your most stable recurring artists: {', '.join(artist_names)}.")

    # Recurrence rate
    if context.artists:
        recurrence_rate = len(context.recurring_artist_ids) / len(context.artists) * 100
        if recurrence_rate > 50:
            notes.append("High listening stability: over 50% of artists appear across multiple time windows.")
        elif recurrence_rate < 20:
            notes.append("High variety: less than 20% of artists recur across time windows.")

    # Audio profile observations
    ap = context.audio_profile
    if ap.energy_center > 0.7:
        notes.append("Your listening skews high-energy.")
    elif ap.energy_center < 0.4:
        notes.append("Your listening skews low-energy/calm.")

    if ap.valence_center > 0.6:
        notes.append("Your listening tends toward positive/upbeat moods.")
    elif ap.valence_center < 0.4:
        notes.append("Your listening tends toward darker/melancholic moods.")

    return notes


# =========================================================================
# OMISSION SCAN ENDPOINT (STEP 2)
# =========================================================================

@app.get("/scan", response_model=OmissionScanResponse)
async def run_omission_scan(
    access_token: str = Query(..., description="Spotify access token"),
    min_popularity: int = Query(5, ge=0, le=100),
    max_popularity: int = Query(60, ge=0, le=100),
):
    """
    Run an omission scan to find structurally omitted artists.

    REQUIRES: Running diagnosis first (uses same context).

    Returns: Max 5 results, each with full justification.
    Only returns results that pass the confidence gate.
    """
    try:
        client = SpotifyClient(access_token)

        # Build context
        context = await build_user_context(client, time_range="all")

        # Expand candidates (requires 2+ seed support)
        candidates = await expand_candidates(
            client, context,
            max_candidates=100,
            min_popularity=min_popularity,
            max_popularity=max_popularity
        )

        if not candidates:
            return OmissionScanResponse(
                results=[],
                diagnosis_summary=_get_diagnosis_summary(context),
                candidates_evaluated=0,
                confidence_threshold_used=0.55,
            )

        # Score and filter by confidence gate
        top_results = get_top_recommendations(
            candidates, context, limit=MAX_RESULTS
        )

        # Format results with evidence
        results = []
        for scored in top_results:
            c = scored.candidate
            results.append(OmissionResultItem(
                artist_id=c.id,
                artist_name=c.name,
                sample_track_name=c.sample_track_name,
                genres=c.genres[:3],
                omission_score=round(scored.omission_score, 3),
                explanation=scored.explanation,
                evidence=EvidenceItem(
                    seed_artists=scored.seed_artists or [],
                    genre_overlap_count=scored.genre_overlap_count,
                    audio_similarity_score=scored.audio_similarity_score,
                    popularity=c.popularity,
                    earliest_album_year=scored.earliest_album_year,
                ),
            ))

        return OmissionScanResponse(
            results=results,
            diagnosis_summary=_get_diagnosis_summary(context),
            candidates_evaluated=len(candidates),
            confidence_threshold_used=0.55,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scan failed: {str(e)}")


def _get_diagnosis_summary(context: UserContext) -> str:
    """One-line summary of the diagnosis context."""
    top_genres = sorted(
        context.genre_weights.items(),
        key=lambda x: x[1],
        reverse=True
    )[:3]
    genre_str = ", ".join([g[0] for g in top_genres])
    return f"Based on {len(context.artists)} artists, {len(context.recurring_artist_ids)} recurring. Top genres: {genre_str}."


# =========================================================================
# FEEDBACK ENDPOINT (STEP 3)
# =========================================================================

@app.post("/feedback", response_model=FeedbackResponse)
def submit_feedback(request: FeedbackRequest):
    """
    Submit feedback on an omission scan result.

    verdict: "accept" or "reject"

    Feedback is used to:
    - Up-rank accepted artists (+0.10)
    - Down-rank rejected artists (-0.15)
    - Hard-exclude artists rejected 2+ times
    """
    if request.verdict not in ("accept", "reject"):
        raise HTTPException(status_code=400, detail="Verdict must be 'accept' or 'reject'")

    success = db.add_feedback(
        candidate_artist_id=request.candidate_artist_id,
        verdict=request.verdict,
        seed_artists=request.seed_artists,
        omission_score=request.omission_score,
    )

    if success:
        return FeedbackResponse(
            success=True,
            message=f"Feedback recorded: {request.verdict}"
        )
    else:
        return FeedbackResponse(
            success=False,
            message="Failed to record feedback"
        )


@app.get("/feedback/stats", response_model=FeedbackStatsResponse)
def get_feedback_stats():
    """Get aggregate feedback statistics."""
    stats = db.get_feedback_stats()
    return FeedbackStatsResponse(**stats)


@app.get("/feedback/history")
def get_feedback_history(limit: int = Query(50, ge=1, le=200)):
    """Get recent feedback history."""
    return {"feedback": db.get_feedback_history(limit)}


# =========================================================================
# HEALTH CHECK
# =========================================================================

@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "latent-search", "version": "0.2.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
