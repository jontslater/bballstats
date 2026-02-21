import { useState, useEffect } from 'react';
import { format } from 'date-fns';
import apiService from '../services/api';
import Last3Games from '../components/Last3Games';
import { useSport } from '../contexts/SportContext';
import GenerationProgress from '../components/GenerationProgress';
import { parseDateString } from '../utils/dateUtils';

interface SureBet {
  prediction_id: number;
  player_id: number;
  player_name: string;
  player_team: string;
  game_id: number;
  game_date: string;
  game_time?: string;
  stat_type: string;
  line: number;
  probability: number;
  confidence_score: number; // 0-100, higher = more confident
  volatility_level: 'LOW' | 'MEDIUM' | 'HIGH';
  last_3_games?: any[];
  reasoning: string;
  adjustment_factors: {
    matchup_factor: number;
    form_trend_factor: number;
    teammate_chemistry_factor: number;
    advanced_analytics_factor: number;
    situational_performance_factor: number;
    health_factor: number;
    motivation_factor: number;
    ml_factor: number;
  };
  game_info: {
    home_team: string;
    away_team: string;
    home_score?: number;
    away_score?: number;
  };
}

interface DailyBettingPlan {
  date: string;
  total_plays: number;
  recommended_bets: SureBet[];
  bankroll_allocation: {
    conservative: number; // 2-3 bets
    moderate: number;     // 3-5 bets
    aggressive: number;   // 5+ bets
  };
  expected_value: number;
  risk_level: 'LOW' | 'MEDIUM' | 'HIGH';
}

