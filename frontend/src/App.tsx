import { useState, useEffect } from 'react';
import {
  getSpotifyAuthUrl,
  exchangeCodeForToken,
  runDiagnosis,
  runOmissionScan,
  submitFeedback,
  DiagnosisResponse,
  OmissionScanResponse,
  OmissionResult,
  ScanSettings,
  DEFAULT_SCAN_SETTINGS,
} from './api';
import './App.css';

type AppState =
  | 'disconnected'
  | 'connected'
  | 'diagnosing'
  | 'diagnosed'
  | 'scanning'
  | 'results'
  | 'error';

function App() {
  const [state, setState] = useState<AppState>('disconnected');
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [diagnosis, setDiagnosis] = useState<DiagnosisResponse | null>(null);
  const [scanResults, setScanResults] = useState<OmissionScanResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expandedItems, setExpandedItems] = useState<Set<string>>(new Set());
  const [showSettings, setShowSettings] = useState(false);
  const [settings, setSettings] = useState<ScanSettings>(DEFAULT_SCAN_SETTINGS);
  const [feedbackGiven, setFeedbackGiven] = useState<Map<string, 'accept' | 'reject'>>(new Map());

  // Check for OAuth callback on mount
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get('code');

    if (code) {
      window.history.replaceState({}, '', '/');

      exchangeCodeForToken(code)
        .then((data) => {
          setAccessToken(data.access_token);
          setState('connected');
          sessionStorage.setItem('spotify_token', data.access_token);
        })
        .catch((err) => {
          setError(err.message);
          setState('error');
        });
    } else {
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

  const handleRunDiagnosis = async () => {
    if (!accessToken) return;

    setState('diagnosing');
    setError(null);

    try {
      const response = await runDiagnosis(accessToken);
      setDiagnosis(response);
      setState('diagnosed');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Diagnosis failed');
      setState('error');
    }
  };

  const handleRunScan = async () => {
    if (!accessToken) return;

    setState('scanning');
    setError(null);

    try {
      const response = await runOmissionScan(accessToken, settings);
      setScanResults(response);
      setFeedbackGiven(new Map()); // Reset feedback for new results
      setState('results');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Scan failed');
      setState('error');
    }
  };

  const handleDisconnect = () => {
    sessionStorage.removeItem('spotify_token');
    setAccessToken(null);
    setDiagnosis(null);
    setScanResults(null);
    setFeedbackGiven(new Map());
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

  const handleFeedback = async (result: OmissionResult, verdict: 'accept' | 'reject') => {
    try {
      await submitFeedback({
        candidate_artist_id: result.artist_id,
        verdict,
        seed_artists: result.evidence.seed_artists,
        omission_score: result.omission_score,
      });
      setFeedbackGiven((prev) => new Map(prev).set(result.artist_id, verdict));
    } catch (err) {
      console.error('Feedback failed:', err);
    }
  };

  return (
    <div className="app">
      <header className="header">
        <h1>Latent Search</h1>
        <p className="tagline">Diagnostic instrument for music discovery through omission scoring</p>
      </header>

      <main className="main">
        {/* Disconnected State */}
        {state === 'disconnected' && (
          <div className="action-section">
            <div className="flow-indicator">
              <span className="flow-step active">1. Connect</span>
              <span className="flow-arrow">-</span>
              <span className="flow-step">2. Diagnose</span>
              <span className="flow-arrow">-</span>
              <span className="flow-step">3. Scan</span>
            </div>
            <p className="description">
              Connect your Spotify account to run a listening profile diagnosis
              and surface structurally omitted artists.
            </p>
            <button className="btn btn-primary" onClick={handleConnectSpotify}>
              Connect Spotify
            </button>
          </div>
        )}

        {/* Connected State - Ready to Diagnose */}
        {state === 'connected' && (
          <div className="action-section">
            <div className="flow-indicator">
              <span className="flow-step completed">1. Connect</span>
              <span className="flow-arrow">-</span>
              <span className="flow-step active">2. Diagnose</span>
              <span className="flow-arrow">-</span>
              <span className="flow-step">3. Scan</span>
            </div>
            <p className="status">Spotify connected</p>
            <p className="description">
              Run a diagnosis to analyze your listening patterns across
              short, medium, and long-term windows.
            </p>
            <button className="btn btn-primary" onClick={handleRunDiagnosis}>
              Run Latent Diagnosis
            </button>
            <button className="btn btn-tertiary" onClick={handleDisconnect}>
              Disconnect
            </button>
          </div>
        )}

        {/* Diagnosing State */}
        {state === 'diagnosing' && (
          <div className="action-section">
            <p className="status">Analyzing listening history...</p>
            <div className="loader"></div>
          </div>
        )}

        {/* Diagnosed State - Show Diagnosis + Ready to Scan */}
        {state === 'diagnosed' && diagnosis && (
          <div className="diagnosis-section">
            <div className="flow-indicator">
              <span className="flow-step completed">1. Connect</span>
              <span className="flow-arrow">-</span>
              <span className="flow-step completed">2. Diagnose</span>
              <span className="flow-arrow">-</span>
              <span className="flow-step active">3. Scan</span>
            </div>

            <div className="diagnosis-panel">
              <h2>Listening Profile Diagnosis</h2>

              <div className="diagnosis-stats">
                <span>{diagnosis.total_artists_analyzed} artists analyzed</span>
                <span className="separator">|</span>
                <span>{diagnosis.total_tracks_analyzed} tracks</span>
                <span className="separator">|</span>
                <span>{diagnosis.recurring_artists.length} recurring</span>
              </div>

              {/* Notes/Observations */}
              {diagnosis.notes.length > 0 && (
                <div className="diagnosis-notes">
                  {diagnosis.notes.map((note, i) => (
                    <p key={i} className="note">{note}</p>
                  ))}
                </div>
              )}

              {/* Top Genres */}
              <div className="diagnosis-block">
                <h3>Top Genres</h3>
                <div className="genre-list">
                  {diagnosis.top_genres.map((g) => (
                    <span key={g.genre} className="genre-item">
                      {g.genre}
                      <span className="genre-weight">{(g.weight * 100).toFixed(0)}%</span>
                    </span>
                  ))}
                </div>
              </div>

              {/* Recurring Artists */}
              <div className="diagnosis-block">
                <h3>Recurring Artists</h3>
                <div className="recurring-artists">
                  {diagnosis.recurring_artists.slice(0, 8).map((a) => (
                    <div key={a.id} className="recurring-artist">
                      <span className="artist-name">{a.name}</span>
                      <div className="time-windows">
                        {a.in_short_term && <span className="window short" title="Recent">S</span>}
                        {a.in_medium_term && <span className="window medium" title="Medium">M</span>}
                        {a.in_long_term && <span className="window long" title="Long">L</span>}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Audio Profile */}
              <div className="diagnosis-block">
                <h3>Audio Profile</h3>
                <div className="audio-profile">
                  <div className="audio-bar">
                    <span className="label">Energy</span>
                    <div className="bar-track">
                      <div className="bar-fill" style={{ width: `${diagnosis.audio_feature_profile.energy.center * 100}%` }} />
                    </div>
                    <span className="value">{(diagnosis.audio_feature_profile.energy.center * 100).toFixed(0)}</span>
                  </div>
                  <div className="audio-bar">
                    <span className="label">Danceability</span>
                    <div className="bar-track">
                      <div className="bar-fill" style={{ width: `${diagnosis.audio_feature_profile.danceability.center * 100}%` }} />
                    </div>
                    <span className="value">{(diagnosis.audio_feature_profile.danceability.center * 100).toFixed(0)}</span>
                  </div>
                  <div className="audio-bar">
                    <span className="label">Valence</span>
                    <div className="bar-track">
                      <div className="bar-fill" style={{ width: `${diagnosis.audio_feature_profile.valence.center * 100}%` }} />
                    </div>
                    <span className="value">{(diagnosis.audio_feature_profile.valence.center * 100).toFixed(0)}</span>
                  </div>
                  <div className="audio-bar">
                    <span className="label">Acousticness</span>
                    <div className="bar-track">
                      <div className="bar-fill" style={{ width: `${diagnosis.audio_feature_profile.acousticness.center * 100}%` }} />
                    </div>
                    <span className="value">{(diagnosis.audio_feature_profile.acousticness.center * 100).toFixed(0)}</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Scan Controls */}
            <div className="scan-controls">
              <button
                className="btn btn-tertiary"
                onClick={() => setShowSettings(!showSettings)}
              >
                {showSettings ? 'Hide Settings' : 'Scan Settings'}
              </button>

              {showSettings && (
                <div className="settings-panel">
                  <div className="setting-row">
                    <label>Popularity Range</label>
                    <div className="range-inputs">
                      <input
                        type="number"
                        min="0"
                        max="100"
                        value={settings.minPopularity}
                        onChange={(e) => setSettings({ ...settings, minPopularity: parseInt(e.target.value) || 0 })}
                      />
                      <span>to</span>
                      <input
                        type="number"
                        min="0"
                        max="100"
                        value={settings.maxPopularity}
                        onChange={(e) => setSettings({ ...settings, maxPopularity: parseInt(e.target.value) || 100 })}
                      />
                    </div>
                  </div>
                </div>
              )}

              <button className="btn btn-primary" onClick={handleRunScan}>
                Run Omission Scan
              </button>
              <button className="btn btn-tertiary" onClick={handleDisconnect}>
                Disconnect
              </button>
            </div>
          </div>
        )}

        {/* Scanning State */}
        {state === 'scanning' && (
          <div className="action-section">
            <p className="status">Running omission scan...</p>
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
        {state === 'results' && scanResults && (
          <div className="results-section">
            <div className="flow-indicator">
              <span className="flow-step completed">1. Connect</span>
              <span className="flow-arrow">-</span>
              <span className="flow-step completed">2. Diagnose</span>
              <span className="flow-arrow">-</span>
              <span className="flow-step completed">3. Scan</span>
            </div>

            <div className="scan-summary">
              <p className="summary-text">{scanResults.diagnosis_summary}</p>
              <p className="candidates-info">
                {scanResults.candidates_evaluated} candidates evaluated |
                Confidence threshold: {(scanResults.confidence_threshold_used * 100).toFixed(0)}%
              </p>
            </div>

            {scanResults.results.length === 0 ? (
              <div className="no-results">
                <p>No high-confidence omissions found.</p>
                <p className="hint">Try adjusting the popularity range or check back later.</p>
              </div>
            ) : (
              <ul className="omission-results">
                {scanResults.results.map((result, index) => (
                  <li key={result.artist_id} className="omission-item">
                    <div className="omission-main">
                      <span className="omission-number">{index + 1}</span>
                      <div className="omission-content">
                        <div className="omission-header">
                          <span className="omission-artist">{result.artist_name}</span>
                          <span className="omission-score">
                            {(result.omission_score * 100).toFixed(0)}
                          </span>
                        </div>
                        {result.sample_track_name && (
                          <span className="omission-track">{result.sample_track_name}</span>
                        )}
                        <div className="omission-genres">
                          {result.genres.map((g) => (
                            <span key={g} className="genre-tag">{g}</span>
                          ))}
                        </div>
                        <p className="omission-explanation">{result.explanation}</p>
                      </div>

                      <div className="feedback-buttons">
                        {feedbackGiven.get(result.artist_id) ? (
                          <span className={`feedback-given ${feedbackGiven.get(result.artist_id)}`}>
                            {feedbackGiven.get(result.artist_id) === 'accept' ? 'Accepted' : 'Rejected'}
                          </span>
                        ) : (
                          <>
                            <button
                              className="feedback-btn accept"
                              onClick={() => handleFeedback(result, 'accept')}
                              title="Makes sense"
                            >
                              Makes sense
                            </button>
                            <button
                              className="feedback-btn reject"
                              onClick={() => handleFeedback(result, 'reject')}
                              title="Not for me"
                            >
                              Not for me
                            </button>
                          </>
                        )}
                      </div>

                      <button
                        className="toggle-btn"
                        onClick={() => toggleExpanded(result.artist_id)}
                        aria-expanded={expandedItems.has(result.artist_id)}
                      >
                        {expandedItems.has(result.artist_id) ? '-' : '+'}
                      </button>
                    </div>

                    {expandedItems.has(result.artist_id) && (
                      <div className="omission-evidence">
                        <h4>Evidence</h4>
                        <ul className="evidence-list">
                          {result.evidence.seed_artists.length > 0 && (
                            <li>
                              <strong>Seed artists:</strong> {result.evidence.seed_artists.join(', ')}
                            </li>
                          )}
                          <li>
                            <strong>Genre overlap:</strong> {result.evidence.genre_overlap_count} genres
                          </li>
                          <li>
                            <strong>Audio similarity:</strong> {(result.evidence.audio_similarity_score * 100).toFixed(0)}%
                          </li>
                          <li>
                            <strong>Popularity:</strong> {result.evidence.popularity}/100
                          </li>
                          {result.evidence.earliest_album_year && (
                            <li>
                              <strong>Earliest album:</strong> {result.evidence.earliest_album_year}
                            </li>
                          )}
                        </ul>
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            )}

            <div className="results-actions">
              <button
                className="btn btn-tertiary"
                onClick={() => setShowSettings(!showSettings)}
              >
                {showSettings ? 'Hide Settings' : 'Adjust Settings'}
              </button>

              {showSettings && (
                <div className="settings-panel">
                  <div className="setting-row">
                    <label>Popularity Range</label>
                    <div className="range-inputs">
                      <input
                        type="number"
                        min="0"
                        max="100"
                        value={settings.minPopularity}
                        onChange={(e) => setSettings({ ...settings, minPopularity: parseInt(e.target.value) || 0 })}
                      />
                      <span>to</span>
                      <input
                        type="number"
                        min="0"
                        max="100"
                        value={settings.maxPopularity}
                        onChange={(e) => setSettings({ ...settings, maxPopularity: parseInt(e.target.value) || 100 })}
                      />
                    </div>
                  </div>
                </div>
              )}

              <button className="btn btn-secondary" onClick={handleRunScan}>
                Scan Again
              </button>
              <button className="btn btn-secondary" onClick={() => setState('diagnosed')}>
                Back to Diagnosis
              </button>
              <button className="btn btn-tertiary" onClick={handleDisconnect}>
                Disconnect
              </button>
            </div>
          </div>
        )}
      </main>

      <footer className="footer">
        <p>Diagnostic Instrument - Not a consumer product</p>
      </footer>
    </div>
  );
}

export default App;
