"""
Unit tests for Latent Search core modules.

Run with: pytest test_core.py -v
"""
import pytest
import os
import tempfile
from dataclasses import dataclass
from typing import Optional

# Import modules to test
from omission_scorer import (
    _compute_popularity_score,
    _compute_recency_score,
    _compute_saturation_score,
    _count_genre_overlap,
    _generate_explanation,
    ScoredCandidate,
)
from candidate_expander import CandidateArtist, _compute_genre_overlap
from config import (
    MIN_SEED_SUPPORT,
    MIN_CONTEXTUAL_SIMILARITY,
    MAX_POPULARITY_GATE,
    MAX_RESULTS,
)


# =========================================================================
# POPULARITY SCORING TESTS
# =========================================================================

class TestPopularityScore:
    """Test popularity score calculation."""

    def test_low_popularity_high_score(self):
        """Low popularity artists should get high scores."""
        score = _compute_popularity_score(10)
        assert score >= 0.9

    def test_high_popularity_low_score(self):
        """High popularity artists should get low scores."""
        score = _compute_popularity_score(90)
        assert score <= 0.4

    def test_moderate_popularity(self):
        """Moderate popularity should get moderate score."""
        score = _compute_popularity_score(50)
        assert 0.4 <= score <= 0.6

    def test_zero_popularity(self):
        """Zero popularity should get maximum score."""
        score = _compute_popularity_score(0)
        assert score == 1.0

    def test_max_popularity(self):
        """Max popularity should get minimum score."""
        score = _compute_popularity_score(100)
        assert score <= 0.4


# =========================================================================
# RECENCY SCORING TESTS
# =========================================================================

class TestRecencyScore:
    """Test recency score calculation."""

    def test_old_catalog_high_score(self):
        """Pre-2018 artists should get high score."""
        score = _compute_recency_score(2010)
        assert score == 1.0

    def test_recent_catalog_low_score(self):
        """Recent artists should get low score."""
        score = _compute_recency_score(2024)
        assert score <= 0.3

    def test_unknown_year_neutral(self):
        """Unknown year should get neutral score."""
        score = _compute_recency_score(None)
        assert score == 0.5

    def test_cutoff_year_full_score(self):
        """2018 should get full score."""
        score = _compute_recency_score(2018)
        assert score == 1.0


# =========================================================================
# SATURATION SCORING TESTS
# =========================================================================

class TestSaturationScore:
    """Test playlist saturation score calculation."""

    def test_low_popularity_not_saturated(self):
        """Low popularity = not saturated = high score."""
        score = _compute_saturation_score(20)
        assert score == 1.0

    def test_high_popularity_saturated(self):
        """High popularity = saturated = low score."""
        score = _compute_saturation_score(80)
        assert score <= 0.3


# =========================================================================
# GENRE OVERLAP TESTS
# =========================================================================

class TestGenreOverlap:
    """Test genre overlap calculation."""

    def test_exact_match(self):
        """Exact genre matches should count."""
        candidate_genres = ["indie rock", "alternative"]
        user_weights = {"indie rock": 0.5, "alternative": 0.3}
        count = _count_genre_overlap(candidate_genres, user_weights)
        assert count == 2

    def test_partial_match(self):
        """Partial matches (substring) should count."""
        candidate_genres = ["indie rock"]
        user_weights = {"rock": 0.5}
        count = _count_genre_overlap(candidate_genres, user_weights)
        assert count >= 1

    def test_no_match(self):
        """No overlap should return 0."""
        candidate_genres = ["hip-hop", "rap"]
        user_weights = {"classical": 0.5, "jazz": 0.3}
        count = _count_genre_overlap(candidate_genres, user_weights)
        assert count == 0

    def test_empty_inputs(self):
        """Empty inputs should return 0."""
        assert _count_genre_overlap([], {"rock": 0.5}) == 0
        assert _count_genre_overlap(["rock"], {}) == 0


# =========================================================================
# CANDIDATE GENRE OVERLAP TESTS
# =========================================================================

class TestCandidateGenreOverlap:
    """Test candidate expander genre overlap calculation."""

    def test_direct_genre_overlap(self):
        """Direct genre matches should score high."""
        candidate_genres = ["indie rock", "alternative rock"]
        user_weights = {"indie rock": 0.4, "alternative rock": 0.3}
        score = _compute_genre_overlap(candidate_genres, user_weights)
        assert score > 0.3

    def test_no_overlap_zero_score(self):
        """No overlap should give 0."""
        candidate_genres = ["metal", "death metal"]
        user_weights = {"jazz": 0.5, "classical": 0.5}
        score = _compute_genre_overlap(candidate_genres, user_weights)
        assert score == 0.0