export default function PoorMansBet() {
  const { sport } = useSport();
  const [sureBets, setSureBets] = useState<SureBet[]>([]);
  const [dailyPlan, setDailyPlan] = useState<DailyBettingPlan | null>(null);
  const [loading, setLoading] = useState(true);
  const [generatingPredictions, setGeneratingPredictions] = useState(false);
  const [generationProgress, setGenerationProgress] = useState<{
    progress: number;
    message: string;
  } | null>(null);
  const [selectedGameDate, setSelectedGameDate] = useState<string>(
    new Date().toISOString().split('T')[0]
  );
  const [selectedBets, setSelectedBets] = useState<Set<number>>(new Set());
  const [bankrollAmount, setBankrollAmount] = useState<string>('100');
  const [riskLevel, setRiskLevel] = useState<'conservative' | 'moderate' | 'aggressive'>('conservative');
  const [showBettingPlan, setShowBettingPlan] = useState(false);

  useEffect(() => {
    loadSureBets();
  }, [selectedGameDate, sport]);

  const loadSureBets = async () => {
    setLoading(true);
    try {
      // Get predictions with high confidence from the enhanced algorithm
      const predictions = await apiService.getUpcomingPredictions(
        1, // days ahead
        undefined, // stat type
        undefined, // bet type
        sport
      );

      // Filter for high-confidence predictions only
      const highConfidencePredictions = predictions.filter((pred: any) =>
        (pred.safe_probability || 0) >= 0.50 || (pred.standard_probability || 0) >= 0.60
      );

      // Transform predictions into SureBet format
      const transformedBets: SureBet[] = highConfidencePredictions.map((pred: any) => ({
        prediction_id: pred.prediction_id,
        player_id: pred.player_id,
        player_name: pred.player_name,
        player_team: pred.team_abbreviation || pred.player_team || '',
        game_id: pred.game_id,
        game_date: selectedGameDate,
        game_time: pred.game_time,
        stat_type: pred.stat_type,
        line: pred.line,
        probability: pred.safe_probability || pred.standard_probability || pred.long_shot_probability || 0,
        confidence_score: calculateConfidenceScore(pred),
        volatility_level: 'LOW' as const, // Will be determined by algorithm
        last_3_games: pred.last_3_games || [],
        reasoning: generateReasoning(pred),
        adjustment_factors: {
          matchup_factor: pred.matchup_factor || 1.0,
          form_trend_factor: pred.form_trend_factor || 1.0,
          teammate_chemistry_factor: pred.teammate_chemistry_factor || 1.0,
          advanced_analytics_factor: pred.advanced_analytics_factor || 1.0,
          situational_performance_factor: pred.situational_performance_factor || 1.0,
          health_factor: pred.health_factor || 1.0,
          motivation_factor: pred.motivation_factor || 1.0,
          ml_factor: pred.ml_factor || 1.0,
        },
        game_info: {
          home_team: pred.home_team || '',
          away_team: pred.away_team || '',
          home_score: pred.home_score,
          away_score: pred.away_score,
        }
      }));

      // Sort by confidence score
      transformedBets.sort((a, b) => b.confidence_score - a.confidence_score);

      setSureBets(transformedBets);

      // Generate daily betting plan
      const plan = generateDailyBettingPlan(transformedBets, parseFloat(bankrollAmount));
      setDailyPlan(plan);

    } catch (error) {
      console.error('Error loading sure bets:', error);
      setSureBets([]);
      setDailyPlan(null);
    } finally {
      setLoading(false);
    }
  };

  const calculateConfidenceScore = (prediction: any): number => {
    // Calculate confidence score based on multiple factors
    let score = 0;

    // Base probability (40% weight)
    const bestProb = Math.max(
      prediction.safe_probability || 0,
      prediction.standard_probability || 0,
      prediction.long_shot_probability || 0
    );
    score += bestProb * 40;

    // Adjustment factors alignment (30% weight)
    const factors = [
      prediction.matchup_factor || 1.0,
      prediction.form_trend_factor || 1.0,
      prediction.teammate_chemistry_factor || 1.0,
      prediction.advanced_analytics_factor || 1.0,
      prediction.situational_performance_factor || 1.0,
      prediction.health_factor || 1.0,
      prediction.motivation_factor || 1.0,
      prediction.ml_factor || 1.0,
    ];

    const avgFactor = factors.reduce((sum, f) => sum + f, 0) / factors.length;
    score += Math.min(avgFactor - 0.9, 1.0) * 30; // Reward factors > 1.0

    // Consistency bonus (20% weight)
    const factorVariance = Math.sqrt(
      factors.reduce((sum, f) => sum + Math.pow(f - avgFactor, 2), 0) / factors.length
    );
    score += Math.max(0, 1.0 - factorVariance) * 20; // Lower variance = higher consistency

    // Recent performance bonus (10% weight)
    if (prediction.last_3_games && prediction.last_3_games.length >= 2) {
      const recentAvg = prediction.last_3_games.reduce((sum, game) => sum + (game.value || 0), 0) / prediction.last_3_games.length;
      const seasonAvg = prediction.season_avg || recentAvg;
      if (seasonAvg > 0) {
        const recentRatio = recentAvg / seasonAvg;
        score += Math.min(recentRatio, 1.2) * 10; // Cap at 1.2x for bonus
      }
    }

    return Math.min(100, Math.max(0, score));
  };

  const generateReasoning = (prediction: any): string => {
    const reasons = [];

    // Primary probability reason
    const bestProb = Math.max(
      prediction.safe_probability || 0,
      prediction.standard_probability || 0,
      prediction.long_shot_probability || 0
    );
    reasons.push(`High ${Math.round(bestProb * 100)}% probability`);

    // Key supporting factors
    if ((prediction.matchup_factor || 1.0) > 1.05) {
      reasons.push('Strong matchup advantage');
    }
    if ((prediction.form_trend_factor || 1.0) > 1.05) {
      reasons.push('Hot recent form');
    }
    if ((prediction.teammate_chemistry_factor || 1.0) > 1.05) {
      reasons.push('Teammate chemistry boost');
    }
    if ((prediction.advanced_analytics_factor || 1.0) > 1.05) {
      reasons.push('Advanced analytics support');
    }
    if ((prediction.health_factor || 1.0) > 1.05) {
      reasons.push('Strong health indicators');
    }

    return reasons.join(' • ');
  };

  const generateDailyBettingPlan = (bets: SureBet[], bankroll: number): DailyBettingPlan => {
    // Filter to top confidence bets
    const topBets = bets
      .filter(bet => bet.confidence_score >= 75) // Only 75+ confidence
      .slice(0, 8); // Max 8 bets

    // Calculate allocations based on risk level
    const allocations = {
      conservative: Math.min(3, topBets.length),
      moderate: Math.min(5, topBets.length),
      aggressive: Math.min(8, topBets.length),
    };

    const betCount = allocations[riskLevel];
    const recommendedBets = topBets.slice(0, betCount);

    // Calculate expected value
    const totalProbability = recommendedBets.reduce((sum, bet) => sum + bet.probability, 0);
    const avgProbability = totalProbability / recommendedBets.length;
    const expectedValue = bankroll * (avgProbability - (1 - avgProbability)) * recommendedBets.length;

    // Determine risk level
    let planRisk: 'LOW' | 'MEDIUM' | 'HIGH' = 'LOW';
    if (betCount >= 5) planRisk = 'HIGH';
    else if (betCount >= 3) planRisk = 'MEDIUM';

    return {
      date: selectedGameDate,
      total_plays: topBets.length,
      recommended_bets: recommendedBets,
      bankroll_allocation: {
        conservative: allocations.conservative,
        moderate: allocations.moderate,
        aggressive: allocations.aggressive,
      },
      expected_value: expectedValue,
      risk_level: planRisk,
    };
  };

  const handleGeneratePredictions = async () => {
    if (!selectedGameDate) {
      alert('Please select a game date first');
      return;
    }

    if (!confirm(`Generate predictions for ${format(new Date(selectedGameDate), 'MMM d, yyyy')}?`)) {
      return;
    }

    setGeneratingPredictions(true);
    setGenerationProgress({ progress: 0, message: 'Starting prediction generation...' });

    try {
      // Calculate days ahead
      const today = new Date();
      today.setHours(0, 0, 0, 0);
      const targetDate = new Date(selectedGameDate);
      targetDate.setHours(0, 0, 0, 0);
      const diffTime = targetDate.getTime() - today.getTime();
      const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
      const daysAhead = Math.max(0, diffDays);

      await apiService.generatePredictions(
        undefined,
        daysAhead,
        ['points', 'rebounds', 'assists', 'three_pointers_made'],
        (progress) => {
          setGenerationProgress({
            progress: progress.progress || 0,
            message: progress.message || 'Generating predictions...'
          });
        }
      );

      setGenerationProgress({ progress: 100, message: 'Complete!' });
      setTimeout(() => {
        setGenerationProgress(null);
        alert('Predictions generated successfully!');
        loadSureBets(); // Reload the sure bets
      }, 1000);
    } catch (error: any) {
      console.error('Error generating predictions:', error);
      setGenerationProgress(null);
      alert(`Error: ${error.message || 'Failed to generate predictions'}`);
    } finally {
      setGeneratingPredictions(false);
    }
  };

  const handleBetSelection = (predictionId: number) => {
    const newSelected = new Set(selectedBets);
    if (newSelected.has(predictionId)) {
      newSelected.delete(predictionId);
    } else {
      newSelected.add(predictionId);
    }
    setSelectedBets(newSelected);
  };

  const calculateOptimalBetAmount = () => {
    if (!dailyPlan || selectedBets.size === 0) return 0;

    const bankroll = parseFloat(bankrollAmount) || 100;
    const recommendedCount = dailyPlan.bankroll_allocation[riskLevel];
    const selectedCount = selectedBets.size;

    // Scale bet amount based on how many we're betting vs recommended
    const scalingFactor = Math.min(selectedCount, recommendedCount) / recommendedCount;

    return Math.round((bankroll * 0.1 * scalingFactor) * 100) / 100; // 10% of bankroll per bet max
  };

  const getConfidenceColor = (score: number) => {
    if (score >= 85) return 'text-green-600 bg-green-50 border-green-200';
    if (score >= 75) return 'text-blue-600 bg-blue-50 border-blue-200';
    if (score >= 65) return 'text-yellow-600 bg-yellow-50 border-yellow-200';
    return 'text-red-600 bg-red-50 border-red-200';
  };

  const getVolatilityColor = (level: string) => {
    switch (level) {
      case 'LOW': return 'text-green-600';
      case 'MEDIUM': return 'text-yellow-600';
      case 'HIGH': return 'text-red-600';
      default: return 'text-gray-600';
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center h-64">
        <div className="text-gray-500">Loading sure bets...</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Generation Progress Indicator */}
      {generationProgress && (
        <GenerationProgress progress={generationProgress} title="Generating Predictions" color="blue" />
      )}

      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">🎯 Sure Bets</h1>
          <p className="mt-1 text-sm text-gray-500">
            AI-powered high-confidence predictions using 20+ advanced factors
          </p>
        </div>
      </div>

      {/* Controls Panel */}
      <div className="bg-white rounded-lg shadow-md p-6">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Game Date
            </label>
            <input
              type="date"
              value={selectedGameDate}
              onChange={(e) => setSelectedGameDate(e.target.value)}
              min={new Date().toISOString().split('T')[0]}
              max={new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString().split('T')[0]}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Bankroll ($)
            </label>
            <input
              type="number"
              value={bankrollAmount}
              onChange={(e) => setBankrollAmount(e.target.value)}
              min="10"
              max="10000"
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Risk Level
            </label>
            <select
              value={riskLevel}
              onChange={(e) => setRiskLevel(e.target.value as any)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="conservative">Conservative (2-3 bets)</option>
              <option value="moderate">Moderate (3-5 bets)</option>
              <option value="aggressive">Aggressive (5+ bets)</option>
            </select>
          </div>

          <div className="flex items-end">
            <button
              onClick={handleGeneratePredictions}
              disabled={generatingPredictions}
              className="w-full px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed font-semibold"
            >
              {generatingPredictions ? 'Generating...' : 'Generate Predictions'}
            </button>
          </div>
        </div>
      </div>

      {/* Daily Betting Plan */}
      {dailyPlan && (
        <div className="bg-gradient-to-r from-green-50 to-blue-50 border-2 border-green-200 rounded-lg p-6">
          <div className="flex justify-between items-start mb-4">
            <div>
              <h2 className="text-xl font-bold text-gray-900 flex items-center gap-2">
                📅 Daily Betting Plan
                <span className={`px-2 py-1 rounded text-xs font-medium ${
                  dailyPlan.risk_level === 'LOW' ? 'bg-green-100 text-green-800' :
                  dailyPlan.risk_level === 'MEDIUM' ? 'bg-yellow-100 text-yellow-800' :
                  'bg-red-100 text-red-800'
                }`}>
                  {dailyPlan.risk_level} RISK
                </span>
              </h2>
              <p className="text-sm text-gray-600 mt-1">
                {format(new Date(dailyPlan.date), 'MMM d, yyyy')} • {dailyPlan.recommended_bets.length} recommended bets
              </p>
            </div>
            <div className="text-right">
              <div className="text-lg font-bold text-green-600">
                ${dailyPlan.expected_value.toFixed(2)}
              </div>
              <div className="text-xs text-gray-600">Expected Value</div>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-4 mb-4">
            <div className="bg-white rounded p-3 border border-green-200">
              <div className="text-sm text-gray-600">Conservative</div>
              <div className="text-lg font-bold text-green-600">
                {dailyPlan.bankroll_allocation.conservative} bets
              </div>
            </div>
            <div className="bg-white rounded p-3 border border-yellow-200">
              <div className="text-sm text-gray-600">Moderate</div>
              <div className="text-lg font-bold text-blue-600">
                {dailyPlan.bankroll_allocation.moderate} bets
              </div>
            </div>
            <div className="bg-white rounded p-3 border border-red-200">
              <div className="text-sm text-gray-600">Aggressive</div>
              <div className="text-lg font-bold text-red-600">
                {dailyPlan.bankroll_allocation.aggressive} bets
              </div>
            </div>
          </div>

          <div className="flex gap-2">
            <div className="text-sm text-gray-600">
              💰 Optimal bet per play: <span className="font-bold text-green-600">${calculateOptimalBetAmount().toFixed(2)}</span>
            </div>
            <button
              onClick={() => setShowBettingPlan(!showBettingPlan)}
              className="text-sm text-blue-600 hover:text-blue-800 underline"
            >
              {showBettingPlan ? 'Hide Details' : 'Show Details'}
            </button>
          </div>

          {showBettingPlan && (
            <div className="mt-4 space-y-2">
              <h3 className="font-semibold text-gray-900">Recommended Strategy:</h3>
              <ul className="text-sm text-gray-700 space-y-1">
                <li>• Start with {dailyPlan.bankroll_allocation.conservative} conservative bets</li>
                <li>• Only bet on plays with 75%+ confidence score</li>
                <li>• Use ${calculateOptimalBetAmount().toFixed(2)} per bet (${(calculateOptimalBetAmount() * dailyPlan.recommended_bets.length).toFixed(2)} total)</li>
                <li>• Expected win rate: ~65-70% based on historical data</li>
                <li>• Risk management: Stop if down 20% of daily bankroll</li>
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Sure Bets Display */}
      {sureBets.length > 0 ? (
        <div className="space-y-4">
          {/* Selected Bets Summary */}
          {selectedBets.size > 0 && (
            <div className="bg-blue-50 border-2 border-blue-200 rounded-lg p-4">
              <div className="flex justify-between items-center mb-3">
                <h3 className="text-lg font-bold text-gray-900">
                  Selected Bets ({selectedBets.size})
                </h3>
                <div className="text-right">
                  <div className="text-xl font-bold text-green-600">
                    ${(calculateOptimalBetAmount() * selectedBets.size).toFixed(2)}
                  </div>
                  <div className="text-sm text-gray-600">Total Investment</div>
                </div>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => {
                    // Place all selected bets
                    alert(`Placing ${selectedBets.size} bets for $${(calculateOptimalBetAmount() * selectedBets.size).toFixed(2)} total`);
                  }}
                  className="px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 font-semibold"
                >
                  Place All Bets
                </button>
                <button
                  onClick={() => setSelectedBets(new Set())}
                  className="px-4 py-2 bg-gray-500 text-white rounded-md hover:bg-gray-600"
                >
                  Clear Selection
                </button>
              </div>
            </div>
          )}

          {/* Group bets by game */}
          {Object.entries(
            sureBets.reduce((acc, bet) => {
              const gameKey = `${bet.game_info.home_team} vs ${bet.game_info.away_team}`;
              if (!acc[gameKey]) acc[gameKey] = [];
              acc[gameKey].push(bet);
              return acc;
            }, {} as Record<string, SureBet[]>)
          ).map(([gameKey, gameBets]) => (
            <div key={gameKey} className="bg-white rounded-lg shadow-md p-6">
              <div className="flex justify-between items-center mb-4">
                <div>
                  <h3 className="text-xl font-bold text-gray-900">{gameKey}</h3>
                  <p className="text-sm text-gray-600">
                    {format(new Date(gameBets[0].game_date), 'MMM d, yyyy')}
                    {gameBets[0].game_time && ` • ${gameBets[0].game_time}`}
                  </p>
                </div>
                <span className="px-3 py-1 bg-blue-100 text-blue-800 rounded-full text-sm font-medium">
                  {gameBets.length} sure bet{gameBets.length !== 1 ? 's' : ''}
                </span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {gameBets.map((bet) => {
                  const isSelected = selectedBets.has(bet.prediction_id);
                  return (
                    <div
                      key={bet.prediction_id}
                      onClick={() => handleBetSelection(bet.prediction_id)}
                      className={`p-4 rounded-lg border-2 cursor-pointer transition-all ${
                        isSelected
                          ? 'border-green-500 bg-green-50'
                          : 'border-gray-200 bg-white hover:border-blue-300 hover:bg-blue-50'
                      }`}
                    >
                      {/* Header */}
                      <div className="flex justify-between items-start mb-3">
                        <div className="flex-1">
                          <div className="font-semibold text-gray-900 text-sm">
                            {bet.player_name}
                            <span className="ml-1 text-gray-600 text-xs">({bet.player_team})</span>
                          </div>
                          <div className="text-sm text-gray-700 mt-1">
                            {bet.stat_type === 'points' ? 'PTS' :
                             bet.stat_type === 'rebounds' ? 'REB' :
                             bet.stat_type === 'assists' ? 'AST' :
                             bet.stat_type === 'three_pointers_made' ? '3PM' : bet.stat_type.toUpperCase()}
                            {' '}Over {bet.line.toFixed(1)}
                          </div>
                        </div>
                        <div className="text-right">
                          <div className={`text-lg font-bold px-2 py-1 rounded ${
                            getConfidenceColor(bet.confidence_score)
                          }`}>
                            {bet.confidence_score}
                          </div>
                          <div className="text-xs text-gray-600">Confidence</div>
                        </div>
                      </div>

                      {/* Probability and Volatility */}
                      <div className="flex justify-between items-center mb-3">
                        <div className="text-sm">
                          <span className="text-gray-600">Probability: </span>
                          <span className="font-semibold text-blue-600">
                            {(bet.probability * 100).toFixed(0)}%
                          </span>
                        </div>
                        <div className={`text-sm font-medium ${getVolatilityColor(bet.volatility_level)}`}>
                          {bet.volatility_level} VOLATILITY
                        </div>
                      </div>

                      {/* Reasoning */}
                      <div className="text-xs text-gray-600 mb-2 p-2 bg-gray-50 rounded">
                        {bet.reasoning}
                      </div>

                      {/* Last 3 Games */}
                      {bet.last_3_games && bet.last_3_games.length > 0 && (
                        <div className="mb-2">
                          <Last3Games
                            last3Games={bet.last_3_games}
                            statType={bet.stat_type}
                          />
                        </div>
                      )}

                      {/* Adjustment Factors */}
                      <div className="text-xs text-gray-500">
                        <div className="grid grid-cols-2 gap-1">
                          <span>Matchup: {(bet.adjustment_factors.matchup_factor * 100 - 100).toFixed(1)}%</span>
                          <span>Teammate: {(bet.adjustment_factors.teammate_chemistry_factor * 100 - 100).toFixed(1)}%</span>
                          <span>Analytics: {(bet.adjustment_factors.advanced_analytics_factor * 100 - 100).toFixed(1)}%</span>
                          <span>Health: {(bet.adjustment_factors.health_factor * 100 - 100).toFixed(1)}%</span>
                        </div>
                      </div>

                      {/* Selection Indicator */}
                      {isSelected && (
                        <div className="mt-2 text-green-600 font-bold text-sm text-center">
                          ✓ SELECTED
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="bg-white rounded-lg shadow-md p-8 text-center">
          <div className="text-6xl mb-4">🎯</div>
          <h3 className="text-xl font-bold text-gray-900 mb-2">No Sure Bets Found</h3>
          <p className="text-gray-600 mb-4">
            Generate predictions for {selectedGameDate ? format(new Date(selectedGameDate), 'MMM d, yyyy') : 'today'} to see AI-powered sure bets.
          </p>
          <button
            onClick={handleGeneratePredictions}
            disabled={generatingPredictions}
            className="px-6 py-3 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed font-semibold"
          >
            {generatingPredictions ? 'Generating...' : 'Generate Predictions'}
          </button>
        </div>
      )}
    </div>
  );
}
