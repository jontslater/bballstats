import { useState, useEffect } from 'react';
import apiService from '../services/api';
import { parseDateString, formatDateDisplay } from '../utils/dateUtils';

interface PredictionResult {
  prediction_id: number;
  player_id: number;
  player_name: string;
  game_id: number;
  game_date: string;
  game_matchup?: string | null;
  home_team?: string | null;
  away_team?: string | null;
  stat_type: string;
  bet_type: string;
  line: number | null;
  predicted_mean: number | null;
  predicted_std: number | null;
  actual_result: number | null;
  hit: boolean | null | 'void';  // Can be true, false, null (pending), or 'void' (didn't play)
  probability: number | null;
  confidence_level: string | null;
  volatility_level: string | null;
}

interface AccuracyStats {
  total: number;
  evaluated: number;
  unevaluated: number;
  hits: number;
  misses: number;
  accuracy: number;
  by_bet_type: {
    [key: string]: {
      hits: number;
      misses: number;
      evaluated: number;
      unevaluated: number;
      total: number;
      accuracy: number;
    };
  };
}

interface EvaluationStatus {
  total_predictions: number;
  evaluated_predictions: number;
  unevaluated_predictions: number;
  finished_games_with_unevaluated: number;
  total_finished_games: number;
  evaluation_percentage: number;
}

interface ParlayResult {
  parlay_id: number;
  name: string | null;
  status: string;
  legs_hit: number;
  total_legs: number;
  total_odds: number | null;
  total_probability: number | null;
  created_at: string | null;
  plays: Array<{
    play_id: number;
    player_name: string;
    game_date: string | null;
    stat_type: string;
    bet_line: string | null;
    status: string;
    actual_result: number | null;
  }>;
}

