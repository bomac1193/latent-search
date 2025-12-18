import { useState, useEffect } from 'react';
import { getSpotifyAuthUrl, exchangeCodeForToken, runLatentSearch, Recommendation, ContextSummary } from './api';
import './App.css';

type AppState = 'disconnected' | 'connected' | 'searching' | 'results' | 'error';

function App() {
  const [state, setState] = useState<AppState>('disconnected');
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [contextSummary, setContextSummary] = useState<ContextSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expandedItems, setExpandedItems] = useState<Set<string>>(new Set());

  // Check for OAuth callback on mount
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get('code');

    if (code) {
      // Clear URL params
      window.history.replaceState({}, '', '/');

      // Exchange code for token
      exchangeCodeForToken(code)
        .then((data) => {
          setAccessToken(data.access_token);
          setState('connected');
          // Store in session for page refreshes
          sessionStorage.setItem('spotify_token', data.access_token);
        })
        .catch((err) => {
          setError(err.message);
          setState('error');
        });
    } else {
      // Check for existing token
      const storedToken = sessionStorage.getItem('spotify_token');
      if (storedToken) {
        setAccessToken(storedToken);
        setState('connected');
      }
    }
  }, []);

  const handleConnectSpotify = async () => {
    try {
      const authUrl = await getSpotifyAuthUrl();
      window.location.href = authUrl;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to connect');
      setState('error');
    }
  };

  const handleRunSearch = async () => {
    if (!accessToken) return;

    setState('searching');
    setError(null);

    try {
      const response = await runLatentSearch(accessToken);
      setRecommendations(response.recommendations);
      setContextSummary(response.context_summary);
      setState('results');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Search failed');
      setState('error');
    }
  };

  const handleDisconnect = () => {
    sessionStorage.removeItem('spotify_token');
    setAccessToken(null);
    setRecommendations([]);
    setContextSummary(null);
    setState('disconnected');
  };

  const toggleExpanded = (artistId: string) => {
    setExpandedItems((prev) => {
      const next = new Set(prev);
      if (next.has(artistId)) {
        next.delete(artistId);
      } else {
        next.add(artistId);
      }
      return next;
    });
  };

  return (
    <div className="app">
      <header className="header">
        <h1>Latent Search</h1>
        <p className="tagline">Discover what algorithms exclude</p>
      </header>

      <main className="main">
        {/* Disconnected State */}
        {state === 'disconnected' && (
          <div className="action-section">
            <p className="description">
              Connect your Spotify account to analyze your listening history
              and surface artists that standard recommendation systems miss.
            </p>
            <button className="btn btn-primary" onClick={handleConnectSpotify}>
              Connect Spotify
            </button>
          </div>
        )}

        {/* Connected State */}
        {state === 'connected' && (
          <div className="action-section">
            <p className="status">Spotify connected</p>
            <button className="btn btn-primary" onClick={handleRunSearch}>
              Run Latent Search
            </button>
            <button className="btn btn-secondary" onClick={handleDisconnect}>
              Disconnect
            </button>
          </div>
        )}

        {/* Searching State */}
        {state === 'searching' && (
          <div className="action-section">
            <p className="status">Analyzing listening history...</p>
            <div className="loader"></div>
          </div>
        )}

        {/* Error State */}
        {state === 'error' && (
          <div className="action-section">
            <p className="error">{error}</p>
            <button className="btn btn-secondary" onClick={handleDisconnect}>
              Try Again
            </button>
          </div>
        )}

        {/* Results State */}
        {state === 'results' && (
          <div className="results-section">
            {contextSummary && (
              <div className="context-summary">
                <span>Analyzed {contextSummary.artists_analyzed} artists</span>
                <span className="separator">|</span>
                <span>{contextSummary.recurring_artists} recurring</span>
                <span className="separator">|</span>
                <span>{contextSummary.candidates_evaluated} candidates evaluated</span>
              </div>
            )}

            {recommendations.length === 0 ? (
              <p className="no-results">
                {contextSummary?.message || 'No recommendations found.'}
              </p>
            ) : (
              <ul className="recommendations">
                {recommendations.map((rec, index) => (
                  <li key={rec.artist_id} className="recommendation-item">
                    <div className="rec-main">
                      <span className="rec-number">{index + 1}</span>
                      <div className="rec-content">
                        <div className="rec-header">
                          <span className="rec-artist">{rec.artist_name}</span>
                          <span className="rec-score">
                            {(rec.omission_score * 100).toFixed(0)}
                          </span>
                        </div>
                        {rec.sample_track_name && (
                          <span className="rec-track">{rec.sample_track_name}</span>
                        )}
                        <div className="rec-genres">
                          {rec.genres.map((g) => (
                            <span key={g} className="genre-tag">{g}</span>
                          ))}
                        </div>
                      </div>
                      <button
                        className="toggle-btn"
                        onClick={() => toggleExpanded(rec.artist_id)}
                        aria-expanded={expandedItems.has(rec.artist_id)}
                      >
                        {expandedItems.has(rec.artist_id) ? '−' : '+'}
                      </button>
                    </div>

                    {expandedItems.has(rec.artist_id) && (
                      <div className="rec-details">
                        <p className="rec-explanation">{rec.explanation}</p>
                        {rec.found_via_artist && (
                          <p className="rec-source">
                            Found via: {rec.found_via_artist}
                          </p>
                        )}
                        <p className="rec-popularity">
                          Popularity: {rec.popularity}/100
                        </p>
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            )}

            <div className="results-actions">
              <button className="btn btn-secondary" onClick={handleRunSearch}>
                Search Again
              </button>
              <button className="btn btn-secondary" onClick={handleDisconnect}>
                Disconnect
              </button>
            </div>
          </div>
        )}
      </main>

      <footer className="footer">
        <p>Research MVP - Not a consumer product</p>
      </footer>
    </div>
  );
}

export default App;
