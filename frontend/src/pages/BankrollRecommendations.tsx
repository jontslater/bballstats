import { useState } from 'react';
import { format } from 'date-fns';
import apiService from '../services/api';

interface BetSuggestion {
  bet_type: 'builder' | 'safe_long_parlay' | 'safe_bet';
  amount: number;
  probability?: number;
  expected_roi?: number;
  expected_return: number;
  // Builder/Safe Long Parlay fields
  parlay_legs?: Array<{
    prediction_id: number;
    player_id: number;
    player_name: string;
    player_team?: string;
    game_id: number;
    stat_type: string;
    line: number;
    probability: number;
  }>;
  num_legs?: number;
  combined_probability?: number;
  odds_display?: string;
  // Safe Bet fields
  prediction_id?: number;
  player_id?: number;
  player_name?: string;
  player_team?: string;
  game_id?: number;
  stat_type?: string;
  line?: number;
  bet_line?: string;
}

interface Recommendation {
  strategy: 'poor_mans_bet' | 'builder' | 'safe_long_parlay' | 'safe_bets' | 'mixed';
  priority: number;
  priority_score: number;
  allocation: number;
  reasoning: string;
  challenge_config?: {
    start_amount: number;
    target_amount: number;
    days_target: number;
  };
  suggested_bets: BetSuggestion[];
}

interface RecommendationsResponse {
  available_to_bet: number;
  total_bankroll: number;
  reserve_amount: number;
  risk_tolerance: string;
  game_date: string;
  recommendations: Recommendation[];
}