# =========================================================================
# CONFIGURATION TESTS
# =========================================================================

class TestConfiguration:
    """Test configuration values are sensible."""

    def test_min_seed_support(self):
        """MIN_SEED_SUPPORT should be at least 2."""
        assert MIN_SEED_SUPPORT >= 2

    def test_max_results_cap(self):
        """MAX_RESULTS should be 5 or less."""
        assert MAX_RESULTS <= 5

    def test_contextual_similarity_threshold(self):
        """Contextual similarity threshold should be reasonable."""
        assert 0.4 <= MIN_CONTEXTUAL_SIMILARITY <= 0.7

    def test_popularity_gate(self):
        """Popularity gate should exclude very popular artists."""
        assert MAX_POPULARITY_GATE <= 80


# =========================================================================
# EXPLANATION GENERATION TESTS
# =========================================================================

class TestExplanationGeneration:
    """Test template-based explanation generation."""

    def test_multi_seed_explanation(self):
        """High seed support should mention seeds."""
        candidate = CandidateArtist(
            id="test",
            name="Test Artist",
            genres=["rock"],
            popularity=30,
            source="related_artist",
            seed_support_count=3,
            seed_artist_names=["Artist A", "Artist B", "Artist C"],
        )
        explanation = _generate_explanation(
            candidate=candidate,
            contextual_similarity=0.7,
            popularity_score=0.7,
            recency_score=0.5,
            genre_overlap_count=2,
        )
        assert "Artist A" in explanation or "preferences" in explanation.lower()

    def test_structural_omission_explanation(self):
        """2+ seed support should mention structural connection."""
        candidate = CandidateArtist(
            id="test",
            name="Test Artist",
            genres=["rock"],
            popularity=30,
            source="related_artist",
            seed_support_count=2,
            seed_artist_names=["Artist A", "Artist B"],
        )
        explanation = _generate_explanation(
            candidate=candidate,
            contextual_similarity=0.7,
            popularity_score=0.5,
            recency_score=0.5,
            genre_overlap_count=2,
        )
        assert "2" in explanation or "recurring" in explanation.lower()


# =========================================================================
# DATABASE TESTS (uses temp file)
# =========================================================================

class TestDatabase:
    """Test database operations with temporary file."""

    @pytest.fixture(autouse=True)
    def setup_temp_db(self, tmp_path):
        """Setup temporary database for each test."""
        import database as db
        # Override DB path
        self.original_db_path = db.DB_PATH
        db.DB_PATH = str(tmp_path / "test.db")
        db.init_db()
        yield
        # Restore original path
        db.DB_PATH = self.original_db_path

    def test_add_feedback(self):
        """Test adding feedback."""
        import database as db
        success = db.add_feedback(
            candidate_artist_id="artist123",
            verdict="accept",
            seed_artists=["seed1", "seed2"],
            omission_score=0.75,
        )
        assert success is True

    def test_reject_feedback(self):
        """Test adding reject feedback."""
        import database as db
        success = db.add_feedback(
            candidate_artist_id="artist456",
            verdict="reject",
        )
        assert success is True

    def test_invalid_verdict(self):
        """Invalid verdict should return False."""
        import database as db
        success = db.add_feedback(
            candidate_artist_id="artist789",
            verdict="invalid",
        )
        assert success is False

    def test_feedback_stats(self):
        """Test feedback statistics."""
        import database as db
        # Add some feedback
        db.add_feedback("a1", "accept")
        db.add_feedback("a2", "accept")
        db.add_feedback("a3", "reject")

        stats = db.get_feedback_stats()
        assert stats["total_feedback"] == 3
        assert stats["accepts"] == 2
        assert stats["rejects"] == 1

    def test_hard_exclusion(self):
        """Test hard exclusion after 2 rejects."""
        import database as db
        # Reject same artist twice
        db.add_feedback("bad_artist", "reject")
        db.add_feedback("bad_artist", "reject")

        excluded = db.get_excluded_artists()
        assert "bad_artist" in excluded

    def test_feedback_adjustments(self):
        """Test feedback adjustments calculation."""
        import database as db
        # Accept an artist
        db.add_feedback("good_artist", "accept")

        adjustments = db.get_feedback_adjustments()
        assert adjustments.get("good_artist", 0) > 0  # Positive boost


# =========================================================================
# RUN TESTS
# =========================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
