/**
 * Latent Search API Client
 *
 * Diagnostic instrument endpoints only.
 * Flow: Connect Spotify → Run Diagnosis → Run Omission Scan → Feedback
 */

const API_BASE = '/api';

// =========================================================================
// AUTH
// =========================================================================

export async function getSpotifyAuthUrl(): Promise<string> {
  const response = await fetch(`${API_BASE}/auth/spotify/url`);
  if (!response.ok) {
    throw new Error('Failed to get auth URL');
  }
  const data = await response.json();
  return data.auth_url;
}

export async function exchangeCodeForToken(code: string): Promise<{
  access_token: string;
  refresh_token: string;
  expires_in: number;
}> {
  const response = await fetch(`${API_BASE}/auth/spotify/callback?code=${encodeURIComponent(code)}`);
  if (!response.ok) {
    throw new Error('Failed to exchange code for token');
  }
  return response.json();
}

// =========================================================================
// DIAGNOSIS
// =========================================================================

export interface RecurringArtist {
  id: string;
  name: string;
  genres: string[];
  popularity: number;
  in_short_term: boolean;
  in_medium_term: boolean;
  in_long_term: boolean;
  recurrence_score: number;
}

export interface GenreWeight {
  genre: string;
  weight: number;
}

export interface AudioFeatureProfile {
  energy: { center: number };
  danceability: { center: number };
  valence: { center: number };
  tempo: { center: number };
  acousticness: { center: number };
  instrumentalness: { center: number };
}

export interface DiagnosisResponse {
  recurring_artists: RecurringArtist[];
  top_genres: GenreWeight[];
  audio_feature_profile: AudioFeatureProfile;
  notes: string[];
  total_artists_analyzed: number;
  total_tracks_analyzed: number;
}

export async function runDiagnosis(accessToken: string): Promise<DiagnosisResponse> {
  const params = new URLSearchParams({ access_token: accessToken });
  const response = await fetch(`${API_BASE}/diagnosis?${params}`);
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Diagnosis failed' }));
    throw new Error(error.detail || 'Diagnosis failed');
  }
  return response.json();
}

// =========================================================================
// OMISSION SCAN
// =========================================================================

export interface Evidence {
  seed_artists: string[];
  genre_overlap_count: number;
  audio_similarity_score: number;
  popularity: number;
  earliest_album_year: number | null;
}

export interface OmissionResult {
  artist_id: string;
  artist_name: string;
  sample_track_name: string | null;
  genres: string[];
  omission_score: number;
  explanation: string;
  evidence: Evidence;
}

export interface OmissionScanResponse {
  results: OmissionResult[];
  diagnosis_summary: string;
  candidates_evaluated: number;
  confidence_threshold_used: number;
}

export interface ScanSettings {
  minPopularity: number;
  maxPopularity: number;
}

export const DEFAULT_SCAN_SETTINGS: ScanSettings = {
  minPopularity: 5,
  maxPopularity: 60,
};

export async function runOmissionScan(
  accessToken: string,
  settings: ScanSettings = DEFAULT_SCAN_SETTINGS
): Promise<OmissionScanResponse> {
  const params = new URLSearchParams({
    access_token: accessToken,
    min_popularity: settings.minPopularity.toString(),
    max_popularity: settings.maxPopularity.toString(),
  });

  const response = await fetch(`${API_BASE}/scan?${params}`);
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Scan failed' }));
    throw new Error(error.detail || 'Scan failed');
  }
  return response.json();
}

// =========================================================================
// FEEDBACK
// =========================================================================

export interface FeedbackRequest {
  candidate_artist_id: string;
  verdict: 'accept' | 'reject';
  seed_artists?: string[];
  omission_score?: number;
}

export interface FeedbackResponse {
  success: boolean;
  message: string;
}

export async function submitFeedback(request: FeedbackRequest): Promise<FeedbackResponse> {
  const response = await fetch(`${API_BASE}/feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Feedback failed' }));
    throw new Error(error.detail || 'Feedback failed');
  }
  return response.json();
}

export interface FeedbackStats {
  total_feedback: number;
  accepts: number;
  rejects: number;
  unique_artists: number;
  accept_rate: number;
}

export async function getFeedbackStats(): Promise<FeedbackStats> {
  const response = await fetch(`${API_BASE}/feedback/stats`);
  if (!response.ok) {
    throw new Error('Failed to get feedback stats');
  }
  return response.json();
}
