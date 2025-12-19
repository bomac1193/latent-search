"""
Omission Scoring System.

THE CORE ALGORITHM OF LATENT SEARCH.

For each candidate artist, computes an "omission score" that measures:
- High contextual similarity (should be in user's wheelhouse)
- Low user exposure (user hasn't heard them)
- Low playlist saturation (not over-recommended by algorithms)
- Penalized popularity (prefer less popular artists)
- Penalized recency (prefer older catalog)

CONFIDENCE GATE: Only returns candidates that pass all thresholds.
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
    MAX_RESULTS,
    MIN_SEED_SUPPORT,
    MIN_CONTEXTUAL_SIMILARITY,
    MAX_POPULARITY_GATE,
)
import database as db


@dataclass
class ScoredCandidate:
    """A candidate with computed omission score, evidence, and explanation."""
    candidate: CandidateArtist

    # Component scores (all 0-1, higher = better for recommendation)
    contextual_similarity: float = 0.0
    exposure_score: float = 0.0      # 1.0 = no exposure (good)
    saturation_score: float = 0.0    # 1.0 = not saturated (good)
    popularity_score: float = 0.0    # 1.0 = unpopular (good)
    recency_score: float = 0.0       # 1.0 = old catalog (good)

    # Final omission score
    omission_score: float = 0.0

    # Confidence gate result
    is_confident: bool = False

    # Human-readable explanation (template-based)
    explanation: str = ""

    # EVIDENCE FIELDS (for transparency)
    seed_artists: list[str] = None       # Names of seed artists that linked here
    genre_overlap_count: int = 0         # Number of genres that overlap
    audio_similarity_score: float = 0.0  # Audio feature similarity
    earliest_album_year: Optional[int] = None


# =========================================================================
# EXPLANATION TEMPLATES (no generative text)
# =========================================================================
EXPLANATION_TEMPLATES = {
    "structural_omission": "Related to {n} of your recurring artists, yet absent from your library.",
    "deep_genre_fit": "Strong match to your genre profile ({genres}), with low algorithmic visibility.",
    "old_catalog": "Established catalog (since {year}) matching your context, often missed by recency bias.",
    "low_popularity": "Contextually relevant but under-promoted (popularity: {pop}).",
    "multi_seed": "Connected to multiple stable preferences: {seeds}.",
}


def score_candidates(
    candidates: list[CandidateArtist],
    context: UserContext,
    apply_feedback: bool = True
) -> list[ScoredCandidate]:
    """
    Score all candidates and return sorted by omission score.
    Only returns candidates that pass the confidence gate.
    """
    scored = []

    # Get feedback history for score adjustments
    feedback_adjustments = {}
    if apply_feedback:
        feedback_adjustments = db.get_feedback_adjustments()

    # Dynamic seed support threshold based on recurring artists
    num_recurring = len(context.recurring_artist_ids)
    effective_min_seed = MIN_SEED_SUPPORT if num_recurring >= 3 else 1

    for candidate in candidates:
        scored_candidate = _score_single_candidate(
            candidate, context, feedback_adjustments, effective_min_seed
        )

        # CONFIDENCE GATE: Only include if confident
        if scored_candidate.is_confident:
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
    Strict cap at MAX_RESULTS (5).
    """
    scored = score_candidates(candidates, context, apply_feedback=True)

    # STRICT CAP: never return more than MAX_RESULTS
    capped_limit = min(limit, MAX_RESULTS)

    return scored[:capped_limit]


