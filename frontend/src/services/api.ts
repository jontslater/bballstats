/**
 * API Service
 * Handles all API calls to the backend
 */
import axios from 'axios';

const API_BASE_URL = (import.meta.env?.VITE_API_URL as string) || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 10000, // 10 second timeout for all requests
});

// Request interceptor for logging
api.interceptors.request.use(
  (config) => {
    console.log(`API Request: ${config.method?.toUpperCase()} ${config.url}`);
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor for error handling
api.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error('API Error:', error.response?.data || error.message);
    return Promise.reject(error);
  }
);

// Types
export interface Game {
  game_id: number;
  game_date: string;
  game_time?: string;
  game_status: string;
  home_team_id: number;
  home_team_name?: string;
  home_team_abbreviation?: string;
  away_team_id: number;
  away_team_name?: string;
  away_team_abbreviation?: string;
  home_score?: number;
  away_score?: number;
  prediction_count?: number;
  safe_bets_count?: number;
  long_shots_count?: number;
  // Alternative format from getUpcomingGames
  home_team?: {
    team_id: number;
    name: string;
    abbreviation: string;
  };
  away_team?: {
    team_id: number;
    name: string;
    abbreviation: string;
  };
}

export interface Prediction {
  prediction_id: number;
  player_id: number;
  player_name: string;
  player_team?: string;
  game_id: number;
  game_time?: string;
  stat_type: string;
  distribution_mean: number;
  distribution_std_dev: number;
  safe_line: number;
  safe_probability: number;
  standard_line: number;
  standard_probability: number;
  long_shot_line: number;
  long_shot_probability: number;
  bet_type: string;
  confidence_level: string;
  volatility_level: string;
  reasoning?: string;
  percentile_25?: number;
  percentile_50?: number;
  percentile_85?: number;
}

export interface Play {
  play_id: number;
  player_id: number;
  player_name?: string;
  game_id: number;
  game_date?: string;
  stat_type: string;
  bet_line: string;
  predicted_min?: number;
  predicted_max?: number;
  likelihood_score?: number;
  notes?: string;
  status: string;
  actual_result?: number;
}

