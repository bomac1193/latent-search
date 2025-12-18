"""
Configuration for Latent Search backend.
Load Spotify API credentials from environment variables.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Spotify OAuth Configuration
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "")
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI", "http://localhost:5173/callback")

# Spotify API Base URLs
SPOTIFY_AUTH_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_API_BASE = "https://api.spotify.com/v1"

# Required Spotify Scopes
SPOTIFY_SCOPES = [
    "user-top-read",           # Top artists and tracks
    "user-read-recently-played", # Recently played tracks
    "user-library-read",       # Saved tracks
]

# Algorithm Configuration
# Weights for omission score calculation
OMISSION_WEIGHTS = {
    "contextual_similarity": 0.35,  # How well artist fits user's context
    "exposure_penalty": 0.25,       # Penalize if user has heard them
    "playlist_saturation": 0.15,    # Penalize playlist-dominant artists
    "popularity_penalty": 0.15,     # Penalize popular artists
    "recency_penalty": 0.10,        # Penalize recent releases
}

# Popularity threshold (0-100, lower = less popular = better)
POPULARITY_CEILING = 60

# Release year cutoff for recency penalty
RECENCY_CUTOFF_YEAR = 2018

# Maximum results to return
MAX_RESULTS = 7
