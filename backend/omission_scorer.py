"""
Omission Scoring System.

THE CORE ALGORITHM OF LATENT SEARCH.

For each candidate artist, computes an "omission score" that measures:
- High contextual similarity (should be in user's wheelhouse)
- Low user exposure (user hasn't heard them)
- Low playlist saturation (not over-recommended by algorithms)
- Penalized popularity (prefer less popular artists)
- Penalized recency (prefer older catalog)

High omission score = "This artist SHOULD be in your library, but isn't."
"""
from dataclasses import dataclass
from typing import Optional
from candidate_expander import CandidateArtist
from context_builder import UserContext, AudioFeatureProfile
from config import (
    OMISSION_WEIGHTS,
    POPULARITY_CEILING,
    RECENCY_CUTOFF_YEAR,
    MAX_RESULTS
)


@dataclass
class ScoredCandidate:
    """A candidate with computed omission score and explanation."""
    candidate: CandidateArtist

    # Component scores (all 0-1, higher = better for recommendation)
    contextual_similarity: float = 0.0
    exposure_score: float = 0.0      # 1.0 = no exposure (good)
    saturation_score: float = 0.0    # 1.0 = not saturated (good)
    popularity_score: float = 0.0    # 1.0 = unpopular (good)
    recency_score: float = 0.0       # 1.0 = old catalog (good)

    # Final omission score
    omission_score: float = 0.0

    # Human-readable explanation (template-based)
    explanation: str = ""


# =========================================================================
# EXPLANATION TEMPLATES (no generative text)
# =========================================================================
EXPLANATION_TEMPLATES = {
    "related_audio": "Frequently associated with artists you listen to, with matching sonic character.",
    "related_genre": "Connected to your recurring artists, sharing genre overlap.",
    "related_obscure": "Related to artists you love, but rarely surfaces in algorithmic playlists.",
    "old_catalog": "Strong contextual fit with a catalog predating 2018, often overlooked by recency-biased systems.",
    "low_popularity": "Matches your listening context but lacks the popularity that drives algorithmic visibility.",
    "genre_deep_cut": "Fits your genre profile but exists outside mainstream playlist circulation.",
}


def score_candidates(
    candidates: list[CandidateArtist],
    context: UserContext
) -> list[ScoredCandidate]:
    """
    Score all candidates and return sorted by omission score.

    The omission score identifies artists that:
    1. SHOULD be relevant to the user (high contextual similarity)
    2. But ARE NOT in their library (low exposure)
    3. And ARE NOT over-promoted by algorithms (low saturation, low popularity)
    """
    scored = []

    for candidate in candidates:
        scored_candidate = _score_single_candidate(candidate, context)
        scored.append(scored_candidate)

    # Sort by omission score (highest first)
    scored.sort(key=lambda s: s.omission_score, reverse=True)

    return scored


def get_top_recommendations(
    candidates: list[CandidateArtist],
    context: UserContext,
    limit: int = MAX_RESULTS
) -> list[ScoredCandidate]:
    """
    Score candidates and return top N recommendations.
    This is the main entry point for the recommendation engine.
    """
    scored = score_candidates(candidates, context)
    return scored[:limit]


def _score_single_candidate(
    candidate: CandidateArtist,
    context: UserContext
) -> ScoredCandidate:
    """
    Compute omission score for a single candidate.

    OMISSION SCORE FORMULA:
    score = (contextual_similarity * w1) +
            (exposure_score * w2) +
            (saturation_score * w3) +
            (popularity_score * w4) +
            (recency_score * w5)

    Where all component scores are 0-1 and higher = better for recommendation.
    """
    # =========================================================================
    # COMPONENT 1: Contextual Similarity
    # How well does this artist fit the user's listening context?
    # =========================================================================
    contextual_similarity = _compute_contextual_similarity(candidate, context)

    # =========================================================================
    # COMPONENT 2: Exposure Score
    # Has the user already been exposed to this artist?
    # Since candidates are pre-filtered, this should always be 1.0
    # =========================================================================
    exposure_score = 1.0 if candidate.id not in context.known_artist_ids else 0.0

    # =========================================================================
    # COMPONENT 3: Playlist Saturation Score
    # Is this artist over-represented in algorithmic playlists?
    # We estimate this from popularity (saturated artists tend to be popular)
    # =========================================================================
    # Higher popularity = more saturation = lower score
    saturation_score = _compute_saturation_score(candidate.popularity)

    # =========================================================================
    # COMPONENT 4: Popularity Score
    # Explicitly penalize popular artists
    # =========================================================================
    popularity_score = _compute_popularity_score(candidate.popularity)

    # =========================================================================
    # COMPONENT 5: Recency Score
    # Penalize recent releases, favor older catalog
    # =========================================================================
    recency_score = _compute_recency_score(candidate.earliest_release_year)

    # =========================================================================
    # FINAL OMISSION SCORE (weighted sum)
    # =========================================================================
    weights = OMISSION_WEIGHTS
    omission_score = (
        contextual_similarity * weights["contextual_similarity"] +
        exposure_score * weights["exposure_penalty"] +
        saturation_score * weights["playlist_saturation"] +
        popularity_score * weights["popularity_penalty"] +
        recency_score * weights["recency_penalty"]
    )

    # =========================================================================
    # GENERATE EXPLANATION (template-based, no AI)
    # =========================================================================
    explanation = _generate_explanation(
        candidate, contextual_similarity, popularity_score, recency_score
    )

    return ScoredCandidate(
        candidate=candidate,
        contextual_similarity=contextual_similarity,
        exposure_score=exposure_score,
        saturation_score=saturation_score,
        popularity_score=popularity_score,
        recency_score=recency_score,
        omission_score=omission_score,
        explanation=explanation
    )