export default function HistoricalResults() {
  const [activeTab, setActiveTab] = useState<'predictions' | 'parlays'>('predictions');
  const [results, setResults] = useState<PredictionResult[]>([]);
  const [parlayResults, setParlayResults] = useState<ParlayResult[]>([]);
  const [stats, setStats] = useState<AccuracyStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [evaluating, setEvaluating] = useState(false);
  const [evaluationStatus, setEvaluationStatus] = useState<EvaluationStatus | null>(null);
  const [evaluatingAll, setEvaluatingAll] = useState(false);
  const [evaluationProgress, setEvaluationProgress] = useState<{
    progress: number;
    message: string;
    step?: number;
    total_steps?: number;
    games_processed?: number;
    total_games?: number;
    total_evaluated?: number;
    total_skipped?: number;
    total_errors?: number;
  } | null>(null);
  
  // Filters - default to last 30 days to avoid loading too much data
  const getDefaultStartDate = () => {
    const date = new Date();
    date.setDate(date.getDate() - 30);
    return date.toISOString().split('T')[0];
  };
  
  const getDefaultEndDate = () => {
    return new Date().toISOString().split('T')[0];
  };

  const [startDate, setStartDate] = useState<string>(getDefaultStartDate());
  const [endDate, setEndDate] = useState<string>(getDefaultEndDate());
  const [betTypeFilter, setBetTypeFilter] = useState<string>('');
  const [statTypeFilter, setStatTypeFilter] = useState<string>('');
  const [parlayStatusFilter, setParlayStatusFilter] = useState<string>('');
  const [parlayTypeFilter, setParlayTypeFilter] = useState<string>('all'); // Filter by parlay type: all, safe_long, builder, suggested, combo
  const [collapsedParlays, setCollapsedParlays] = useState<Set<string>>(new Set()); // Track collapsed parlays

  useEffect(() => {
    loadData();
    if (activeTab === 'predictions') {
      loadEvaluationStatus();
    }
  }, [activeTab]);

  useEffect(() => {
    loadData();
  }, [startDate, endDate, betTypeFilter, statTypeFilter, parlayStatusFilter]);

  const loadEvaluationStatus = async () => {
    try {
      const status = await apiService.getEvaluationStatus();
      setEvaluationStatus(status);
    } catch (error) {
      console.error('Failed to load evaluation status:', error);
    }
  };

  const handleEvaluateAll = async () => {
    if (!confirm('This will collect box scores (if needed) and evaluate all predictions for finished games. This may take a few minutes. Continue?')) {
      return;
    }

    setEvaluatingAll(true);
    setEvaluationProgress({ progress: 0, message: 'Starting evaluation...' });
    
    try {
      const result = await apiService.evaluateAllFinishedGames(90, (progress) => {
        setEvaluationProgress(progress);
      });
      
      if (result) {
        setEvaluationProgress({
          progress: 100,
          message: result.message || 'Evaluation complete!',
          total_evaluated: result.total_evaluated,
          total_skipped: result.total_skipped,
          total_errors: result.total_errors,
          games_processed: result.games_processed
        });
        
        // Show completion message after a brief delay
        setTimeout(() => {
          alert(`Evaluation complete!\n\nGames processed: ${result.games_processed}\nPredictions evaluated: ${result.total_evaluated}\nSkipped: ${result.total_skipped}\nErrors: ${result.total_errors}`);
          setEvaluationProgress(null);
        }, 1000);
      }
      
      // Reload data and status
      await loadData();
      await loadEvaluationStatus();
    } catch (error: any) {
      console.error('Failed to evaluate all games:', error);
      setEvaluationProgress(null);
      alert(`Error: ${error.response?.data?.detail || error.message}`);
    } finally {
      setEvaluatingAll(false);
    }
  };

  const loadData = async () => {
    setLoading(true);
    try {
      if (activeTab === 'predictions') {
        const [resultsData, statsData] = await Promise.all([
          apiService.getPredictionResults(
            startDate || undefined,
            endDate || undefined,
            betTypeFilter || undefined,
            statTypeFilter || undefined
          ),
          apiService.getAccuracyStats(
            startDate || undefined,
            endDate || undefined,
            betTypeFilter || undefined
          )
        ]);
        setResults(resultsData);
        setStats(statsData);
      } else {
        const parlayData = await apiService.getParlayResults(
          startDate || undefined,
          endDate || undefined,
          parlayStatusFilter || undefined
        );
        setParlayResults(parlayData.parlays || []);
      }
    } catch (error) {
      console.error('Error loading historical results:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleEvaluateYesterday = async () => {
    setEvaluating(true);
    try {
      const yesterday = new Date();
      yesterday.setDate(yesterday.getDate() - 1);
      const dateStr = yesterday.toISOString().split('T')[0];
      
      await apiService.evaluateDate(dateStr);
      await loadData(); // Reload data after evaluation
      alert('Predictions evaluated successfully!');
    } catch (error) {
      console.error('Error evaluating predictions:', error);
      alert('Error evaluating predictions');
    } finally {
      setEvaluating(false);
    }
  };

  const handleFilter = () => {
    loadData();
  };

  const copyResultsToClipboard = () => {
    if (results.length === 0) {
      alert('No results to copy');
      return;
    }

    // Format results for Discord (plain text, no special formatting)
    const lines: string[] = [];
    
    // Get date range
    const startDateStr = startDate ? formatDateDisplay(parseDateString(startDate)) : 'N/A';
    const endDateStr = endDate ? formatDateDisplay(parseDateString(endDate)) : 'N/A';
    const dateRange = startDate === endDate ? startDateStr : `${startDateStr} - ${endDateStr}`;
    
    lines.push(`📊 Historical Results - ${dateRange}`);
    lines.push('');
    
    // Group by game
    const gamesMap = new Map<number, PredictionResult[]>();
    results.forEach(result => {
      if (!gamesMap.has(result.game_id)) {
        gamesMap.set(result.game_id, []);
      }
      gamesMap.get(result.game_id)!.push(result);
    });

    // Sort games by date (most recent first)
    const gamesArray = Array.from(gamesMap.entries()).sort((a, b) => {
      const dateA = new Date(a[1][0].game_date).getTime();
      const dateB = new Date(b[1][0].game_date).getTime();
      return dateB - dateA;
    });

    // Format each game
    gamesArray.forEach(([gameId, gameResults]) => {
      const firstResult = gameResults[0];
      const gameMatchup = firstResult.game_matchup || 
                         `${firstResult.away_team || 'Away'} @ ${firstResult.home_team || 'Home'}`;
      const gameDate = formatDateDisplay(parseDateString(firstResult.game_date));
      
      const hits = gameResults.filter(r => r.hit === true).length;
      const misses = gameResults.filter(r => r.hit === false).length;
      const voids = gameResults.filter(r => r.hit === 'void').length;
      const pending = gameResults.filter(r => r.hit === null).length;
      const evaluated = hits + misses;
      const accuracy = evaluated > 0 ? ((hits / evaluated) * 100).toFixed(1) : '0.0';
      
      lines.push(`🏀 ${gameMatchup} - ${gameDate}`);
      lines.push(`   ${hits} Hits / ${misses} Misses (${accuracy}% accuracy)`);
      if (pending > 0) {
        lines.push(`   ${pending} Pending`);
      }
      lines.push('');
      
      // Group by player
      const byPlayer = new Map<string, PredictionResult[]>();
      gameResults.forEach(result => {
        const playerKey = result.player_name;
        if (!byPlayer.has(playerKey)) {
          byPlayer.set(playerKey, []);
        }
        byPlayer.get(playerKey)!.push(result);
      });

      // Format each player's results
      Array.from(byPlayer.entries()).sort((a, b) => a[0].localeCompare(b[0])).forEach(([playerName, playerResults]) => {
        lines.push(`  ${playerName}`);
        
        playerResults.forEach(result => {
          const statType = result.stat_type === 'points' ? 'PTS' : 
                          result.stat_type === 'rebounds' ? 'REB' : 
                          result.stat_type === 'assists' ? 'AST' : 
                          result.stat_type.toUpperCase();
          
          const betType = result.bet_type === 'safe' ? 'SAFE' : 
                         result.bet_type === 'standard' ? 'STD' : 
                         result.bet_type === 'long_shot' ? 'LONG' : 
                         result.bet_type.toUpperCase();
          
          const line = result.line !== null ? result.line.toFixed(1) : 'N/A';
          const predicted = result.predicted_mean !== null && result.predicted_std !== null
            ? `${result.predicted_mean.toFixed(1)} ± ${result.predicted_std.toFixed(1)}`
            : 'N/A';
          const actual = result.actual_result !== null ? result.actual_result.toFixed(1) : 'N/A';
          const probability = result.probability !== null ? (result.probability * 100).toFixed(1) : 'N/A';
          
          let resultIcon = '⏳';
          if (result.hit === true) {
            resultIcon = '✅';
          } else if (result.hit === false) {
            resultIcon = '❌';
          } else if (result.hit === 'void') {
            resultIcon = '⚠️';
          }
          
          const resultText = result.hit === true ? 'HIT' : 
                           result.hit === false ? 'MISS' : 
                           result.hit === 'void' ? 'VOID' :
                           'PENDING';
          
          lines.push(`    ${resultIcon} ${statType} Over ${line} (${betType}) - Predicted: ${predicted}, Actual: ${actual} - ${resultText} (${probability}%)`);
        });
      });
      
      lines.push('');
    });

    // Add summary
    if (stats) {
      lines.push('---');
      lines.push(`Summary: ${stats.hits} Hits / ${stats.misses} Misses (${stats.accuracy.toFixed(1)}% accuracy)`);
      lines.push(`Total: ${stats.total} predictions (${stats.evaluated || 0} evaluated, ${stats.unevaluated || 0} pending)`);
    }

    // Join with newlines and copy to clipboard
    const text = lines.join('\n');
    
    // Use the Clipboard API
    navigator.clipboard.writeText(text).then(() => {
      alert(`Copied ${results.length} results to clipboard! Ready to paste in Discord.`);
    }).catch(err => {
      console.error('Failed to copy:', err);
      // Fallback: create a textarea and copy
      const textarea = document.createElement('textarea');
      textarea.value = text;
      textarea.style.position = 'fixed';
      textarea.style.opacity = '0';
      document.body.appendChild(textarea);
      textarea.select();
      try {
        document.execCommand('copy');
        alert(`Copied ${results.length} results to clipboard! Ready to paste in Discord.`);
      } catch (err) {
        alert('Failed to copy. Please try selecting and copying manually.');
      }
      document.body.removeChild(textarea);
    });
  };

  const getHitBadge = (hit: boolean | null) => {
    if (hit === null) return <span className="text-gray-500">Pending</span>;
    if (hit) {
      return <span className="px-2 py-1 bg-green-100 text-green-800 rounded text-sm font-semibold">✓ Hit</span>;
    }
    return <span className="px-2 py-1 bg-red-100 text-red-800 rounded text-sm font-semibold">✗ Miss</span>;
  };

  const getBetTypeBadge = (betType: string) => {
    const colors: { [key: string]: string } = {
      safe: 'bg-blue-100 text-blue-800',
      standard: 'bg-yellow-100 text-yellow-800',
      long_shot: 'bg-purple-100 text-purple-800',
    };
    return (
      <span className={`px-2 py-1 rounded text-sm font-semibold ${colors[betType] || 'bg-gray-100 text-gray-800'}`}>
        {betType.charAt(0).toUpperCase() + betType.slice(1)}
      </span>
    );
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center h-64">
        <div className="text-lg">Loading historical results...</div>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Evaluation Progress Indicator */}
      {evaluationProgress && (
        <div className="fixed top-4 right-4 bg-white rounded-lg shadow-lg p-4 border-2 border-blue-500 z-50 min-w-[300px] max-w-[400px]">
          <div className="flex items-center justify-between mb-2">
            <h3 className="font-semibold text-gray-900">Evaluating Predictions</h3>
            <span className="text-sm font-semibold text-blue-600">{evaluationProgress.progress}%</span>
          </div>
          <div className="w-full bg-gray-200 rounded-full h-2.5 mb-2">
            <div
              className="bg-blue-600 h-2.5 rounded-full transition-all duration-300"
              style={{ width: `${evaluationProgress.progress}%` }}
            />
          </div>
          <p className="text-sm text-gray-600 mb-1">{evaluationProgress.message}</p>
          {evaluationProgress.games_processed !== undefined && evaluationProgress.total_games !== undefined && (
            <p className="text-xs text-gray-500">
              Games: {evaluationProgress.games_processed}/{evaluationProgress.total_games}
              {evaluationProgress.total_evaluated !== undefined && (
                <> • Evaluated: {evaluationProgress.total_evaluated}</>
              )}
            </p>
          )}
        </div>
      )}
      
      <div className="mb-6">
        <div className="flex justify-between items-center mb-2">
          <div>
            <h1 className="text-3xl font-bold">Historical Results</h1>
            <p className="text-gray-600">View past predictions and track accuracy</p>
          </div>
          <div className="flex gap-4 items-center">
            {evaluationStatus && (
              <div className="text-sm text-gray-600">
                <span className="font-semibold">{evaluationStatus.evaluated_predictions}</span> / <span className="font-semibold">{evaluationStatus.total_predictions}</span> evaluated
                {evaluationStatus.finished_games_with_unevaluated > 0 && (
                  <span className="ml-2 text-orange-600">
                    ({evaluationStatus.finished_games_with_unevaluated} games pending)
                  </span>
                )}
              </div>
            )}
            {results.length > 0 && (
              <button
                onClick={copyResultsToClipboard}
                className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 flex items-center gap-2"
                title="Copy results in Discord-friendly format"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                </svg>
                Copy Results
              </button>
            )}
            {results.length > 0 && (
              <button
                onClick={copyResultsToClipboard}
                className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 flex items-center gap-2"
                title="Copy results in Discord-friendly format"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                </svg>
                Copy Results
              </button>
            )}
            <button
              onClick={handleEvaluateAll}
              disabled={evaluatingAll || (evaluationStatus?.finished_games_with_unevaluated === 0)}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
            >
              {evaluatingAll ? 'Evaluating...' : 'Evaluate All Finished Games'}
            </button>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="bg-white rounded-lg shadow-md mb-6">
        <div className="border-b border-gray-200">
          <nav className="flex -mb-px">
            <button
              onClick={() => setActiveTab('predictions')}
              className={`px-6 py-4 text-sm font-medium border-b-2 ${
                activeTab === 'predictions'
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              Predictions
            </button>
            <button
              onClick={() => setActiveTab('parlays')}
              className={`px-6 py-4 text-sm font-medium border-b-2 ${
                activeTab === 'parlays'
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              Parlays
            </button>
          </nav>
        </div>
        
        {/* Sub-tabs for Parlay Types (only show when Parlays tab is active) */}
        {activeTab === 'parlays' && (
          <div className="border-b border-gray-200 bg-gray-50">
            <nav className="flex -mb-px px-4">
              <button
                onClick={() => setParlayTypeFilter('all')}
                className={`px-4 py-3 text-xs font-medium border-b-2 ${
                  parlayTypeFilter === 'all'
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                All
              </button>
              <button
                onClick={() => setParlayTypeFilter('safe_long')}
                className={`px-4 py-3 text-xs font-medium border-b-2 ${
                  parlayTypeFilter === 'safe_long'
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                12 Leg
              </button>
              <button
                onClick={() => setParlayTypeFilter('builder')}
                className={`px-4 py-3 text-xs font-medium border-b-2 ${
                  parlayTypeFilter === 'builder'
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                Builder
              </button>
              <button
                onClick={() => setParlayTypeFilter('suggested')}
                className={`px-4 py-3 text-xs font-medium border-b-2 ${
                  parlayTypeFilter === 'suggested'
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                Suggested
              </button>
              <button
                onClick={() => setParlayTypeFilter('combo')}
                className={`px-4 py-3 text-xs font-medium border-b-2 ${
                  parlayTypeFilter === 'combo'
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                Combos
              </button>
            </nav>
          </div>
        )}
      </div>

      {/* Accuracy Stats - Only show for predictions */}
      {activeTab === 'predictions' && stats && (
        <div className="bg-white rounded-lg shadow-md p-6 mb-6">
          <h2 className="text-xl font-semibold mb-4">Accuracy Statistics</h2>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <div className="text-center">
              <div className="text-3xl font-bold text-blue-600">{stats.total}</div>
              <div className="text-sm text-gray-600">Total Predictions</div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-bold text-green-600">{stats.evaluated || 0}</div>
              <div className="text-sm text-gray-600">Evaluated</div>
            </div>
            {(stats.unevaluated || 0) > 0 && (
              <div className="text-center">
                <div className="text-3xl font-bold text-orange-600">{stats.unevaluated || 0}</div>
                <div className="text-sm text-gray-600">Pending</div>
              </div>
            )}
            <div className="text-center">
              <div className="text-3xl font-bold text-green-600">{stats.hits}</div>
              <div className="text-sm text-gray-600">Hits</div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-bold text-red-600">{stats.misses}</div>
              <div className="text-sm text-gray-600">Misses</div>
            </div>
            <div className="text-center col-span-2 md:col-span-1">
              <div className="text-3xl font-bold text-purple-600">{stats.accuracy.toFixed(1)}%</div>
              <div className="text-sm text-gray-600">Overall Accuracy</div>
              <div className="text-xs text-gray-500 mt-1">({stats.evaluated || 0} evaluated)</div>
            </div>
          </div>

          {/* By Bet Type - More Prominent */}
          <div className="mt-6 border-t pt-6">
            <h3 className="text-lg font-semibold mb-4">Accuracy by Bet Type</h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {['safe', 'standard', 'long_shot'].map((betType) => {
                const data = stats.by_bet_type[betType];
                if (!data || data.total === 0) {
                  return (
                    <div key={betType} className="bg-gray-50 rounded-lg p-4 border border-gray-200">
                      <div className="font-semibold mb-2 capitalize flex items-center gap-2">
                        {betType === 'safe' && <span className="text-green-600">🟢</span>}
                        {betType === 'standard' && <span className="text-blue-600">🔵</span>}
                        {betType === 'long_shot' && <span className="text-purple-600">🟣</span>}
                        {betType.replace('_', ' ')}
                      </div>
                      <div className="text-sm text-gray-500">No predictions yet</div>
                    </div>
                  );
                }
                
                const evaluated = data.evaluated || 0;
                const unevaluated = data.unevaluated || 0;
                
                // Only calculate accuracy if we have evaluated predictions
                const accuracyColor = evaluated > 0 ? (
                  data.accuracy >= 70 ? 'text-green-600' : 
                  data.accuracy >= 50 ? 'text-yellow-600' : 'text-red-600'
                ) : 'text-gray-500';
                
                return (
                  <div key={betType} className="bg-gradient-to-br from-gray-50 to-gray-100 rounded-lg p-5 border-2 border-gray-200 shadow-sm">
                    <div className="font-semibold mb-3 capitalize flex items-center gap-2 text-lg">
                      {betType === 'safe' && <span className="text-green-600">🟢</span>}
                      {betType === 'standard' && <span className="text-blue-600">🔵</span>}
                      {betType === 'long_shot' && <span className="text-purple-600">🟣</span>}
                      {betType.replace('_', ' ')}
                    </div>
                    <div className="space-y-2">
                      <div className="flex justify-between items-center">
                        <span className="text-sm text-gray-600">Total:</span>
                        <span className="font-semibold">{data.total}</span>
                      </div>
                      {evaluated > 0 && (
                        <>
                          <div className="flex justify-between items-center">
                            <span className="text-sm text-gray-600">Evaluated:</span>
                            <span className="font-semibold text-blue-600">{evaluated}</span>
                          </div>
                          {unevaluated > 0 && (
                            <div className="flex justify-between items-center">
                              <span className="text-sm text-gray-600">Pending:</span>
                              <span className="font-semibold text-orange-600">{unevaluated}</span>
                            </div>
                          )}
                          <div className="flex justify-between items-center">
                            <span className="text-sm text-gray-600">Hits:</span>
                            <span className="font-semibold text-green-600">{data.hits}</span>
                          </div>
                          <div className="flex justify-between items-center">
                            <span className="text-sm text-gray-600">Misses:</span>
                            <span className="font-semibold text-red-600">{data.misses}</span>
                          </div>
                          <div className="border-t pt-2 mt-2">
                            <div className="flex justify-between items-center">
                              <span className="text-sm font-medium text-gray-700">Accuracy:</span>
                              <span className={`text-2xl font-bold ${accuracyColor}`}>
                                {data.accuracy.toFixed(1)}%
                              </span>
                            </div>
                            <div className="text-xs text-gray-500 mt-1 text-right">
                              (of {evaluated} evaluated)
                            </div>
                          </div>
                        </>
                      )}
                      {evaluated === 0 && (
                        <div className="text-sm text-gray-500 text-center py-2">
                          No evaluations yet
                          {unevaluated > 0 && (
                            <div className="text-xs mt-1">({unevaluated} pending box scores)</div>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="bg-white rounded-lg shadow-md p-6 mb-6">
        <h2 className="text-xl font-semibold mb-4">Filters</h2>
        <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Start Date</label>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">End Date</label>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Bet Type</label>
            <select
              value={betTypeFilter}
              onChange={(e) => setBetTypeFilter(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md"
            >
              <option value="">All</option>
              <option value="safe">Safe</option>
              <option value="standard">Standard</option>
              <option value="long_shot">Long Shot</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Stat Type</label>
            <select
              value={statTypeFilter}
              onChange={(e) => setStatTypeFilter(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md"
            >
              <option value="">All</option>
              <option value="points">Points</option>
              <option value="rebounds">Rebounds</option>
              <option value="assists">Assists</option>
            </select>
          </div>
          <div className="flex items-end">
            <button
              onClick={handleFilter}
              className="w-full px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
            >
              Apply Filters
            </button>
          </div>
        </div>
        <div className="mt-4">
          <button
            onClick={handleEvaluateYesterday}
            disabled={evaluating}
            className="px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 disabled:bg-gray-400"
          >
            {evaluating ? 'Evaluating...' : 'Evaluate Yesterday\'s Games'}
          </button>
        </div>
      </div>

      {/* Info Box */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
        <h3 className="text-sm font-semibold text-blue-900 mb-2">Understanding the Predictions</h3>
        <ul className="text-sm text-blue-800 space-y-1">
          <li>
            <strong>Predicted (e.g., "5.3 ± 2.8"):</strong> Mean ± Standard Deviation
            <br />
            <span className="text-blue-700">This means we predicted an average of 5.3, with most results falling between 2.5 and 7.8 (within 1 standard deviation).</span>
          </li>
          <li>
            <strong>Actual:</strong> What the player actually achieved in the game
          </li>
          <li>
            <strong>Line:</strong> The betting line (e.g., "Over 4.5" means we bet the player would score more than 4.5)
          </li>
          <li>
            <strong>"Pass" predictions:</strong> These are filtered out - they weren't recommended bets due to uncertainty
          </li>
        </ul>
      </div>

      {/* Results - Show predictions or parlays based on active tab */}
      {activeTab === 'predictions' ? (
        <div className="space-y-6">
        {results.length === 0 ? (
          <div className="bg-white rounded-lg shadow-md p-8 text-center">
            <p className="text-gray-500">
              No results found. Try evaluating yesterday's games or adjusting filters.
            </p>
            <p className="text-sm text-gray-400 mt-2">
              Note: "Pass" predictions are excluded (they weren't recommended bets)
            </p>
          </div>
        ) : (
          (() => {
            // Group results by game
            const gamesMap = new Map<number, PredictionResult[]>();
            results.forEach(result => {
              if (!gamesMap.has(result.game_id)) {
                gamesMap.set(result.game_id, []);
              }
              gamesMap.get(result.game_id)!.push(result);
            });

            // Convert to array and sort by date
            const gamesArray = Array.from(gamesMap.entries()).sort((a, b) => {
              const dateA = new Date(a[1][0].game_date).getTime();
              const dateB = new Date(b[1][0].game_date).getTime();
              return dateB - dateA; // Most recent first
            });

            return gamesArray.map(([gameId, gameResults]) => {
              const firstResult = gameResults[0];
              const hits = gameResults.filter(r => r.hit === true).length;
              const misses = gameResults.filter(r => r.hit === false).length;
              const voids = gameResults.filter(r => r.hit === 'void').length;
              const pending = gameResults.filter(r => r.hit === null).length;

              return (
                <div key={gameId} className="bg-white rounded-lg shadow-md overflow-hidden">
                  {/* Game Header */}
                  <div className="bg-gray-50 px-6 py-3 border-b border-gray-200">
                    <div className="flex justify-between items-center">
                      <div>
                        <h3 className="text-lg font-semibold text-gray-900">
                          {firstResult.game_matchup || `${firstResult.away_team || 'Away'} @ ${firstResult.home_team || 'Home'}`}
                        </h3>
                        <p className="text-sm text-gray-600">
                          {formatDateDisplay(parseDateString(firstResult.game_date))}
                        </p>
                      </div>
                      <div className="text-right">
                                  <div className="text-sm text-gray-600">
                                    <span className="text-green-600 font-semibold">{hits} Hits</span>
                                    {' / '}
                                    <span className="text-red-600 font-semibold">{misses} Misses</span>
                                    {voids > 0 && <span className="text-yellow-600"> / {voids} Void</span>}
                                    {pending > 0 && <span className="text-gray-500"> / {pending} Pending</span>}
                                  </div>
                        <div className="text-xs text-gray-500 mt-1">
                          {gameResults.length} predictions
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Predictions Table */}
                  <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-gray-200">
                      <thead className="bg-gray-50">
                        <tr>
                          <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Player</th>
                          <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Stat</th>
                          <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Bet Type</th>
                          <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Line</th>
                          <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                            Predicted
                            <span className="block text-xs font-normal text-gray-400 mt-1">(mean ± std dev)</span>
                          </th>
                          <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Actual</th>
                          <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Result</th>
                          <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Probability</th>
                        </tr>
                      </thead>
                      <tbody className="bg-white divide-y divide-gray-200">
                        {gameResults.map((result) => {
                          // Calculate difference between predicted and actual
                          const diff = result.actual_result !== null && result.predicted_mean !== null
                            ? result.actual_result - result.predicted_mean
                            : null;
                          const diffColor = diff !== null
                            ? diff > 0 ? 'text-green-600' : diff < 0 ? 'text-red-600' : 'text-gray-600'
                            : 'text-gray-600';

                          return (
                            <tr key={result.prediction_id} className="hover:bg-gray-50">
                              <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                                {result.player_name}
                              </td>
                              <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 capitalize">
                                {result.stat_type}
                              </td>
                              <td className="px-6 py-4 whitespace-nowrap">
                                {getBetTypeBadge(result.bet_type)}
                              </td>
                              <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                                {result.line !== null ? `Over ${result.line}` : 'N/A'}
                              </td>
                              <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                                {result.predicted_mean !== null
                                  ? (
                                    <div>
                                      <div>{result.predicted_mean.toFixed(1)} ± {result.predicted_std?.toFixed(1) || '0'}</div>
                                      <div className="text-xs text-gray-400">Range: {(result.predicted_mean - (result.predicted_std || 0)).toFixed(1)} - {(result.predicted_mean + (result.predicted_std || 0)).toFixed(1)}</div>
                                    </div>
                                  )
                                  : 'N/A'}
                              </td>
                              <td className="px-6 py-4 whitespace-nowrap">
                                {result.hit === 'void' ? (
                                  <span className="text-sm text-yellow-600 font-semibold">Did not play</span>
                                ) : result.actual_result !== null ? (
                                  <div>
                                    <span className="text-sm font-semibold text-gray-900">{result.actual_result}</span>
                                    {diff !== null && (
                                      <span className={`text-xs ml-2 ${diffColor}`}>
                                        ({diff > 0 ? '+' : ''}{diff.toFixed(1)})
                                      </span>
                                    )}
                                  </div>
                                ) : (
                                  <span className="text-sm text-gray-400">N/A</span>
                                )}
                              </td>
                              <td className="px-6 py-4 whitespace-nowrap">
                                {getHitBadge(result.hit)}
                              </td>
                              <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                                {result.probability !== null ? `${(result.probability * 100).toFixed(1)}%` : 'N/A'}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              );
            });
          })()
        )}
      </div>
      ) : (
        <div className="space-y-6">
          {parlayResults.length === 0 ? (
            <div className="bg-white rounded-lg shadow-md p-8 text-center">
              <p className="text-gray-500">
                No parlay results found. Try adjusting filters or evaluating finished games.
              </p>
            </div>
          ) : (
            (() => {
              // Filter parlays by type
              let filteredParlays = parlayResults;
              if (parlayTypeFilter !== 'all') {
                filteredParlays = parlayResults.filter((parlay) => {
                  const parlayType = (parlay as any).parlay_type || '';
                  if (parlayTypeFilter === 'safe_long') {
                    return parlayType === 'safe_long';
                  } else if (parlayTypeFilter === 'builder') {
                    return parlayType === 'builder';
                  } else if (parlayTypeFilter === 'suggested') {
                    return parlayType === 'suggested';
                  } else if (parlayTypeFilter === 'combo') {
                    // Check if any leg has a combo stat type (points_rebounds, points_assists, rebounds_assists)
                    return parlay.plays.some((play) => 
                      play.stat_type === 'points_rebounds' ||
                      play.stat_type === 'points_assists' ||
                      play.stat_type === 'rebounds_assists' ||
                      play.stat_type.includes('_') ||
                      (play.bet_line && play.bet_line.toLowerCase().includes('combo'))
                    );
                  }
                  return true;
                });
              }
              
              if (filteredParlays.length === 0) {
                return (
                  <div className="bg-white rounded-lg shadow-md p-8 text-center">
                    <p className="text-gray-500">
                      No {parlayTypeFilter !== 'all' ? parlayTypeFilter.replace('_', ' ') : ''} parlay results found for the selected filters.
                    </p>
                  </div>
                );
              }
              
              return filteredParlays.map((parlay) => {
                const statusColor = parlay.status === 'hit' ? 'text-green-600' : 
                                   parlay.status === 'miss' ? 'text-red-600' : 'text-gray-600';
                const statusBg = parlay.status === 'hit' ? 'bg-green-50 border-green-200' : 
                                parlay.status === 'miss' ? 'bg-red-50 border-red-200' : 'bg-gray-50 border-gray-200';
                
                const parlayType = (parlay as any).type || 'saved';
                const parlayTypeName = (parlay as any).parlay_type || '';
                const isSuggested = parlayType === 'suggested';
                const isCollapsed = collapsedParlays.has(parlay.parlay_id);
              
              const toggleCollapse = () => {
                const newCollapsed = new Set(collapsedParlays);
                if (isCollapsed) {
                  newCollapsed.delete(parlay.parlay_id);
                } else {
                  newCollapsed.add(parlay.parlay_id);
                }
                setCollapsedParlays(newCollapsed);
              };
              
              return (
                <div key={parlay.parlay_id} className="bg-white rounded-lg shadow-md overflow-hidden">
                  <div className={`px-6 py-4 border-b-2 ${statusBg}`}>
                    <div className="flex justify-between items-center">
                      <div className="flex-1">
                        <div className="flex items-center gap-2">
                          <button
                            onClick={toggleCollapse}
                            className="text-gray-500 hover:text-gray-700 focus:outline-none transition-transform"
                            aria-label={isCollapsed ? 'Expand parlay' : 'Collapse parlay'}
                          >
                            <svg
                              className={`w-5 h-5 transition-transform ${isCollapsed ? '' : 'rotate-180'}`}
                              fill="none"
                              stroke="currentColor"
                              viewBox="0 0 24 24"
                            >
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                            </svg>
                          </button>
                          <h3 className="text-lg font-semibold text-gray-900">
                            {parlay.name || `Parlay #${parlay.parlay_id}`}
                          </h3>
                          {isSuggested && (
                            <span className="px-2 py-1 text-xs font-semibold bg-blue-100 text-blue-800 rounded">
                              {parlayTypeName || 'SUGGESTED'}
                            </span>
                          )}
                        </div>
                        <p className="text-sm text-gray-600 mt-1">
                          {parlay.created_at ? formatDateDisplay(parseDateString(parlay.created_at)) : 'Unknown date'}
                        </p>
                      </div>
                      <div className="text-right">
                        <div className={`text-lg font-semibold ${statusColor} mb-1`}>
                          {parlay.status.toUpperCase()}
                        </div>
                        <div className="text-sm text-gray-600">
                          {parlay.legs_hit} / {parlay.total_legs} legs hit
                        </div>
                        {parlay.total_odds && (
                          <div className="text-xs text-gray-500 mt-1">
                            Odds: {parlay.total_odds > 0 ? '+' : ''}{parlay.total_odds?.toFixed(0)}
                          </div>
                        )}
                        {parlay.total_probability && (
                          <div className="text-xs text-gray-500">
                            Probability: {(parlay.total_probability * 100).toFixed(1)}%
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                  
                  {!isCollapsed && (
                    <div className="px-6 py-4">
                      <h4 className="text-sm font-semibold text-gray-700 mb-3">Legs:</h4>
                      <div className="space-y-2">
                        {parlay.plays.map((play, idx) => {
                          const playStatusColor = play.status === 'hit' ? 'text-green-600' : 
                                                 play.status === 'miss' ? 'text-red-600' : 
                                                 play.status === 'void' ? 'text-yellow-600' : 
                                                 'text-gray-500';
                          return (
                            <div key={play.play_id || idx} className="flex items-center justify-between py-2 border-b border-gray-100 last:border-0">
                              <div className="flex-1">
                                <div className="text-sm font-medium text-gray-900">
                                  {idx + 1}. {play.player_name} - {play.stat_type} {play.bet_line}
                                </div>
                                {play.game_date && (
                                  <div className="text-xs text-gray-500 mt-1">
                                    {formatDateDisplay(parseDateString(play.game_date))}
                                  </div>
                                )}
                                {play.status === 'void' && (
                                  <div className="text-xs text-yellow-600 mt-1 italic">
                                    Player did not play - leg voided
                                  </div>
                                )}
                              </div>
                              <div className="text-right">
                                <div className={`text-sm font-semibold ${playStatusColor}`}>
                                  {play.status.toUpperCase()}
                                </div>
                                {play.actual_result !== null && (
                                  <div className="text-xs text-gray-500 mt-1">
                                    Actual: {play.actual_result}
                                  </div>
                                )}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </div>
              );
            });
            })()
          )}
        </div>
      )}
    </div>
  );
}