export default function BankrollRecommendations() {
  const [totalBankroll, setTotalBankroll] = useState<number>(50);
  const [reserveAmount, setReserveAmount] = useState<number>(20);
  const [riskTolerance, setRiskTolerance] = useState<'conservative' | 'moderate' | 'aggressive'>('moderate');
  const [gameDate, setGameDate] = useState<string>(format(new Date(), 'yyyy-MM-dd'));
  const [loading, setLoading] = useState(false);
  const [recommendations, setRecommendations] = useState<RecommendationsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleGetRecommendations = async () => {
    if (totalBankroll <= 0) {
      setError('Total bankroll must be greater than 0');
      return;
    }
    if (reserveAmount < 0) {
      setError('Reserve amount cannot be negative');
      return;
    }
    if (reserveAmount > totalBankroll) {
      setError('Reserve amount cannot exceed total bankroll');
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const data = await apiService.getBankrollRecommendations({
        total_bankroll: totalBankroll,
        reserve_amount: reserveAmount,
        game_date: gameDate,
        risk_tolerance: riskTolerance,
      });
      setRecommendations(data);
    } catch (err: any) {
      console.error('Error getting recommendations:', err);
      setError(err.response?.data?.detail || 'Failed to get recommendations');
    } finally {
      setLoading(false);
    }
  };

  const availableToBet = totalBankroll - reserveAmount;

  return (
    <div className="max-w-6xl mx-auto p-6 space-y-6">
      <div className="bg-white rounded-lg shadow-md p-6">
        <h1 className="text-3xl font-bold text-gray-900 mb-6">Bankroll Recommendations</h1>
        <p className="text-gray-600 mb-6">
          Enter your bankroll information and get personalized betting recommendations with specific plays and dollar allocations.
        </p>

        {/* Input Form */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Total Bankroll ($)
            </label>
            <input
              type="number"
              min="0"
              step="0.01"
              value={totalBankroll}
              onChange={(e) => setTotalBankroll(parseFloat(e.target.value) || 0)}
              className="w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              placeholder="50.00"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Reserve Amount ($)
            </label>
            <input
              type="number"
              min="0"
              step="0.01"
              value={reserveAmount}
              onChange={(e) => setReserveAmount(parseFloat(e.target.value) || 0)}
              className="w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              placeholder="20.00"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Available to Bet
            </label>
            <div className="px-4 py-2 bg-gray-50 border border-gray-300 rounded-md text-lg font-semibold text-green-600">
              ${availableToBet.toFixed(2)}
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Risk Tolerance
            </label>
            <select
              value={riskTolerance}
              onChange={(e) => setRiskTolerance(e.target.value as 'conservative' | 'moderate' | 'aggressive')}
              className="w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            >
              <option value="conservative">Conservative</option>
              <option value="moderate">Moderate</option>
              <option value="aggressive">Aggressive</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Game Date
            </label>
            <input
              type="date"
              value={gameDate}
              onChange={(e) => setGameDate(e.target.value)}
              className="w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>
        </div>

        {error && (
          <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-md text-red-700">
            {error}
          </div>
        )}

        <button
          onClick={handleGetRecommendations}
          disabled={loading || availableToBet <= 0}
          className="w-full md:w-auto px-6 py-3 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed font-semibold"
        >
          {loading ? 'Loading Recommendations...' : 'Get Recommendations'}
        </button>
      </div>

      {/* Recommendations */}
      {recommendations && (
        <div className="space-y-6">
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
            <div className="flex justify-between items-center">
              <div>
                <h2 className="text-xl font-bold text-gray-900">Summary</h2>
                <p className="text-sm text-gray-600 mt-1">
                  Game Date: {format(new Date(recommendations.game_date), 'MMM d, yyyy')} • 
                  Risk: {recommendations.risk_tolerance.charAt(0).toUpperCase() + recommendations.risk_tolerance.slice(1)}
                </p>
              </div>
              <div className="text-right">
                <div className="text-2xl font-bold text-green-600">
                  ${recommendations.available_to_bet.toFixed(2)}
                </div>
                <div className="text-sm text-gray-600">Available to Bet</div>
              </div>
            </div>
          </div>

          {recommendations.recommendations.length === 0 ? (
            <div className="bg-white rounded-lg shadow-md p-8 text-center text-gray-500">
              No recommendations available. Try adjusting your bankroll or risk tolerance.
            </div>
          ) : (
            recommendations.recommendations.map((rec, idx) => (
              <div key={idx} className="bg-white rounded-lg shadow-md p-6 border-2 border-blue-200">
                {/* Recommendation Header */}
                <div className="flex justify-between items-start mb-4">
                  <div>
                    <div className="flex items-center gap-3">
                      <span className="px-3 py-1 bg-blue-600 text-white rounded-full text-sm font-semibold">
                        Option {rec.priority}
                      </span>
                      <span className="px-3 py-1 bg-gray-200 text-gray-700 rounded-full text-sm font-medium capitalize">
                        {rec.strategy.replace('_', ' ')}
                      </span>
                    </div>
                    <h3 className="text-xl font-bold text-gray-900 mt-2">{rec.reasoning}</h3>
                  </div>
                  <div className="text-right">
                    <div className="text-2xl font-bold text-green-600">
                      ${rec.allocation.toFixed(2)}
                    </div>
                    <div className="text-sm text-gray-600">Allocation</div>
                  </div>
                </div>

                {/* Poor Man's Bet Challenge Config */}
                {rec.strategy === 'poor_mans_bet' && rec.challenge_config && (
                  <div className="mb-4 p-4 bg-purple-50 border border-purple-200 rounded-md">
                    <h4 className="font-semibold text-gray-900 mb-2">Challenge Details</h4>
                    <div className="grid grid-cols-3 gap-4 text-sm">
                      <div>
                        <span className="text-gray-600">Start:</span>
                        <span className="ml-2 font-semibold">${rec.challenge_config.start_amount.toFixed(2)}</span>
                      </div>
                      <div>
                        <span className="text-gray-600">Target:</span>
                        <span className="ml-2 font-semibold">${rec.challenge_config.target_amount.toFixed(2)}</span>
                      </div>
                      <div>
                        <span className="text-gray-600">Days:</span>
                        <span className="ml-2 font-semibold">{rec.challenge_config.days_target}</span>
                      </div>
                    </div>
                  </div>
                )}

                {/* Suggested Bets */}
                {rec.suggested_bets.length > 0 && (
                  <div className="mt-4">
                    <h4 className="font-semibold text-gray-900 mb-3">
                      Suggested Bets ({rec.suggested_bets.length})
                    </h4>
                    <div className="space-y-3">
                      {rec.suggested_bets.map((bet, betIdx) => (
                        <div key={betIdx} className="border border-gray-200 rounded-lg p-4 bg-gray-50">
                          <div className="flex justify-between items-start mb-3">
                            <div>
                              <div className="flex items-center gap-2">
                                <span className="px-2 py-1 bg-green-100 text-green-800 rounded text-xs font-medium">
                                  ${bet.amount.toFixed(2)}
                                </span>
                                <span className="px-2 py-1 bg-blue-100 text-blue-800 rounded text-xs font-medium capitalize">
                                  {bet.bet_type.replace('_', ' ')}
                                </span>
                                {bet.combined_probability && (
                                  <span className="px-2 py-1 bg-purple-100 text-purple-800 rounded text-xs font-medium">
                                    {(bet.combined_probability * 100).toFixed(1)}% prob
                                  </span>
                                )}
                                {bet.probability && (
                                  <span className="px-2 py-1 bg-purple-100 text-purple-800 rounded text-xs font-medium">
                                    {(bet.probability * 100).toFixed(1)}% prob
                                  </span>
                                )}
                              </div>
                              <div className="mt-2 text-sm">
                                <span className="text-gray-600">Expected Return:</span>
                                <span className="ml-2 font-semibold text-green-600">
                                  ${bet.expected_return.toFixed(2)}
                                </span>
                                {bet.expected_roi && (
                                  <span className="ml-2 text-gray-500">
                                    ({(bet.expected_roi * 100).toFixed(1)}% ROI)
                                  </span>
                                )}
                              </div>
                            </div>
                          </div>

                          {/* Parlay Legs */}
                          {bet.parlay_legs && bet.parlay_legs.length > 0 && (
                            <div className="mt-3">
                              <div className="text-sm font-medium text-gray-700 mb-2">
                                {bet.num_legs}-Leg Parlay:
                              </div>
                              <div className="space-y-2">
                                {bet.parlay_legs.map((leg, legIdx) => (
                                  <div key={legIdx} className="bg-white rounded p-2 text-sm">
                                    <span className="font-medium text-gray-900">
                                      {leg.player_name}
                                    </span>
                                    {leg.player_team && (
                                      <span className="ml-2 text-gray-500">({leg.player_team})</span>
                                    )}
                                    <span className="ml-2 text-gray-600">
                                      {leg.stat_type === 'points' ? 'PTS' : leg.stat_type === 'rebounds' ? 'REB' : 'AST'} 
                                      Over {leg.line.toFixed(1)}
                                    </span>
                                    <span className="ml-2 text-green-600 font-semibold">
                                      ({(leg.probability * 100).toFixed(0)}%)
                                    </span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          {/* Single Safe Bet */}
                          {bet.bet_type === 'safe_bet' && bet.player_name && (
                            <div className="mt-3 bg-white rounded p-2 text-sm">
                              <span className="font-medium text-gray-900">
                                {bet.player_name}
                              </span>
                              {bet.player_team && (
                                <span className="ml-2 text-gray-500">({bet.player_team})</span>
                              )}
                              <span className="ml-2 text-gray-600">
                                {bet.bet_line || `${bet.stat_type?.toUpperCase()} Over ${bet.line?.toFixed(1)}`}
                              </span>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}

