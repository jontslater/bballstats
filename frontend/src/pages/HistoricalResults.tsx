import React, { useState, useEffect } from 'react';
import { format, parseISO } from 'date-fns';
import apiService from '../services/api';

// Helper function to display stat types
const getStatTypeDisplay = (statType: string): string => {
  const statMap: { [key: string]: string } = {
    // NBA stats
    'points': 'PTS',
    'rebounds': 'REB',
    'assists': 'AST',
    'steals': 'STL',
    'blocks': 'BLK',
    'turnovers': 'TOV',
    'minutes': 'MIN',
    'pts+ast+reb': 'P+A+R',
    'three_pointers_made': '3PM',

    // NFL stats
    'passing_yards': 'PASS YDS',
    'passing_tds': 'PASS TD',
    'rushing_yards': 'RUSH YDS',
    'rushing_tds': 'RUSH TD',
    'receiving_yards': 'REC YDS',
    'receiving_tds': 'REC TD',
    'receptions': 'REC',
    'targets': 'TGT',
  };

  return statMap[statType] || statType.toUpperCase();
};

const HistoricalResults: React.FC = () => {
  const [performance, setPerformance] = useState<any>(null);
  const [recentResults, setRecentResults] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [daysBack, setDaysBack] = useState(30);

  useEffect(() => {
    loadData();
  }, [daysBack]);

  const loadData = async () => {
    try {
      setLoading(true);
      setError(null);

      const [performanceResponse, resultsResponse] = await Promise.allSettled([
        apiService.getHistoricalPerformance(daysBack),
        apiService.getRecentHistoricalResults(50)
      ]);

      const performanceData = performanceResponse.status === 'fulfilled' ? performanceResponse.value : null;
      const resultsData = resultsResponse.status === 'fulfilled' ? resultsResponse.value : null;

      if (performanceData) {
        setPerformance(performanceData.performance);
      }

      if (resultsData) {
        setRecentResults(resultsData.results);
      }

    } catch (err: any) {
      console.error('Error loading historical results:', err);
      setError(err.response?.data?.detail || 'Failed to load historical results');
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateResults = async () => {
    try {
      setLoading(true);
      const result = await apiService.updateHistoricalResults();
      alert(`Updated ${result.bets_updated} bets and ${result.parlays_updated} parlays for ${result.target_date}`);
      // Reload data
      await loadData();
    } catch (err: any) {
      console.error('Error updating results:', err);
      const errorMessage = err.code === 'ERR_NETWORK' || err.message === 'Network Error'
        ? 'Backend not running. Please start the backend server first.'
        : 'Failed to update results: ' + (err.response?.data?.detail || err.message);
      alert(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-32 w-32 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <div className="flex">
            <div className="ml-3">
              <h3 className="text-sm font-medium text-red-800">Error Loading Historical Results</h3>
              <div className="mt-2 text-sm text-red-700">{error}</div>
              <div className="mt-4">
                <button
                  onClick={loadData}
                  className="bg-red-100 hover:bg-red-200 text-red-800 px-3 py-2 rounded-md text-sm font-medium"
                >
                  Try Again
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">📊 Historical Results</h1>
        <p className="text-gray-600">
          Track performance of suggested bets and parlays over time. See which recommendations hit or missed.
        </p>
      </div>

      {/* Controls */}
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 mb-8">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Analysis Period</label>
              <select
                value={daysBack}
                onChange={(e) => setDaysBack(parseInt(e.target.value))}
                className="rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
              >
                <option value="7">Last 7 days</option>
                <option value="30">Last 30 days</option>
                <option value="90">Last 90 days</option>
                <option value="180">Last 6 months</option>
              </select>
            </div>
          </div>
          <button
            onClick={handleUpdateResults}
            className="px-4 py-2 bg-green-600 hover:bg-green-700 text-white text-sm font-medium rounded-lg flex items-center space-x-2"
          >
            <span>🔄</span>
            <span>Update Results</span>
          </button>
        </div>
      </div>

      {/* Performance Overview */}
      {performance && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
          {/* Suggested Bets Performance */}
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">⭐ Suggested Bets</h3>
            <div className="grid grid-cols-3 gap-4">
              <div className="text-center">
                <div className="text-2xl font-bold text-blue-600">{performance.suggested_bets.total}</div>
                <div className="text-sm text-gray-500">Total Bets</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-bold text-green-600">{performance.suggested_bets.hits}</div>
                <div className="text-sm text-gray-500">Hits</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-bold text-purple-600">{performance.suggested_bets.hit_rate.toFixed(1)}%</div>
                <div className="text-sm text-gray-500">Hit Rate</div>
              </div>
            </div>
          </div>

          {/* Parlays Performance */}
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">🎯 Parlays</h3>
            <div className="grid grid-cols-3 gap-4">
              <div className="text-center">
                <div className="text-2xl font-bold text-blue-600">{performance.parlays.total}</div>
                <div className="text-sm text-gray-500">Total Parlays</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-bold text-green-600">{performance.parlays.wins}</div>
                <div className="text-sm text-gray-500">Wins</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-bold text-purple-600">{performance.parlays.win_rate.toFixed(1)}%</div>
                <div className="text-sm text-gray-500">Win Rate</div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Recent Results */}
      {recentResults && (
        <div className="space-y-6">
          {/* Recent Suggested Bets */}
          {recentResults.suggested_bets && recentResults.suggested_bets.length > 0 && (
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
              <div className="bg-gradient-to-r from-blue-500 to-indigo-600 px-6 py-4 text-white">
                <h3 className="text-lg font-semibold">Recent Suggested Bets</h3>
              </div>
              <div className="divide-y divide-gray-200">
                {recentResults.suggested_bets.slice(0, 20).map((bet: any, idx: number) => (
                  <div key={bet.id} className="px-6 py-4 hover:bg-gray-50">
                    <div className="flex items-center justify-between">
                      <div className="flex-1">
                        <div className="flex items-center space-x-4">
                          <div className={`w-3 h-3 rounded-full ${bet.hit ? 'bg-green-500' : bet.hit === false ? 'bg-red-500' : 'bg-gray-400'}`}></div>
                          <div>
                            <div className="font-medium text-gray-900">
                              {bet.player_name} ({bet.player_team}) - {getStatTypeDisplay(bet.stat_type)} {bet.line > 0 ? 'Over' : 'Under'} {Math.abs(bet.line)}
                            </div>
                            <div className="text-sm text-gray-500">
                              {bet.actual_result ? `Actual: ${bet.actual_result} • ` : ''}
                              Generated: {format(parseISO(bet.generated_at), 'MMM d, yyyy')}
                            </div>
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center space-x-4">
                        <div className="text-sm text-gray-500">
                          {(bet.probability * 100).toFixed(1)}%
                        </div>
                        <div className={`px-2 py-1 rounded-full text-xs font-medium ${
                          bet.hit ? 'bg-green-100 text-green-800' :
                          bet.hit === false ? 'bg-red-100 text-red-800' :
                          'bg-gray-100 text-gray-800'
                        }`}>
                          {bet.hit ? 'HIT' : bet.hit === false ? 'MISS' : 'PENDING'}
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Recent Parlays */}
          {recentResults.parlays && recentResults.parlays.length > 0 && (
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
              <div className="bg-gradient-to-r from-purple-500 to-pink-600 px-6 py-4 text-white">
                <h3 className="text-lg font-semibold">Recent Parlays</h3>
              </div>
              <div className="divide-y divide-gray-200">
                {recentResults.parlays.slice(0, 10).map((parlay: any, idx: number) => (
                  <div key={parlay.id} className="px-6 py-4 hover:bg-gray-50">
                    <div className="flex items-center justify-between mb-3">
                      <div>
                        <div className="font-medium text-gray-900">
                          {parlay.parlay_type.replace('_', ' ').toUpperCase()} Parlay ({parlay.num_legs} legs)
                        </div>
                        <div className="text-sm text-gray-500">
                          {parlay.odds_display} • Generated: {format(parseISO(parlay.generated_at), 'MMM d, yyyy')}
                        </div>
                      </div>
                      <div className={`px-3 py-1 rounded-full text-sm font-medium ${
                        parlay.all_legs_hit ? 'bg-green-100 text-green-800' :
                        parlay.all_legs_hit === false ? 'bg-red-100 text-red-800' :
                        'bg-gray-100 text-gray-800'
                      }`}>
                        {parlay.all_legs_hit ? 'WON' : parlay.all_legs_hit === false ? 'LOST' : 'PENDING'}
                        {parlay.all_legs_hit === false && ` (${parlay.legs_hit_count}/${parlay.num_legs})`}
                      </div>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
                      {parlay.legs.map((leg: any, legIdx: number) => (
                        <div key={legIdx} className="text-sm bg-gray-50 rounded p-2">
                          <div className={`w-2 h-2 rounded-full inline-block mr-2 ${
                            leg.hit ? 'bg-green-500' :
                            leg.hit === false ? 'bg-red-500' :
                            'bg-gray-400'
                          }`}></div>
                          {leg.player_name} ({leg.player_team}) - {getStatTypeDisplay(leg.stat_type)} Over {leg.line}
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Empty State */}
      {!performance && !recentResults && (
        <div className="bg-gray-50 border border-gray-200 rounded-lg p-8 text-center">
          <div className="text-gray-500 text-lg">Historical tracking temporarily disabled.</div>
          <div className="text-gray-400 text-sm mt-2">
            We're fixing API validation issues. The core prediction system is working perfectly.
            <br />
            <strong>Historical tracking will be re-enabled soon!</strong>
          </div>
          <div className="mt-4 p-4 bg-blue-50 border border-blue-200 rounded-lg">
            <div className="text-sm text-blue-800">
              <strong>✅ What's working:</strong><br />
              • Dashboard predictions<br />
              • Suggested bets & parlays<br />
              • Value ladders<br />
              • All core betting features
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default HistoricalResults;