def _compute_contextual_similarity(
    candidate: CandidateArtist,
    context: UserContext
) -> float:
    """
    Compute how similar this candidate is to user's listening context.
    Combines genre overlap and audio feature similarity.
    """
    # Genre overlap (already computed in candidate expansion)
    genre_score = getattr(candidate, 'genre_overlap', 0.0)

    # Audio feature similarity
    audio_score = 0.0
    if candidate.audio_features:
        audio_score = _compute_audio_similarity(
            candidate.audio_features,
            context.audio_profile
        )

    # Combine (weight audio features slightly higher as more objective)
    if audio_score > 0:
        return (genre_score * 0.4) + (audio_score * 0.6)
    else:
        return genre_score


def _compute_audio_similarity(
    candidate_features: dict,
    user_profile: AudioFeatureProfile
) -> float:
    """
    Compute how similar candidate's audio features are to user's profile.
    Returns 0-1 score.
    """
    similarities = []

    # Compare each feature to user's center value
    feature_pairs = [
        ("energy", user_profile.energy_center),
        ("danceability", user_profile.danceability_center),
        ("valence", user_profile.valence_center),
        ("acousticness", user_profile.acousticness_center),
        ("instrumentalness", user_profile.instrumentalness_center),
    ]

    for feature_name, user_center in feature_pairs:
        candidate_value = candidate_features.get(feature_name)
        if candidate_value is not None:
            # Compute distance (0-1 scale for these features)
            distance = abs(candidate_value - user_center)
            similarity = 1 - distance
            similarities.append(similarity)

    # Tempo needs special handling (not 0-1 scale)
    if candidate_features.get("tempo") and user_profile.tempo_center:
        tempo_diff = abs(candidate_features["tempo"] - user_profile.tempo_center)
        # Normalize: 40 BPM difference = 0 similarity
        tempo_similarity = max(0, 1 - (tempo_diff / 40))
        similarities.append(tempo_similarity)

    if not similarities:
        return 0.0

    return sum(similarities) / len(similarities)


def _compute_saturation_score(popularity: int) -> float:
    """
    Estimate playlist saturation from popularity.
    High popularity = high saturation = low score.

    Returns 0-1 where 1.0 = not saturated (good for recommendation).
    """
    # Popularity is 0-100
    # We want to penalize high popularity
    # Below 30 popularity = likely not saturated
    # Above 70 popularity = likely very saturated

    if popularity <= 30:
        return 1.0
    elif popularity >= 70:
        return 0.2
    else:
        # Linear interpolation
        return 1.0 - ((popularity - 30) / 40) * 0.8


def _compute_popularity_score(popularity: int) -> float:
    """
    Explicit popularity penalty.
    Returns 0-1 where 1.0 = unpopular (good for recommendation).
    """
    # Invert popularity (0-100 -> 1.0-0.0)
    # But use ceiling to cap the penalty
    capped_popularity = min(popularity, POPULARITY_CEILING)
    return 1.0 - (capped_popularity / 100)


def _compute_recency_score(earliest_year: Optional[int]) -> float:
    """
    Penalize recent releases, favor older catalog.
    Returns 0-1 where 1.0 = old catalog (good for recommendation).
    """
    if earliest_year is None:
        return 0.5  # Unknown = neutral

    current_year = 2024

    if earliest_year <= RECENCY_CUTOFF_YEAR:
        # Pre-2018: full score
        return 1.0
    elif earliest_year >= current_year - 1:
        # Very recent (last 2 years): heavy penalty
        return 0.2
    else:
        # Linear interpolation between 2018 and recent
        years_since_cutoff = earliest_year - RECENCY_CUTOFF_YEAR
        max_years = current_year - 1 - RECENCY_CUTOFF_YEAR
        return 1.0 - (years_since_cutoff / max_years) * 0.8


def _generate_explanation(
    candidate: CandidateArtist,
    contextual_similarity: float,
    popularity_score: float,
    recency_score: float
) -> str:
    """
    Generate a human-readable explanation using templates only.
    No AI-generated text.
    """
    # Determine primary reason for recommendation
    if recency_score >= 0.9:
        return EXPLANATION_TEMPLATES["old_catalog"]

    if popularity_score >= 0.7:
        return EXPLANATION_TEMPLATES["low_popularity"]

    if candidate.source == "related":
        if candidate.audio_features:
            return EXPLANATION_TEMPLATES["related_audio"]
        else:
            return EXPLANATION_TEMPLATES["related_genre"]

    if contextual_similarity >= 0.6:
        return EXPLANATION_TEMPLATES["genre_deep_cut"]

    return EXPLANATION_TEMPLATES["related_obscure"]
