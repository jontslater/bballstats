import { useState, useEffect } from 'react';
import { format } from 'date-fns';
import apiService from '../services/api';
import { parseDateString } from '../utils/dateUtils';

interface Player {
  player_id: number;
  name: string;
  team?: number;
  position?: string;
}

interface Game {
  game_id: number;
  game_date: string;
  opponent: string;
  home_away: string;
}

interface AnalysisResult {
  player_name: string;
  game_id: number;
  stat_type: string;
  bet_line: string;
  probability: number;
  mean: number;
  std_dev: number;
  confidence_level: string;
  volatility_level: string;
  reasoning?: string;
  alternatives: Array<{
    bet_line: string;
    probability: number;
    reason: string;
  }>;
  suggested_lines: {
    safe?: number;
    standard?: number;
    long_shot?: number;
  };
}

interface ParlayLeg {
  player_id: number;
  player_name: string;
  game_id: number;
  stat_type: string;
  bet_type: 'Over' | 'Under';
  bet_line: number;
}

interface ParlayAnalysisResult {
  legs: Array<{
    player_name: string;
    bet_line: string;
    probability: number;
    mean: number;
    std_dev: number;
  }>;
  combined_probability: number;
  combined_odds: string;
  overall_assessment: string;
}

export default function Analyze() {
  const [mode, setMode] = useState<'single' | 'parlay'>('single');
  const [searchQuery, setSearchQuery] = useState('');
  const [players, setPlayers] = useState<Player[]>([]);
  const [selectedPlayer, setSelectedPlayer] = useState<Player | null>(null);
  const [games, setGames] = useState<Game[]>([]);
  const [selectedGame, setSelectedGame] = useState<Game | null>(null);
  const [statType, setStatType] = useState<string>('points');
  const [betType, setBetType] = useState<'Over' | 'Under'>('Over');
  const [betLine, setBetLine] = useState<string>('');
  const [analysis, setAnalysis] = useState<AnalysisResult | null>(null);
  
  // Parlay mode state
  const [parlayLegs, setParlayLegs] = useState<ParlayLeg[]>([]);
  const [parlayAnalysis, setParlayAnalysis] = useState<ParlayAnalysisResult | null>(null);
  
  const [loading, setLoading] = useState(false);
  const [searching, setSearching] = useState(false);

  useEffect(() => {
    if (searchQuery.length >= 2) {
      const timeoutId = setTimeout(() => {
        searchPlayers();
      }, 300);
      return () => clearTimeout(timeoutId);
    } else {
      setPlayers([]);
    }
  }, [searchQuery]);

  useEffect(() => {
    if (selectedPlayer) {
      loadPlayerGames();
    }
  }, [selectedPlayer]);

  const searchPlayers = async () => {
    setSearching(true);
    try {
      const data = await apiService.searchPlayers(searchQuery, 20);
      setPlayers(data);
    } catch (error) {
      console.error('Error searching players:', error);
    } finally {
      setSearching(false);
    }
  };

  const loadPlayerGames = async () => {
    if (!selectedPlayer) return;
    try {
      const data = await apiService.getPlayerGames(selectedPlayer.player_id);
      setGames(data);
      if (data.length > 0) {
        setSelectedGame(data[0]);
      }
    } catch (error) {
      console.error('Error loading games:', error);
    }
  };

  const handleAnalyze = async () => {
    if (!selectedPlayer || !selectedGame || !betLine) {
      alert('Please select a player, game, and enter a bet line');
      return;
    }

    const lineValue = parseFloat(betLine);
    if (isNaN(lineValue)) {
      alert('Please enter a valid number for the bet line');
      return;
    }

    setLoading(true);
    try {
      const data = await apiService.analyzeBet({
        player_id: selectedPlayer.player_id,
        game_id: selectedGame.game_id,
        stat_type: statType,
        bet_line: lineValue,
        bet_type: betType,
      });
      setAnalysis(data);
    } catch (error: any) {
      console.error('Error analyzing bet:', error);
      alert(error.response?.data?.detail || error.message || 'Failed to analyze bet. Make sure predictions have been generated for this player/game.');
    } finally {
      setLoading(false);
    }
  };

  const getProbabilityColor = (probability: number) => {
    if (probability >= 0.70) return 'text-green-600';
    if (probability >= 0.50) return 'text-blue-600';
    if (probability >= 0.30) return 'text-yellow-600';
    return 'text-orange-600';
  };

  const getProbabilityLabel = (probability: number) => {
    if (probability >= 0.70) return 'High';
    if (probability >= 0.50) return 'Moderate';
    if (probability >= 0.30) return 'Low-Moderate';
    return 'Low';
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-gray-900">Analyze Bet</h1>
        <p className="mt-1 text-sm text-gray-500">
          Analyze single bets or build and analyze parlays
        </p>
      </div>

      {/* Mode Toggle */}
      <div className="flex gap-2">
        <button
          onClick={() => {
            setMode('single');
            setAnalysis(null);
            setParlayAnalysis(null);
          }}
          className={`px-4 py-2 rounded-md ${
            mode === 'single'
              ? 'bg-primary-600 text-white'
              : 'bg-white text-gray-700 hover:bg-gray-100'
          }`}
        >
          Single Bet
        </button>
        <button
          onClick={() => {
            setMode('parlay');
            setAnalysis(null);
            setParlayAnalysis(null);
          }}
          className={`px-4 py-2 rounded-md ${
            mode === 'parlay'
              ? 'bg-primary-600 text-white'
              : 'bg-white text-gray-700 hover:bg-gray-100'
          }`}
        >
          Parlay
        </button>
      </div>

      {/* Search and Selection */}
      <div className="bg-white rounded-lg shadow p-6 space-y-4">
        {/* Player Search */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Search Player
          </label>
          <div className="relative">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Type player name..."
              className="w-full px-4 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
            {searching && (
              <div className="absolute right-3 top-2.5 text-gray-400">Searching...</div>
            )}
          </div>
          {players.length > 0 && (
            <div className="mt-2 border border-gray-200 rounded-md max-h-60 overflow-y-auto">
              {players.map((player) => (
                <button
                  key={player.player_id}
                  onClick={() => {
                    setSelectedPlayer(player);
                    setSearchQuery(player.name);
                    setPlayers([]);
                  }}
                  className="w-full text-left px-4 py-2 hover:bg-gray-100 border-b border-gray-100 last:border-b-0"
                >
                  <div className="font-medium text-gray-900">{player.name}</div>
                  {player.position && (
                    <div className="text-sm text-gray-500">{player.position}</div>
                  )}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Selected Player Info */}
        {selectedPlayer && (
          <div className="bg-blue-50 rounded-lg p-4">
            <div className="font-semibold text-gray-900">Selected: {selectedPlayer.name}</div>
            {selectedPlayer.position && (
              <div className="text-sm text-gray-600">{selectedPlayer.position}</div>
            )}
          </div>
        )}

        {/* Game Selection */}
        {selectedPlayer && games.length > 0 && (
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Select Game
            </label>
            <select
              value={selectedGame?.game_id || ''}
              onChange={(e) => {
                const game = games.find(g => g.game_id === Number(e.target.value));
                setSelectedGame(game || null);
              }}
              className="w-full px-4 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
            >
              {games.map((game) => (
                <option key={game.game_id} value={game.game_id}>
                  {format(parseDateString(game.game_date), 'MMM d, yyyy')} - {game.home_away} vs {game.opponent}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Stat Type */}
        {selectedGame && (
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Stat Type
            </label>
            <div className="flex gap-2">
              {['points', 'rebounds', 'assists'].map((stat) => (
                <button
                  key={stat}
                  onClick={() => setStatType(stat)}
                  className={`flex-1 px-4 py-2 rounded-md capitalize ${
                    statType === stat
                      ? 'bg-primary-600 text-white'
                      : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                  }`}
                >
                  {stat === 'points' ? 'Points' : stat === 'rebounds' ? 'Rebounds' : 'Assists'}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Single Bet Mode */}
        {mode === 'single' && selectedGame && (
          <>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Bet Type
              </label>
              <div className="flex gap-2">
                <button
                  onClick={() => setBetType('Over')}
                  className={`flex-1 px-4 py-2 rounded-md ${
                    betType === 'Over'
                      ? 'bg-green-600 text-white'
                      : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                  }`}
                >
                  Over
                </button>
                <button
                  onClick={() => setBetType('Under')}
                  className={`flex-1 px-4 py-2 rounded-md ${
                    betType === 'Under'
                      ? 'bg-red-600 text-white'
                      : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                  }`}
                >
                  Under
                </button>
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Bet Line
              </label>
              <input
                type="number"
                step="0.5"
                value={betLine}
                onChange={(e) => setBetLine(e.target.value)}
                placeholder="e.g., 6.0"
                className="w-full px-4 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
              />
            </div>

            <button
              onClick={handleAnalyze}
              disabled={loading || !betLine}
              className="w-full px-4 py-2 bg-primary-600 text-white rounded-md hover:bg-primary-700 disabled:bg-gray-300 disabled:cursor-not-allowed"
            >
              {loading ? 'Analyzing...' : 'Analyze Bet'}
            </button>
          </>
        )}

        {/* Parlay Mode - Add Leg */}
        {mode === 'parlay' && selectedGame && (
          <>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Bet Type
              </label>
              <div className="flex gap-2">
                <button
                  onClick={() => setBetType('Over')}
                  className={`flex-1 px-4 py-2 rounded-md ${
                    betType === 'Over'
                      ? 'bg-green-600 text-white'
                      : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                  }`}
                >
                  Over
                </button>
                <button
                  onClick={() => setBetType('Under')}
                  className={`flex-1 px-4 py-2 rounded-md ${
                    betType === 'Under'
                      ? 'bg-red-600 text-white'
                      : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                  }`}
                >
                  Under
                </button>
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Bet Line
              </label>
              <input
                type="number"
                step="0.5"
                value={betLine}
                onChange={(e) => setBetLine(e.target.value)}
                placeholder="e.g., 6.0"
                className="w-full px-4 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
              />
            </div>

            <button
              onClick={() => {
                if (!selectedPlayer || !selectedGame || !betLine) {
                  alert('Please fill in all fields');
                  return;
                }
                const lineValue = parseFloat(betLine);
                if (isNaN(lineValue)) {
                  alert('Please enter a valid number');
                  return;
                }
                const newLeg: ParlayLeg = {
                  player_id: selectedPlayer.player_id,
                  player_name: selectedPlayer.name,
                  game_id: selectedGame.game_id,
                  stat_type: statType,
                  bet_type: betType,
                  bet_line: lineValue,
                };
                setParlayLegs([...parlayLegs, newLeg]);
                setBetLine('');
                setSearchQuery('');
                setSelectedPlayer(null);
                setSelectedGame(null);
              }}
              className="w-full px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700"
            >
              Add to Parlay
            </button>
          </>
        )}
      </div>

      {/* Parlay Legs List */}
      {mode === 'parlay' && parlayLegs.length > 0 && (
        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-xl font-bold text-gray-900">Parlay Legs ({parlayLegs.length})</h2>
            <button
              onClick={async () => {
                if (parlayLegs.length < 2) {
                  alert('Parlay must have at least 2 legs');
                  return;
                }
                setLoading(true);
                try {
                  const data = await apiService.analyzeParlay({
                    legs: parlayLegs.map(leg => ({
                      player_id: leg.player_id,
                      game_id: leg.game_id,
                      stat_type: leg.stat_type,
                      bet_line: leg.bet_line,
                      bet_type: leg.bet_type,
                    }))
                  });
                  setParlayAnalysis(data);
                } catch (error: any) {
                  console.error('Error analyzing parlay:', error);
                  alert(error.response?.data?.detail || error.message || 'Failed to analyze parlay. Make sure predictions have been generated for all players/games.');
                } finally {
                  setLoading(false);
                }
              }}
              disabled={loading || parlayLegs.length < 2}
              className="px-4 py-2 bg-primary-600 text-white rounded-md hover:bg-primary-700 disabled:bg-gray-300 disabled:cursor-not-allowed"
            >
              {loading ? 'Analyzing...' : 'Analyze Parlay'}
            </button>
          </div>
          <div className="space-y-2">
            {parlayLegs.map((leg, idx) => (
              <div key={idx} className="bg-gray-50 rounded-lg p-4 border border-gray-200 flex justify-between items-center">
                <div>
                  <div className="font-semibold text-gray-900">{leg.player_name}</div>
                  <div className="text-sm text-gray-600">
                    {leg.stat_type === 'points' ? 'PTS' : leg.stat_type === 'rebounds' ? 'REB' : 'AST'} • {leg.bet_type} {leg.bet_line}
                  </div>
                </div>
                <button
                  onClick={() => setParlayLegs(parlayLegs.filter((_, i) => i !== idx))}
                  className="text-red-500 hover:text-red-700 text-xl font-bold"
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Single Bet Analysis Results */}
      {mode === 'single' && analysis && (
        <div className="bg-white rounded-lg shadow p-6 space-y-6">
          <h2 className="text-2xl font-bold text-gray-900">Analysis Results</h2>

          {/* Main Assessment */}
          <div className="bg-gradient-to-r from-blue-50 to-purple-50 rounded-lg p-6 border-2 border-blue-200">
            <div className="flex justify-between items-start mb-4">
              <div>
                <div className="text-sm text-gray-600 mb-1">Bet Line</div>
                <div className="text-2xl font-bold text-gray-900">{analysis.bet_line}</div>
              </div>
              <div className="text-right">
                <div className="text-sm text-gray-600 mb-1">Likelihood</div>
                <div className={`text-3xl font-bold ${getProbabilityColor(analysis.probability)}`}>
                  {(analysis.probability * 100).toFixed(1)}%
                </div>
                <div className="text-sm text-gray-500 mt-1">
                  {getProbabilityLabel(analysis.probability)} Probability
                </div>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4 mt-4">
              <div>
                <div className="text-sm text-gray-600">Expected Mean</div>
                <div className="text-lg font-semibold text-gray-900">
                  {analysis.mean.toFixed(1)} ± {analysis.std_dev.toFixed(1)}
                </div>
              </div>
              <div>
                <div className="text-sm text-gray-600">Confidence</div>
                <div className="text-lg font-semibold text-gray-900 capitalize">
                  {analysis.confidence_level} • {analysis.volatility_level}
                </div>
              </div>
            </div>

            {analysis.reasoning && (
              <div className="mt-4 pt-4 border-t border-blue-200">
                <div className="text-sm text-gray-600 mb-1">Analysis</div>
                <div className="text-sm text-gray-700">{analysis.reasoning}</div>
              </div>
            )}
          </div>

          {/* Alternative Plays */}
          {analysis.alternatives.length > 0 && (
            <div>
              <h3 className="text-xl font-semibold text-gray-900 mb-4">Alternative Plays</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {analysis.alternatives.map((alt, idx) => (
                  <div key={idx} className="bg-gray-50 rounded-lg p-4 border border-gray-200">
                    <div className="flex justify-between items-start mb-2">
                      <div>
                        <div className="font-semibold text-gray-900">{alt.bet_line}</div>
                        <div className="text-xs text-gray-500 mt-1">{alt.reason}</div>
                      </div>
                      <div className={`text-lg font-bold ${getProbabilityColor(alt.probability)}`}>
                        {(alt.probability * 100).toFixed(1)}%
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Suggested Lines */}
          <div>
            <h3 className="text-xl font-semibold text-gray-900 mb-4">Suggested Lines</h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {analysis.suggested_lines.safe && (
                <div className="bg-green-50 rounded-lg p-4 border border-green-200">
                  <div className="text-sm text-gray-600 mb-1">Safe</div>
                  <div className="text-xl font-bold text-green-600">
                    Over {analysis.suggested_lines.safe.toFixed(1)}
                  </div>
                  <div className="text-xs text-gray-500 mt-1">~75% likely</div>
                </div>
              )}
              {analysis.suggested_lines.standard && (
                <div className="bg-blue-50 rounded-lg p-4 border border-blue-200">
                  <div className="text-sm text-gray-600 mb-1">Standard</div>
                  <div className="text-xl font-bold text-blue-600">
                    Over {analysis.suggested_lines.standard.toFixed(1)}
                  </div>
                  <div className="text-xs text-gray-500 mt-1">~50% likely</div>
                </div>
              )}
              {analysis.suggested_lines.long_shot && (
                <div className="bg-orange-50 rounded-lg p-4 border border-orange-200">
                  <div className="text-sm text-gray-600 mb-1">Long Shot</div>
                  <div className="text-xl font-bold text-orange-600">
                    Over {analysis.suggested_lines.long_shot.toFixed(1)}
                  </div>
                  <div className="text-xs text-gray-500 mt-1">~15% likely</div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Parlay Analysis Results */}
      {mode === 'parlay' && parlayAnalysis && (
        <div className="bg-white rounded-lg shadow p-6 space-y-6">
          <h2 className="text-2xl font-bold text-gray-900">Parlay Analysis</h2>

          {/* Overall Assessment */}
          <div className="bg-gradient-to-r from-purple-50 to-pink-50 rounded-lg p-6 border-2 border-purple-200">
            <div className="flex justify-between items-start mb-4">
              <div>
                <div className="text-sm text-gray-600 mb-1">Combined Probability</div>
                <div className={`text-3xl font-bold ${getProbabilityColor(parlayAnalysis.combined_probability)}`}>
                  {(parlayAnalysis.combined_probability * 100).toFixed(2)}%
                </div>
              </div>
              <div className="text-right">
                <div className="text-sm text-gray-600 mb-1">Combined Odds</div>
                <div className="text-3xl font-bold text-purple-600">
                  {parlayAnalysis.combined_odds}
                </div>
              </div>
            </div>
            <div className="mt-4 pt-4 border-t border-purple-200">
              <div className="text-sm text-gray-600 mb-1">Assessment</div>
              <div className="text-lg font-semibold text-gray-900">{parlayAnalysis.overall_assessment}</div>
            </div>
          </div>

          {/* Individual Legs */}
          <div>
            <h3 className="text-xl font-semibold text-gray-900 mb-4">Leg Analysis</h3>
            <div className="space-y-3">
              {parlayAnalysis.legs.map((leg, idx) => (
                <div key={idx} className="bg-gray-50 rounded-lg p-4 border border-gray-200">
                  <div className="flex justify-between items-start">
                    <div>
                      <div className="font-semibold text-gray-900">{leg.player_name}</div>
                      <div className="text-sm text-gray-600">{leg.bet_line}</div>
                      {leg.mean && (
                        <div className="text-xs text-gray-500 mt-1">
                          Expected: {leg.mean.toFixed(1)} ± {leg.std_dev.toFixed(1)}
                        </div>
                      )}
                    </div>
                    <div className="text-right">
                      {leg.probability !== null && leg.probability !== undefined ? (
                        <>
                          <div className={`text-lg font-bold ${getProbabilityColor(leg.probability)}`}>
                            {(leg.probability * 100).toFixed(1)}%
                          </div>
                          <div className="text-xs text-gray-500">Likelihood</div>
                        </>
                      ) : (
                        <div className="text-sm text-red-600">{(leg as any).error || 'Error'}</div>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

