# Latent Search

A diagnostic instrument for music discovery through omission scoring. Surfaces artists structurally omitted from your listening despite high contextual fit.

## What This Is

Latent Search is **NOT a search tool**. It's a diagnostic instrument that:

1. **Diagnoses** your listening profile across time windows
2. **Scans** for structurally omitted artists (high context fit, zero exposure)
3. **Collects feedback** to improve future scans

**This is not a consumer product.** It's a testbed for evaluating omission-based discovery.

## Flow

```
Connect Spotify → Run Diagnosis → Run Omission Scan → Provide Feedback
```

### Step 1: Diagnosis

Analyzes your Spotify listening history across three time windows:

- **Short-term** (~4 weeks): Recent listening
- **Medium-term** (~6 months): Stable patterns
- **Long-term** (years): Core identity

Produces:
- **Recurring artists**: Artists appearing in 2+ time windows (stable preferences)
- **Top genres**: Weighted by recurrence
- **Audio profile**: Energy, danceability, valence, acousticness centers
- **Template-based notes**: Observations about your listening patterns

### Step 2: Omission Scan

Uses your diagnosis to find artists you *should* know but don't.

**Key constraint**: A candidate must be related to **2+ recurring artists** to be eligible. This ensures structural omission, not random adjacency.

Returns **max 5 results** with:
- Artist name + sample track
- Omission score
- Template-based explanation
- Evidence (seed artists, genre overlap, audio similarity)

### Step 3: Feedback

For each result, provide feedback:
- **"Makes sense"** → +0.10 score boost for future scans
- **"Not for me"** → -0.15 score penalty
- **2+ rejections** → Hard exclude from future results

Feedback persists across sessions.

## Omission Scoring Algorithm

Each candidate receives an **omission score**:

| Component | Weight | Description |
|-----------|--------|-------------|
| Contextual Similarity | 35% | Genre overlap + audio feature match |
| Exposure Penalty | 25% | Reward for being absent from history |
| Playlist Saturation | 15% | Penalty for high-playlist-presence |
| Popularity Penalty | 15% | Penalty for popular artists |
| Recency Penalty | 10% | Penalty for post-2018 debuts |

**Confidence Gate**: Only returns candidates that pass ALL thresholds:
- 2+ seed artist support
- 55%+ contextual similarity
- Popularity ≤ 70

## Setup

### Prerequisites

- Python 3.10+
- Node.js 18+
- Spotify Developer Account

### Quick Start

```bash
# Clone and setup
git clone <repo>
cd latent-search

# Start everything
./start.sh
```

Or manually:

### Backend

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your Spotify credentials:
# SPOTIFY_CLIENT_ID=your_client_id
# SPOTIFY_CLIENT_SECRET=your_client_secret

# Run server
uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Spotify App Setup

1. Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Create a new app
3. Set redirect URI to `http://localhost:5173/callback`
4. Copy Client ID and Client Secret to `.env`

## API Endpoints

### Auth

- `GET /auth/spotify/url` - Get OAuth authorization URL
- `GET /auth/spotify/callback?code=...` - Exchange code for token

### Diagnosis

- `GET /diagnosis?access_token=...` - Run listening profile diagnosis

Returns:
```json
{
  "recurring_artists": [...],
  "top_genres": [{"genre": "...", "weight": 0.15}],
  "audio_feature_profile": {...},
  "notes": ["Your listening clusters around..."],
  "total_artists_analyzed": 45,
  "total_tracks_analyzed": 120
}
```

### Omission Scan

- `GET /scan?access_token=...&min_popularity=5&max_popularity=60`

Returns max 5 results:
```json
{
  "results": [{
    "artist_id": "...",
    "artist_name": "...",
    "omission_score": 0.72,
    "explanation": "Related to 3 of your recurring artists...",
    "evidence": {
      "seed_artists": ["Artist A", "Artist B"],
      "genre_overlap_count": 4,
      "audio_similarity_score": 0.68
    }
  }],
  "diagnosis_summary": "Based on 45 artists, 12 recurring...",
  "candidates_evaluated": 87,
  "confidence_threshold_used": 0.55
}
```

### Feedback

- `POST /feedback` - Submit accept/reject feedback
- `GET /feedback/stats` - Get aggregate statistics
- `GET /feedback/history` - Get recent feedback

## Project Structure

```
latent-search/
├── backend/
│   ├── main.py              # FastAPI app, all endpoints
│   ├── spotify_client.py    # Spotify API wrapper
│   ├── context_builder.py   # Longitudinal profile builder
│   ├── candidate_expander.py # Candidate generation (2+ seed support)
│   ├── omission_scorer.py   # Core algorithm + confidence gate
│   ├── database.py          # SQLite feedback storage
│   ├── config.py            # Algorithm configuration
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.tsx          # Diagnostic instrument UI
│   │   ├── api.ts           # Backend API client
│   │   └── App.css          # Styling
│   └── package.json
├── start.sh                 # Quick start script
└── README.md
```

## Configuration

Key settings in `backend/config.py`:

```python
# Algorithm weights
OMISSION_WEIGHTS = {
    "contextual_similarity": 0.35,
    "exposure_penalty": 0.25,
    "playlist_saturation": 0.15,
    "popularity_penalty": 0.15,
    "recency_penalty": 0.10,
}

# Thresholds
MAX_RESULTS = 5              # Never return more than 5
MIN_SEED_SUPPORT = 2         # Must relate to 2+ recurring artists
MIN_CONTEXTUAL_SIMILARITY = 0.55
MAX_POPULARITY_GATE = 70
POPULARITY_CEILING = 60
RECENCY_CUTOFF_YEAR = 2018
```

## Feedback Adjustments

```python
ACCEPT_BOOST = 0.10   # Add to score when accepted
REJECT_PENALTY = 0.15 # Subtract from score when rejected
HARD_REJECT_COUNT = 2 # Exclude after 2 rejections
```

## What This Doesn't Do

- Generate playlists
- Optimize for engagement
- Use AI text generation
- Return more than 5 results
- Support infinite scroll
- Have a search bar
- Show external sources

These are intentional constraints for a diagnostic instrument.

## Evaluation Criteria

A successful result:
1. Is **relevant** (fits listening context)
2. Is **unfamiliar** (not in library)
3. Is **explainable** (user can see the evidence)
4. Does **not** feel like a standard Spotify recommendation

## License

Research use only.