def _score_single_candidate(
    candidate: CandidateArtist,
    context: UserContext,
    feedback_adjustments: dict[str, float],
    effective_min_seed: int = MIN_SEED_SUPPORT
) -> ScoredCandidate:
    """
    Compute omission score for a single candidate.

    OMISSION SCORE FORMULA:
    score = (contextual_similarity * w1) +
            (exposure_score * w2) +
            (saturation_score * w3) +
            (popularity_score * w4) +
            (recency_score * w5)

    CONFIDENCE GATE:
    - seed_support_count >= 2
    - contextual_similarity >= 0.55
    - popularity <= 70
    """
    # =========================================================================
    # COMPONENT 1: Contextual Similarity
    # =========================================================================
    contextual_similarity = _compute_contextual_similarity(candidate, context)

    # =========================================================================
    # COMPONENT 2: Exposure Score (pre-filtered, should be 1.0)
    # =========================================================================
    exposure_score = 1.0 if candidate.id not in context.known_artist_ids else 0.0

    # =========================================================================
    # COMPONENT 3: Playlist Saturation Score
    # =========================================================================
    saturation_score = _compute_saturation_score(candidate.popularity)

    # =========================================================================
    # COMPONENT 4: Popularity Score
    # =========================================================================
    popularity_score = _compute_popularity_score(candidate.popularity)

    # =========================================================================
    # COMPONENT 5: Recency Score
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
    # APPLY FEEDBACK ADJUSTMENTS
    # =========================================================================
    if candidate.id in feedback_adjustments:
        omission_score += feedback_adjustments[candidate.id]
        omission_score = max(0.0, min(1.0, omission_score))  # Clamp to 0-1

    # =========================================================================
    # CONFIDENCE GATE (dynamic based on recurring artists)
    # =========================================================================
    is_confident = (
        candidate.seed_support_count >= effective_min_seed and
        contextual_similarity >= MIN_CONTEXTUAL_SIMILARITY and
        candidate.popularity <= MAX_POPULARITY_GATE
    )

    # =========================================================================
    # COMPUTE EVIDENCE FIELDS
    # =========================================================================
    genre_overlap_count = _count_genre_overlap(candidate.genres, context.genre_weights)

    audio_similarity = 0.0
    if candidate.audio_features:
        audio_similarity = _compute_audio_similarity(
            candidate.audio_features,
            context.audio_profile
        )

    # =========================================================================
    # GENERATE EXPLANATION (template-based, no AI)
    # =========================================================================
    explanation = _generate_explanation(
        candidate=candidate,
        contextual_similarity=contextual_similarity,
        popularity_score=popularity_score,
        recency_score=recency_score,
        genre_overlap_count=genre_overlap_count,
    )

    return ScoredCandidate(
        candidate=candidate,
        contextual_similarity=contextual_similarity,
        exposure_score=exposure_score,
        saturation_score=saturation_score,
        popularity_score=popularity_score,
        recency_score=recency_score,
        omission_score=omission_score,
        is_confident=is_confident,
        explanation=explanation,
        # Evidence fields
        seed_artists=candidate.seed_artist_names,
        genre_overlap_count=genre_overlap_count,
        audio_similarity_score=round(audio_similarity, 3),
        earliest_album_year=candidate.earliest_release_year,
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

    # Boost from seed support (structural connection)
    seed_boost = min(0.2, candidate.seed_support_count * 0.05)

    # Combine
    if audio_score > 0:
        base_score = (genre_score * 0.4) + (audio_score * 0.4) + seed_boost
    else:
        base_score = (genre_score * 0.8) + seed_boost

    return min(1.0, base_score)


def _compute_audio_similarity(
    candidate_features: dict,
    user_profile: AudioFeatureProfile
) -> float:
    """
    Compute how similar candidate's audio features are to user's profile.
    Returns 0-1 score.
    """
    similarities = []

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
            distance = abs(candidate_value - user_center)
            similarity = 1 - distance
            similarities.append(similarity)

    # Tempo needs special handling
    if candidate_features.get("tempo") and user_profile.tempo_center:
        tempo_diff = abs(candidate_features["tempo"] - user_profile.tempo_center)
        tempo_similarity = max(0, 1 - (tempo_diff / 40))
        similarities.append(tempo_similarity)

    if not similarities:
        return 0.0

    return sum(similarities) / len(similarities)


def _compute_saturation_score(popularity: int) -> float:
    """
    Estimate playlist saturation from popularity.
    High popularity = high saturation = low score.
    """
    if popularity <= 30:
        return 1.0
    elif popularity >= 70:
        return 0.2
    else:
        return 1.0 - ((popularity - 30) / 40) * 0.8


def _compute_popularity_score(popularity: int) -> float:
    """
    Explicit popularity penalty.
    Returns 0-1 where 1.0 = unpopular (good for recommendation).
    """
    capped_popularity = min(popularity, POPULARITY_CEILING)
    return 1.0 - (capped_popularity / 100)


def _compute_recency_score(earliest_year: Optional[int]) -> float:
    """
    Penalize recent releases, favor older catalog.
    """
    if earliest_year is None:
        return 0.5  # Unknown = neutral

    current_year = 2024

    if earliest_year <= RECENCY_CUTOFF_YEAR:
        return 1.0
    elif earliest_year >= current_year - 1:
        return 0.2
    else:
        years_since_cutoff = earliest_year - RECENCY_CUTOFF_YEAR
        max_years = current_year - 1 - RECENCY_CUTOFF_YEAR
        return 1.0 - (years_since_cutoff / max_years) * 0.8


def _count_genre_overlap(
    candidate_genres: list[str],
    user_genre_weights: dict[str, float]
) -> int:
    """Count how many of the candidate's genres match user's profile."""
    count = 0
    for genre in candidate_genres:
        if genre in user_genre_weights:
            count += 1
        else:
            for user_genre in user_genre_weights:
                if genre in user_genre or user_genre in genre:
                    count += 1
                    break
    return count


def _generate_explanation(
    candidate: CandidateArtist,
    contextual_similarity: float,
    popularity_score: float,
    recency_score: float,
    genre_overlap_count: int,
) -> str:
    """
    Generate a human-readable explanation using templates only.
    No AI-generated text.
    """
    # Multi-seed structural omission (best case)
    if candidate.seed_support_count >= 3:
        seed_names = ", ".join(candidate.seed_artist_names[:3])
        return EXPLANATION_TEMPLATES["multi_seed"].format(seeds=seed_names)

    # Standard structural omission
    if candidate.seed_support_count >= 2:
        return EXPLANATION_TEMPLATES["structural_omission"].format(
            n=candidate.seed_support_count
        )

    # Old catalog
    if recency_score >= 0.9 and candidate.earliest_release_year:
        return EXPLANATION_TEMPLATES["old_catalog"].format(
            year=candidate.earliest_release_year
        )

    # Low popularity
    if popularity_score >= 0.6:
        return EXPLANATION_TEMPLATES["low_popularity"].format(
            pop=candidate.popularity
        )

    # Deep genre fit
    if genre_overlap_count >= 2:
        genres = ", ".join(candidate.genres[:3])
        return EXPLANATION_TEMPLATES["deep_genre_fit"].format(genres=genres)

    # Fallback
    return EXPLANATION_TEMPLATES["structural_omission"].format(
        n=candidate.seed_support_count or 1
    )
