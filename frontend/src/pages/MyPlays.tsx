import { useState, useEffect } from 'react';
import { format } from 'date-fns';
import apiService, { Play } from '../services/api';
import { parseDateString } from '../utils/dateUtils';
import { useSport } from '../contexts/SportContext';

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

interface Parlay {
  parlay_id: number;
  name?: string;
  total_odds?: number;
  total_probability?: number;
  total_legs: number;
  legs_hit: number;
  status: string;
  notes?: string;
  created_at?: string;
  plays: Array<{
    play_id: number;
    player_id: number;
    player_name: string;
    game_id: number;
    game_date?: string;
    stat_type: string;
    bet_line: string;
    status: string;
    actual_result?: number;
  }>;
}

export default function MyPlays() {
  const { sport } = useSport();
  const [plays, setPlays] = useState<Play[]>([]);
  const [parlays, setParlays] = useState<Parlay[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [analyzingPlayId, setAnalyzingPlayId] = useState<number | null>(null);
  const [playAnalysis, setPlayAnalysis] = useState<{ [playId: number]: AnalysisResult }>({});
  const [expandedParlays, setExpandedParlays] = useState<Set<number>>(new Set());

  useEffect(() => {
    loadPlays();
    loadParlays();
    loadStats();
  }, [statusFilter, sport]);

  const loadPlays = async () => {
    setLoading(true);
    try {
      const playsData = await apiService.getPlays(statusFilter === 'all' ? undefined : statusFilter, 100, sport);
      setPlays(playsData);
    } catch (error) {
      console.error('Error loading plays:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadParlays = async () => {
    try {
      const parlaysData = await apiService.getParlays(statusFilter === 'all' ? undefined : statusFilter, sport);
      setParlays(parlaysData);
    } catch (error) {
      console.error('Error loading parlays:', error);
    }
  };

  const loadStats = async () => {
    try {
      const statsData = await apiService.getPlayStats(sport);
      setStats(statsData);
    } catch (error) {
      console.error('Error loading stats:', error);
    }
  };

  const handleUpdatePlay = async (playId: number, updates: { status?: string; actual_result?: number }) => {
    try {
      await apiService.updatePlay(playId, updates);
      loadPlays();
      loadStats();
    } catch (error) {
      console.error('Error updating play:', error);
      alert('Failed to update play');
    }
  };

  const handleDeletePlay = async (playId: number) => {
    if (!confirm('Are you sure you want to delete this play?')) return;
    try {
      await apiService.deletePlay(playId);
      loadPlays();
      loadStats();
    } catch (error) {
      console.error('Error deleting play:', error);
      alert('Failed to delete play');
    }
  };

  const parseBetLine = (betLine: string): { betType: string; lineValue: number } | null => {
    // Parse "Over 24.5" or "Under 10.5" format
    const match = betLine.match(/(Over|Under)\s+([\d.]+)/i);
    if (match) {
      return {
        betType: match[1].charAt(0).toUpperCase() + match[1].slice(1).toLowerCase(),
        lineValue: parseFloat(match[2])
      };
    }
    return null;
  };

  const handleAnalyzePlay = async (play: Play) => {
    const parsed = parseBetLine(play.bet_line);
    if (!parsed) {
      alert('Could not parse bet line. Expected format: "Over 24.5" or "Under 10.5"');
      return;
    }

    // Prevent duplicate analysis if already analyzing or already analyzed
    if (analyzingPlayId === play.play_id || playAnalysis[play.play_id]) {
      return;
    }

    setAnalyzingPlayId(play.play_id);
    try {
      const analysis = await apiService.analyzeBet({
        player_id: play.player_id,
        game_id: play.game_id,
        stat_type: play.stat_type,
        bet_line: parsed.lineValue,
        bet_type: parsed.betType,
      });
      setPlayAnalysis(prev => ({
        ...prev,
        [play.play_id]: analysis
      }));
    } catch (error: any) {
      console.error('Error analyzing play:', error);
      alert(error.response?.data?.detail || error.message || 'Failed to analyze play. Make sure predictions have been generated for this player/game.');
    } finally {
      setAnalyzingPlayId(null);
    }
  };

  const getProbabilityColor = (probability: number) => {
    if (probability >= 0.70) return 'text-green-600';
    if (probability >= 0.50) return 'text-blue-600';
    if (probability >= 0.30) return 'text-yellow-600';
    return 'text-orange-600';
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center h-64">
        <div className="text-gray-500">Loading plays...</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-gray-900">My Plays & Parlays</h1>
        <p className="mt-1 text-sm text-gray-500">Track your betting plays and parlays</p>
      </div>


      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="bg-white rounded-lg shadow p-6">
            <div className="text-sm font-medium text-gray-500">Total Plays</div>
            <div className="mt-2 text-3xl font-bold text-gray-900">{stats.total_plays}</div>
          </div>
          <div className="bg-white rounded-lg shadow p-6">
            <div className="text-sm font-medium text-gray-500">Hit</div>
            <div className="mt-2 text-3xl font-bold text-green-600">{stats.hit}</div>
          </div>
          <div className="bg-white rounded-lg shadow p-6">
            <div className="text-sm font-medium text-gray-500">Miss</div>
            <div className="mt-2 text-3xl font-bold text-red-600">{stats.miss}</div>
          </div>
          <div className="bg-white rounded-lg shadow p-6">
            <div className="text-sm font-medium text-gray-500">Hit Rate</div>
            <div className="mt-2 text-3xl font-bold text-primary-600">{stats.hit_rate.toFixed(1)}%</div>
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="flex gap-2">
        {['all', 'pending', 'hit', 'miss'].map((status) => (
          <button
            key={status}
            onClick={() => setStatusFilter(status)}
            className={`px-4 py-2 rounded-md capitalize ${
              statusFilter === status
                ? 'bg-primary-600 text-white'
                : 'bg-white text-gray-700 hover:bg-gray-100'
            }`}
          >
            {status}
          </button>
        ))}
      </div>

      {/* Combined View: Parlays and Individual Plays */}
      <div className="space-y-6">
        {/* Parlays Section */}
        {parlays.length > 0 && (
          <div>
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">
              🎯 Parlays ({parlays.length})
            </h2>
            <div className="space-y-4">
              {parlays.map((parlay) => {
                const isExpanded = expandedParlays.has(parlay.parlay_id);
                return (
                <div key={parlay.parlay_id} className="bg-gradient-to-r from-blue-50 to-purple-50 rounded-lg shadow-lg p-6 border-2 border-blue-200">
                  <div className="flex justify-between items-start mb-4">
                    <div className="flex-1">
                      <div className="flex items-center gap-3 mb-2">
                        <button
                          onClick={() => {
                            const newExpanded = new Set(expandedParlays);
                            if (isExpanded) {
                              newExpanded.delete(parlay.parlay_id);
                            } else {
                              newExpanded.add(parlay.parlay_id);
                            }
                            setExpandedParlays(newExpanded);
                          }}
                          className="mr-2 text-gray-600 hover:text-gray-900"
                        >
                          {isExpanded ? '▼' : '▶'}
                        </button>
                        <h3 className="text-lg font-bold text-gray-900">
                          {parlay.name || `${parlay.total_legs}-Leg Parlay`}
                        </h3>
                        <span className={`px-2 py-1 text-xs rounded-full ${
                          parlay.status === 'hit'
                            ? 'bg-green-100 text-green-800'
                            : parlay.status === 'miss'
                            ? 'bg-red-100 text-red-800'
                            : parlay.status === 'partial'
                            ? 'bg-yellow-100 text-yellow-800'
                            : 'bg-gray-100 text-gray-800'
                        }`}>
                          {parlay.status}
                        </span>
                      </div>
                      <div className="text-sm text-gray-600 space-y-1">
                        <div>
                          <span className="font-medium">Legs:</span> {parlay.legs_hit}/{parlay.total_legs} hit
                        </div>
                        {parlay.total_probability && (
                          <div>
                            <span className="font-medium">Combined Probability:</span> {(parlay.total_probability * 100).toFixed(2)}%
                          </div>
                        )}
                        {parlay.created_at && (
                          <div className="text-xs text-gray-500">
                            Created: {format(new Date(parlay.created_at), 'MMM d, yyyy h:mm a')}
                          </div>
                        )}
                        {parlay.notes && (
                          <div className="text-gray-500 italic text-xs">{parlay.notes}</div>
                        )}
                      </div>
                    </div>
                    <div className="text-right space-y-2">
                      {parlay.total_odds && (
                        <>
                          <div className="text-2xl font-bold text-blue-600">
                            {parlay.total_odds > 0 ? '+' : ''}{parlay.total_odds.toFixed(0)}
                          </div>
                          <div className="text-xs text-gray-500">Odds</div>
                        </>
                      )}
                      <div className="flex gap-2">
                        <button
                          onClick={async () => {
                            try {
                              const altParlay = await apiService.generateAlternativeParlay(parlay.parlay_id);
                              alert(`Alternative parlay created! New parlay ID: ${altParlay.parlay_id}`);
                              loadParlays(); // Refresh the list
                            } catch (error: any) {
                              console.error('Error generating alternative parlay:', error);
                              alert(error.response?.data?.detail || error.message || 'Failed to generate alternative parlay');
                            }
                          }}
                          className="px-3 py-1 bg-green-600 text-white rounded text-sm hover:bg-green-700"
                          title="Generate an alternative parlay with safer lines"
                        >
                          Alternative
                        </button>
                        <button
                          onClick={async () => {
                            if (!confirm(`Are you sure you want to delete "${parlay.name || `${parlay.total_legs}-Leg Parlay`}"? This cannot be undone.`)) {
                              return;
                            }
                            try {
                              await apiService.deleteParlay(parlay.parlay_id);
                              alert('Parlay deleted successfully');
                              loadParlays(); // Refresh the list
                            } catch (error: any) {
                              console.error('Error deleting parlay:', error);
                              alert(error.response?.data?.detail || error.message || 'Failed to delete parlay');
                            }
                          }}
                          className="px-3 py-1 bg-red-600 text-white rounded text-sm hover:bg-red-700"
                          title="Delete this parlay"
                        >
                          Delete
                        </button>
                      </div>
                    </div>
                  </div>
                  {isExpanded && (
                    <>
                  <div className="mt-4 border-t border-blue-200 pt-4">
                    <div className="flex justify-between items-center mb-3">
                      <div className="text-sm font-medium text-gray-700">Parlay Legs:</div>
                      <button
                        onClick={async () => {
                          if (parlay.plays.length < 2) {
                            alert('Parlay must have at least 2 legs');
                            return;
                          }
                          // Prevent duplicate analysis
                          if (analyzingPlayId === -parlay.parlay_id || playAnalysis[-parlay.parlay_id]) {
                            return;
                          }

                          setAnalyzingPlayId(-parlay.parlay_id); // Use negative ID for parlays
                          try {
                            const legs = parlay.plays.map(play => {
                              const parsed = parseBetLine(play.bet_line);
                              if (!parsed) {
                                throw new Error(`Could not parse bet line: ${play.bet_line}`);
                              }
                              return {
                                player_id: play.player_id,
                                game_id: play.game_id,
                                stat_type: play.stat_type,
                                bet_line: parsed.lineValue,
                                bet_type: parsed.betType,
                              };
                            });
                            const analysis = await apiService.analyzeParlay({ legs });
                            setPlayAnalysis(prev => ({
                              ...prev,
                              [-parlay.parlay_id]: analysis as any
                            }));
                          } catch (error: any) {
                            console.error('Error analyzing parlay:', error);
                            alert(error.response?.data?.detail || error.message || 'Failed to analyze parlay.');
                          } finally {
                            setAnalyzingPlayId(null);
                          }
                        }}
                        disabled={analyzingPlayId === -parlay.parlay_id}
                        className="px-3 py-1 bg-primary-600 text-white rounded text-sm hover:bg-primary-700 disabled:bg-gray-300 disabled:cursor-not-allowed"
                      >
                        {analyzingPlayId === -parlay.parlay_id ? 'Analyzing...' : 'Analyze Parlay'}
                      </button>
                    </div>
                    <div className="space-y-2">
                      {parlay.plays.map((play) => (
                        <div key={play.play_id} className="bg-white rounded p-3 border border-blue-200">
                          <div className="flex items-center justify-between">
                            <div className="flex-1">
                              <div className="font-medium text-sm text-gray-900">
                                {play.player_name}
                              </div>
                              <div className="text-xs text-gray-600 mt-1">
                                {play.stat_type === 'points' ? 'PTS' : play.stat_type === 'rebounds' ? 'REB' : 'AST'} • {play.bet_line}
                              </div>
                              {play.actual_result !== null && play.actual_result !== undefined && (
                                <div className="text-xs text-gray-500 mt-1">
                                  Actual: {play.actual_result}
                                </div>
                              )}
                            </div>
                            <span className={`px-2 py-1 text-xs rounded-full ml-2 ${
                              play.status === 'hit'
                                ? 'bg-green-100 text-green-800'
                                : play.status === 'miss'
                                ? 'bg-red-100 text-red-800'
                                : 'bg-gray-100 text-gray-800'
                            }`}>
                              {play.status}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                    
                    {/* Parlay Analysis Results */}
                    {playAnalysis[-parlay.parlay_id] && (
                      <div className="mt-4 pt-4 border-t border-gray-200 bg-purple-50 rounded-lg p-4">
                        <div className="flex justify-between items-start mb-4">
                          <div>
                            <div className="text-sm text-gray-600 mb-1">Combined Probability</div>
                            <div className={`text-2xl font-bold ${getProbabilityColor((playAnalysis[-parlay.parlay_id] as any).combined_probability)}`}>
                              {((playAnalysis[-parlay.parlay_id] as any).combined_probability * 100).toFixed(2)}%
                            </div>
                          </div>
                          <div className="text-right">
                            <div className="text-sm text-gray-600 mb-1">Combined Odds</div>
                            <div className="text-2xl font-bold text-purple-600">
                              {(playAnalysis[-parlay.parlay_id] as any).combined_odds}
                            </div>
                          </div>
                        </div>
                        <div className="mb-4">
                          <div className="text-sm text-gray-600 mb-1">Assessment</div>
                          <div className="text-lg font-semibold text-gray-900">{(playAnalysis[-parlay.parlay_id] as any).overall_assessment}</div>
                        </div>
                        <div>
                          <div className="text-sm font-medium text-gray-700 mb-2">Leg Analysis</div>
                          <div className="space-y-2">
                            {((playAnalysis[-parlay.parlay_id] as any).legs || []).map((leg: any, idx: number) => (
                              <div key={idx} className="bg-white rounded p-2 flex justify-between items-center">
                                <div>
                                  <div className="font-medium text-gray-900">{leg.player_name}</div>
                                  <div className="text-sm text-gray-600">{leg.bet_line}</div>
                                </div>
                                <div className={`font-bold ${getProbabilityColor(leg.probability || 0)}`}>
                                  {leg.probability !== null && leg.probability !== undefined ? `${(leg.probability * 100).toFixed(1)}%` : 'N/A'}
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                        <button
                          onClick={() => {
                            const newAnalysis = { ...playAnalysis };
                            delete newAnalysis[-parlay.parlay_id];
                            setPlayAnalysis(newAnalysis);
                          }}
                          className="mt-3 text-sm text-gray-500 hover:text-gray-700"
                        >
                          Hide Analysis
                        </button>
                      </div>
                    )}
                  </div>
                    </>
                  )}
                </div>
              );
              })}
            </div>
          </div>
        )}

        {/* Individual Plays Section */}
        {plays.length > 0 && (
          <div>
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">
              📋 Individual Plays ({plays.length})
            </h2>
            {plays.length === 0 ? (
              <div className="bg-white rounded-lg shadow p-8 text-center text-gray-500">
                No individual plays found. Create plays from game predictions.
              </div>
            ) : (
              <div className="space-y-4">
          {plays.map((play) => (
            <div key={play.play_id} className="bg-white rounded-lg shadow p-6">
              <div className="flex justify-between items-start">
                <div className="flex-1">
                  <div className="flex items-center gap-3 mb-2">
                    <div className="font-bold text-lg text-gray-900">{play.player_name || `Player ${play.player_id}`}</div>
                    <span className={`px-2 py-1 text-xs rounded-full ${
                      play.status === 'hit'
                        ? 'bg-green-100 text-green-800'
                        : play.status === 'miss'
                        ? 'bg-red-100 text-red-800'
                        : 'bg-gray-100 text-gray-800'
                    }`}>
                      {play.status}
                    </span>
                  </div>
                  <div className="text-sm text-gray-600 space-y-1">
                    <div>
                      <span className="font-medium">Stat:</span> {play.stat_type} •{' '}
                      <span className="font-medium">Bet:</span> {play.bet_line}
                    </div>
                    {play.game_date && (
                      <div>
                        <span className="font-medium">Game Date:</span>{' '}
                        {play.game_date ? format(parseDateString(play.game_date), 'MMM d, yyyy') : 'N/A'}
                      </div>
                    )}
                    {play.predicted_min !== undefined && play.predicted_max !== undefined && (
                      <div>
                        <span className="font-medium">Predicted Range:</span> {play.predicted_min} - {play.predicted_max}
                      </div>
                    )}
                    {play.actual_result !== null && (
                      <div>
                        <span className="font-medium">Actual Result:</span> {play.actual_result}
                      </div>
                    )}
                    {play.notes && (
                      <div className="text-gray-500 italic">{play.notes}</div>
                    )}
                  </div>
                </div>
                <div className="flex gap-2 ml-4">
                  <button
                    onClick={() => handleAnalyzePlay(play)}
                    disabled={analyzingPlayId === play.play_id}
                    className="px-3 py-1 bg-primary-600 text-white rounded text-sm hover:bg-primary-700 disabled:bg-gray-300 disabled:cursor-not-allowed"
                  >
                    {analyzingPlayId === play.play_id ? 'Analyzing...' : 'Analyze'}
                  </button>
                  {play.status === 'pending' && (
                    <>
                      <button
                        onClick={() => {
                          const result = prompt('Enter actual result:');
                          if (result) {
                            handleUpdatePlay(play.play_id, {
                              status: 'hit',
                              actual_result: Number(result),
                            });
                          }
                        }}
                        className="px-3 py-1 bg-green-600 text-white rounded text-sm hover:bg-green-700"
                      >
                        Hit
                      </button>
                      <button
                        onClick={() => {
                          const result = prompt('Enter actual result:');
                          if (result) {
                            handleUpdatePlay(play.play_id, {
                              status: 'miss',
                              actual_result: Number(result),
                            });
                          }
                        }}
                        className="px-3 py-1 bg-red-600 text-white rounded text-sm hover:bg-red-700"
                      >
                        Miss
                      </button>
                    </>
                  )}
                  <button
                    onClick={() => handleDeletePlay(play.play_id)}
                    className="px-3 py-1 bg-gray-200 text-gray-700 rounded text-sm hover:bg-gray-300"
                  >
                    Delete
                  </button>
                </div>
              </div>
              
              {/* Analysis Results */}
              {playAnalysis[play.play_id] && (
                <div className="mt-4 pt-4 border-t border-gray-200 bg-blue-50 rounded-lg p-4">
                  <div className="flex justify-between items-start mb-4">
                    <div>
                      <div className="text-sm text-gray-600 mb-1">Bet Line</div>
                      <div className="text-xl font-bold text-gray-900">{playAnalysis[play.play_id].bet_line}</div>
                    </div>
                    <div className="text-right">
                      <div className="text-sm text-gray-600 mb-1">Likelihood</div>
                      <div className={`text-2xl font-bold ${getProbabilityColor(playAnalysis[play.play_id].probability)}`}>
                        {(playAnalysis[play.play_id].probability * 100).toFixed(1)}%
                      </div>
                    </div>
                  </div>
                  
                  <div className="grid grid-cols-2 gap-4 mb-4">
                    <div>
                      <div className="text-sm text-gray-600">Expected Mean</div>
                      <div className="text-lg font-semibold text-gray-900">
                        {playAnalysis[play.play_id].mean.toFixed(1)} ± {playAnalysis[play.play_id].std_dev.toFixed(1)}
                      </div>
                    </div>
                    <div>
                      <div className="text-sm text-gray-600">Confidence</div>
                      <div className="text-lg font-semibold text-gray-900 capitalize">
                        {playAnalysis[play.play_id].confidence_level} • {playAnalysis[play.play_id].volatility_level}
                      </div>
                    </div>
                  </div>

                  {playAnalysis[play.play_id].reasoning && (
                    <div className="mb-4">
                      <div className="text-sm text-gray-600 mb-1">Analysis</div>
                      <div className="text-sm text-gray-700">{playAnalysis[play.play_id].reasoning}</div>
                    </div>
                  )}

                  {playAnalysis[play.play_id].alternatives.length > 0 && (
                    <div>
                      <div className="text-sm font-medium text-gray-700 mb-2">Alternative Plays</div>
                      <div className="space-y-2">
                        {playAnalysis[play.play_id].alternatives.map((alt, idx) => (
                          <div key={idx} className="bg-white rounded p-2 flex justify-between items-center">
                            <div>
                              <div className="font-medium text-gray-900">{alt.bet_line}</div>
                              <div className="text-xs text-gray-500">{alt.reason}</div>
                            </div>
                            <div className={`font-bold ${getProbabilityColor(alt.probability)}`}>
                              {(alt.probability * 100).toFixed(1)}%
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  <button
                    onClick={() => {
                      const newAnalysis = { ...playAnalysis };
                      delete newAnalysis[play.play_id];
                      setPlayAnalysis(newAnalysis);
                    }}
                    className="mt-3 text-sm text-gray-500 hover:text-gray-700"
                  >
                    Hide Analysis
                  </button>
                </div>
              )}
            </div>
              ))}
              </div>
            )}
          </div>
        )}

        {/* Empty State */}
        {parlays.length === 0 && plays.length === 0 && (
          <div className="bg-white rounded-lg shadow p-8 text-center text-gray-500">
            No plays or parlays found. Create plays from game predictions or build parlays using the Parlay Builder.
          </div>
        )}
      </div>
    </div>
  );
}