// API Functions
export const apiService = {
  // Health check
  healthCheck: async () => {
    const response = await api.get('/health');
    return response.data;
  },

  // Games
  getGames: async (gameDate?: string, status?: string) => {
    const params: any = {};
    if (gameDate) params.game_date = gameDate;
    if (status) params.status = status;
    const response = await api.get('/api/games', { params });
    return response.data;
  },

  getGame: async (gameId: number) => {
    const response = await api.get(`/api/games/${gameId}`);
    return response.data;
  },

  getUpcomingGames: async (daysAhead: number = 7) => {
    const response = await api.get('/api/games/upcoming/list', {
      params: { days_ahead: daysAhead },
    });
    return response.data;
  },

  // Predictions
  getPredictionsForGame: async (gameId: number, statType?: string, betType?: string) => {
    const params: any = {};
    if (statType) params.stat_type = statType;
    if (betType) params.bet_type = betType;
    const response = await api.get(`/api/predictions/game/${gameId}`, { params });
    return response.data;
  },

  getSafeBets: async (gameDate?: string, limit: number = 50) => {
    const params: any = { limit };
    if (gameDate) params.game_date = gameDate;
    const response = await api.get('/api/predictions/safe-bets', { params });
    return response.data;
  },

  getLongShots: async (gameDate?: string, limit: number = 50) => {
    const params: any = { limit };
    if (gameDate) params.game_date = gameDate;
    const response = await api.get('/api/predictions/long-shots', { params });
    return response.data;
  },

  getUpcomingPredictions: async (daysAhead: number = 1, statType?: string, betType?: string) => {
    const params: any = { days_ahead: daysAhead };
    if (statType) params.stat_type = statType;
    if (betType) params.bet_type = betType;
    const response = await api.get('/api/predictions/upcoming', { params });
    return response.data;
  },

  collectGameResults: async () => {
    const response = await api.post('/api/game-results/collect-previous-day', {}, {
      timeout: 60000, // 60 seconds for this slow operation (scrapes multiple games)
    });
    return response.data;
  },

  generatePredictions: async (
    gameId?: number, 
    daysAhead: number = 1, 
    statTypes: string[] = ['points', 'rebounds', 'assists'],
    onProgress?: (progress: any) => void
  ) => {
    const response = await fetch(`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/api/predictions/generate`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        game_id: gameId,
        days_ahead: daysAhead,
        stat_types: statTypes,
      }),
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const reader = response.body?.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let finalResult: any = null;

    if (reader) {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              if (data.complete) {
                finalResult = data.results || data;
              } else if (onProgress) {
                onProgress(data);
              }
            } catch (e) {
              console.error('Error parsing SSE data:', e);
            }
          }
        }
      }
    }

    return finalResult || { success: true };
  },

  // Players
  getPlayers: async (teamId?: number, position?: string, limit: number = 100) => {
    const params: any = { limit };
    if (teamId) params.team_id = teamId;
    if (position) params.position = position;
    const response = await api.get('/api/players', { params });
    return response.data;
  },

  getPlayer: async (playerId: number) => {
    const response = await api.get(`/api/players/${playerId}`);
    return response.data;
  },

  getPlayerStats: async (playerId: number, seasonId?: number, limit: number = 50) => {
    const params: any = { limit };
    if (seasonId) params.season_id = seasonId;
    const response = await api.get(`/api/players/${playerId}/stats`, { params });
    return response.data;
  },

  // Plays
  getPlays: async (status?: string, limit: number = 100) => {
    const params: any = { limit };
    if (status) params.status = status;
    const response = await api.get('/api/plays', { params });
    return response.data;
  },

  createPlay: async (play: {
    player_id: number;
    game_id: number;
    stat_type: string;
    bet_line: string;
    notes?: string;
  }) => {
    const response = await api.post('/api/plays', play);
    return response.data;
  },

  updatePlay: async (playId: number, updates: {
    status?: string;
    actual_result?: number;
    notes?: string;
  }) => {
    const response = await api.put(`/api/plays/${playId}`, updates);
    return response.data;
  },

  deletePlay: async (playId: number) => {
    const response = await api.delete(`/api/plays/${playId}`);
    return response.data;
  },

  getPlay: async (playId: number) => {
    const response = await api.get(`/api/plays/${playId}`);
    return response.data;
  },

  getPlayStats: async () => {
    const response = await api.get('/api/plays/stats/summary');
    return response.data;
  },

  // Parlays
  createParlay: async (parlay: {
    play_ids: number[];
    name?: string;
    notes?: string;
  }) => {
    const response = await api.post('/api/parlays', parlay);
    return response.data;
  },

  parseTextToBets: async (request: {
    text: string;
    game_date?: string;
  }) => {
    const response = await api.post('/api/parlays/parse-text', request);
    return response.data;
  },

  createParlayFromText: async (request: {
    text: string;
    game_date?: string;
    name?: string;
    notes?: string;
  }) => {
    const response = await api.post('/api/parlays/from-text', request);
    return response.data;
  },

  generateAlternativeParlay: async (parlayId: number) => {
    const response = await api.post(`/api/parlays/${parlayId}/alternative`);
    return response.data;
  },

  deleteParlay: async (parlayId: number) => {
    const response = await api.delete(`/api/parlays/${parlayId}`);
    return response.data;
  },

  getParlays: async (status?: string) => {
    const params: any = {};
    if (status) params.status = status;
    const response = await api.get('/api/parlays', { params });
    return response.data;
  },

  getParlay: async (parlayId: number) => {
    const response = await api.get(`/api/parlays/${parlayId}`);
    return response.data;
  },

  // Analytics
  getTeamDefense: async (teamId: number, position?: string, seasonId?: number) => {
    const params: any = {};
    if (position) params.position = position;
    if (seasonId) params.season_id = seasonId;
    const response = await api.get(`/api/analytics/team-defense/${teamId}`, { params });
    return response.data;
  },

  getMatchup: async (playerId: number, teamId: number, seasonId?: number) => {
    const params: any = {};
    if (seasonId) params.season_id = seasonId;
    const response = await api.get(`/api/analytics/matchup/${playerId}/${teamId}`, { params });
    return response.data;
  },

  getInjuries: async (teamId?: number) => {
    const params: any = {};
    if (teamId) params.team_id = teamId;
    const response = await api.get('/api/analytics/injuries', { params });
    return response.data;
  },

  getGameLineups: async (gameId: number) => {
    const response = await api.get(`/api/lineups/game/${gameId}`);
    return response.data;
  },

  // Suggested Bets
  getSuggestedBets: async (gameDate?: string, limit: number = 10) => {
    const params: any = { limit };
    if (gameDate) params.game_date = gameDate;
    const response = await api.get('/api/suggested-bets/bets', { params });
    return response.data;
  },

  getSuggestedParlays: async (gameDate?: string, limit: number = 5, mixStats: boolean = true) => {
    const params: any = { limit, mix_stats: mixStats };
    if (gameDate) params.game_date = gameDate;
    const response = await api.get('/api/suggested-bets/parlays', { params });
    return response.data;
  },

  getSafeLongParlays: async (gameDate?: string, limit: number = 3, numLegs: number = 12, minLegProbability: number = 0.75) => {
    const params: any = { limit, num_legs: numLegs, min_leg_probability: minLegProbability };
    if (gameDate) params.game_date = gameDate;
    const response = await api.get('/api/suggested-bets/safe-long-parlays', { params });
    return response.data;
  },

  getSameGameParlays: async (gameId: number, limit: number = 5, numLegs: number = 3, minLegProbability: number = 0.70) => {
    const params: any = { limit, num_legs: numLegs, min_leg_probability: minLegProbability };
    const response = await api.get(`/api/suggested-bets/same-game-parlays/${gameId}`, { params });
    return response.data;
  },

  getBuilderPlays: async (gameDate?: string, limit: number = 5, numLegs: number = 2) => {
    const params: any = { limit, num_legs: numLegs };
    if (gameDate) params.game_date = gameDate;
    const response = await api.get('/api/suggested-bets/builder-plays', { params });
    return response.data;
  },

  refreshSafeLongParlay: async (gameDate?: string, numLegs: number = 12, minLegProbability: number = 0.75, excludePlayerIds: number[] = []) => {
    const response = await api.post('/api/suggested-bets/refresh-safe-long-parlay', {
      game_date: gameDate,
      num_legs: numLegs,
      min_leg_probability: minLegProbability,
      exclude_player_ids: excludePlayerIds
    });
    return response.data;
  },

  refreshBuilderPlay: async (gameDate?: string, numLegs: number = 2, excludePlayerIds: number[] = []) => {
    const response = await api.post('/api/suggested-bets/refresh-builder-play', {
      game_date: gameDate,
      num_legs: numLegs,
      exclude_player_ids: excludePlayerIds
    });
    return response.data;
  },

  // Advanced Bets
  getAdvancedBetsForGame: async (gameId: number, limitPerType: number = 5) => {
    const response = await api.get(`/api/advanced-bets/game/${gameId}`, { params: { limit_per_type: limitPerType } });
    return response.data;
  },

  getComboProps: async (gameId: number, playerId: number, comboType: string = 'points_rebounds') => {
    const response = await api.get(`/api/advanced-bets/combo-props/${gameId}/${playerId}`, { params: { combo_type: comboType } });
    return response.data;
  },

  getMilestoneProps: async (gameId: number, playerId: number) => {
    const response = await api.get(`/api/advanced-bets/milestone-props/${gameId}/${playerId}`);
    return response.data;
  },

  getPlayerVsPlayer: async (gameId: number, player1Id: number, player2Id: number, statType: string = 'points') => {
    const response = await api.get(`/api/advanced-bets/player-vs-player/${gameId}/${player1Id}/${player2Id}`, { params: { stat_type: statType } });
    return response.data;
  },

  getAlternateLines: async (gameId: number, playerId: number, statType: string) => {
    const response = await api.get(`/api/advanced-bets/alternate-lines/${gameId}/${playerId}/${statType}`);
    return response.data;
  },

  getPerformanceBrackets: async (gameId: number, playerId: number, statType: string) => {
    const response = await api.get(`/api/advanced-bets/performance-brackets/${gameId}/${playerId}/${statType}`);
    return response.data;
  },

  getTeamTotals: async (gameId: number, teamId: number, statType: string = 'points') => {
    const response = await api.get(`/api/advanced-bets/team-totals/${gameId}/${teamId}`, { params: { stat_type: statType } });
    return response.data;
  },

  getAdvancedBetsForDate: async (gameDate: string, limitPerType: number = 10) => {
    const response = await api.get(`/api/advanced-bets/date/${gameDate}`, { params: { limit_per_type: limitPerType } });
    return response.data;
  },

  // Historical Results
  getPredictionResults: async (startDate?: string, endDate?: string, betType?: string, statType?: string, limit: number = 100) => {
    const params: any = { limit };
    if (startDate) params.start_date = startDate;
    if (endDate) params.end_date = endDate;
    if (betType) params.bet_type = betType;
    if (statType) params.stat_type = statType;
    const response = await api.get('/api/historical-results/predictions', { 
      params,
      timeout: 60000, // 60 seconds for large historical queries
    });
    return response.data;
  },

  getAccuracyStats: async (startDate?: string, endDate?: string, betType?: string) => {
    const params: any = {};
    if (startDate) params.start_date = startDate;
    if (endDate) params.end_date = endDate;
    if (betType) params.bet_type = betType;
    const response = await api.get('/api/historical-results/accuracy', { 
      params,
      timeout: 60000, // 60 seconds for large historical queries
    });
    return response.data;
  },

  evaluateGame: async (gameId: number) => {
    const response = await api.post(`/api/historical-results/evaluate/${gameId}`);
    return response.data;
  },

  evaluateDate: async (targetDate: string) => {
    const response = await api.post(`/api/historical-results/evaluate/date/${targetDate}`, {}, {
      timeout: 120000, // 2 minutes for single date evaluation
    });
    return response.data;
  },

  evaluateAllFinishedGames: async (
    daysBack: number = 30,
    onProgress?: (progress: any) => void
  ) => {
    const response = await fetch(`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/api/historical-results/evaluate/all?days_back=${daysBack}&collect_stats=true`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      // No timeout - let it run as long as needed for 90 days of data
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const reader = response.body?.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let finalResult: any = null;

    if (reader) {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              if (data.complete) {
                finalResult = data;
              } else if (onProgress) {
                onProgress(data);
              }
            } catch (e) {
              console.error('Error parsing SSE data:', e);
            }
          }
        }
      }
    }

    return finalResult || { success: true };
  },

  getEvaluationStatus: async () => {
    const response = await api.get('/api/historical-results/evaluation-status', {
      timeout: 30000, // 30 seconds for status check
    });
    return response.data;
  },

  // Parlay Results
  getParlayResults: async (startDate?: string, endDate?: string, status?: string) => {
    const params: any = {};
    if (startDate) params.start_date = startDate;
    if (endDate) params.end_date = endDate;
    if (status) params.status = status;
    const response = await api.get('/api/historical-results/parlay-results', { params });
    return response.data;
  },

  evaluateParlays: async (gameId?: number, allFinished?: boolean) => {
    const params: any = {};
    if (gameId) params.game_id = gameId;
    if (allFinished) params.all_finished = allFinished;
    const response = await api.post('/api/historical-results/evaluate-parlays', null, { params });
    return response.data;
  },

  collectBoxScores: async (daysBack: number = 7) => {
    const response = await api.post(`/api/game-results/collect-for-finished-games?days_back=${daysBack}`, {}, {
      timeout: 300000, // 5 minutes for box score collection (can take a while)
    });
    return response.data;
  },

  // Updates
  runFullUpdate: async (onProgress?: (progress: any) => void) => {
    const response = await fetch(`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/api/updates/run-full-update`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const reader = response.body?.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let finalResult: any = null;

    if (reader) {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              if (data.complete) {
                finalResult = data;
              } else if (onProgress) {
                onProgress(data);
              }
            } catch (e) {
              console.error('Error parsing SSE data:', e);
            }
          }
        }
      }
    }

    return finalResult || { success: true };
  },

  runQuickUpdate: async (onProgress?: (progress: any) => void) => {
    const response = await fetch(`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/api/updates/run-quick-update`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const reader = response.body?.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let finalResult: any = null;

    if (reader) {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              if (data.complete) {
                finalResult = data;
              } else if (onProgress) {
                onProgress(data);
              }
            } catch (e) {
              console.error('Error parsing SSE data:', e);
            }
          }
        }
      }
    }

    return finalResult || { success: true };
  },

  getUpdateStatus: async () => {
    const response = await api.get('/api/updates/status');
    return response.data;
  },

  // Analyze
  searchPlayers: async (query: string, limit: number = 20) => {
    const response = await api.get('/api/analyze/search-players', {
      params: { query, limit }
    });
    return response.data;
  },

  getPlayerGames: async (playerId: number, gameDate?: string) => {
    const params: any = {};
    if (gameDate) params.game_date = gameDate;
    const response = await api.get(`/api/analyze/player-games`, {
      params: { player_id: playerId, ...params }
    });
    return response.data;
  },

  analyzeBet: async (bet: {
    player_id: number;
    game_id: number;
    stat_type: string;
    bet_line: number;
    bet_type: string;
  }) => {
    const response = await api.post('/api/analyze/bet', bet);
    return response.data;
  },

  analyzeParlay: async (parlay: {
    legs: Array<{
      player_id: number;
      game_id: number;
      stat_type: string;
      bet_line: number;
      bet_type: string;
    }>;
  }) => {
    const response = await api.post('/api/analyze/parlay', parlay);
    return response.data;
  },

  // Poor Man's Bet
  getPoorMansBetChallenges: async () => {
    const response = await api.get('/api/poor-mans-bet/challenges');
    return response.data;
  },

  getPoorMansBetChallenge: async (challengeId: number) => {
    const response = await api.get(`/api/poor-mans-bet/challenges/${challengeId}`);
    return response.data;
  },

  createPoorMansBetChallenge: async (data: {
    name?: string;
    start_amount: number;
    days_target: number;
    target_amount?: number;
  }) => {
    const response = await api.post('/api/poor-mans-bet/challenges', data);
    return response.data;
  },

  getPoorMansBetSuggestion: async (challengeId: number, gameDate?: string) => {
    const params: any = {};
    if (gameDate) params.game_date = gameDate;
    const response = await api.post(`/api/poor-mans-bet/challenges/${challengeId}/suggest-bet`, null, { params });
    return response.data;
  },

  placePoorMansBet: async (data: {
    challenge_id: number;
    prediction_ids: number[];
    bet_amount: number;
    game_date: string;
    notes?: string;
  }) => {
    const response = await api.post(`/api/poor-mans-bet/challenges/${data.challenge_id}/place-bet`, data);
    return response.data;
  },

  resolvePoorMansBet: async (
    challengeId: number,
    dayId: number,
    data: {
      status: 'hit' | 'miss' | 'void';
      actual_return?: number;
    }
  ) => {
    const response = await api.put(`/api/poor-mans-bet/challenges/${challengeId}/resolve-bet/${dayId}`, data);
    return response.data;
  },

  deletePoorMansBetChallenge: async (challengeId: number) => {
    const response = await api.delete(`/api/poor-mans-bet/challenges/${challengeId}`);
    return response.data;
  },

  // Bankroll Recommendations
  getBankrollRecommendations: async (data: {
    total_bankroll: number;
    reserve_amount: number;
    game_date?: string;
    risk_tolerance: 'conservative' | 'moderate' | 'aggressive';
  }) => {
    const response = await api.post('/api/bankroll-recommendations', data);
    return response.data;
  },
};

export default apiService;

