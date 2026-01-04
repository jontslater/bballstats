import { useState, useEffect } from 'react';
import { format } from 'date-fns';
import apiService from '../services/api';

interface PoorMansBetChallenge {
  challenge_id: number;
  name: string;
  start_amount: number;
  target_amount: number;
  days_target: number;
  current_bankroll: number;
  status: 'active' | 'completed' | 'failed';
  start_date: string;
  target_date?: string;
  current_day: number;
  total_bets: number;
  wins: number;
  losses: number;
  notes?: string;
  created_at: string;
  days?: PoorMansBetDay[];
}

interface PoorMansBetDay {
  day_id: number;
  challenge_id: number;
  day_number: number;
  bet_date: string;
  starting_bankroll: number;
  bet_amount: number;
  bet_type: 'single' | 'parlay';
  parlay_id?: number;
  prediction_id?: number;
  status: 'pending' | 'hit' | 'miss' | 'void';
  actual_return?: number;
  ending_bankroll?: number;
  notes?: string;
}

interface BetSuggestion {
  challenge_id: number;
  day_number: number;
  bet_date?: string;
  game_date?: string;
  bet_type: 'single' | 'parlay';
  bet_amount: number;
  expected_return: number;
  combined_probability: number;
  time_slot?: string; // 'early', 'mid', 'late'
  current_bankroll?: number;
  legs: Array<{
    prediction_id: number;
    player_id: number;
    player_name: string;
    player_team?: string;
    game_id: number;
    stat_type: string;
    line: number;
    probability: number;
    confidence_level: string;
    volatility_level: string;
    game_time?: string;
  }>;
  reasoning: string;
}

interface MultipleBetSuggestions {
  multiple: true;
  suggestions: BetSuggestion[];
  challenge_id: number;
  day_number: number;
  game_date: string;
}

export default function PoorMansBet() {
  const [challenges, setChallenges] = useState<PoorMansBetChallenge[]>([]);
  const [selectedChallenge, setSelectedChallenge] = useState<PoorMansBetChallenge | null>(null);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [suggesting, setSuggesting] = useState(false);
  const [betSuggestion, setBetSuggestion] = useState<BetSuggestion | null>(null);
  const [multipleSuggestions, setMultipleSuggestions] = useState<MultipleBetSuggestions | null>(null);
  
  // Create challenge form
  const [formData, setFormData] = useState({
    name: "Poor Man's Bet Challenge",
    start_amount: 5.00,
    days_target: 14,
    target_amount: 5.00 * 200, // 200x growth
  });

  useEffect(() => {
    loadChallenges();
  }, []);

  // Track the challenge ID to avoid infinite loops
  const [selectedChallengeId, setSelectedChallengeId] = useState<number | null>(null);

  useEffect(() => {
    if (selectedChallengeId) {
      loadChallengeDetails(selectedChallengeId);
      loadBetSuggestion(selectedChallengeId);
    }
  }, [selectedChallengeId]);

  const loadChallenges = async () => {
    setLoading(true);
    try {
      const data = await apiService.getPoorMansBetChallenges();
      // Ensure all challenges have required fields
      const challengesWithDefaults = data.map((c: any) => ({
        ...c,
        total_bets: c.total_bets || 0,
        days: c.days || [],
      }));
      setChallenges(challengesWithDefaults);
      if (challengesWithDefaults.length > 0 && !selectedChallengeId) {
        // Load full details for the first challenge
        setSelectedChallengeId(challengesWithDefaults[0].challenge_id);
      }
    } catch (error) {
      console.error('Error loading challenges:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadChallengeDetails = async (challengeId: number) => {
    try {
      const data = await apiService.getPoorMansBetChallenge(challengeId);
      // Ensure days array exists
      const challengeWithDays: PoorMansBetChallenge = {
        ...data,
        days: data.days || [],
      };
      setSelectedChallenge(challengeWithDays);
      // Update challenges list with updated data (but don't update selectedChallengeId to avoid loop)
      setChallenges(prev => prev.map(c => c.challenge_id === challengeId ? challengeWithDays : c));
    } catch (error) {
      console.error('Error loading challenge details:', error);
    }
  };

  const loadBetSuggestion = async (challengeId: number) => {
    setSuggesting(true);
    try {
      const response = await apiService.getPoorMansBetSuggestion(challengeId);
      if (response.available && response.available === true) {
        // Remove 'available' field
        const { available, ...data } = response;
        
        // Check if multiple suggestions
        if (data.multiple && data.suggestions) {
          setMultipleSuggestions(data as MultipleBetSuggestions);
          setBetSuggestion(null);
        } else {
          setMultipleSuggestions(null);
          setBetSuggestion(data as BetSuggestion);
        }
      } else {
        setBetSuggestion(null);
        setMultipleSuggestions(null);
      }
    } catch (error: any) {
      if (error.response?.status === 404) {
        setBetSuggestion(null);
        setMultipleSuggestions(null);
      } else {
        console.error('Error loading bet suggestion:', error);
        setBetSuggestion(null);
        setMultipleSuggestions(null);
      }
    } finally {
      setSuggesting(false);
    }
  };

  const handleCreateChallenge = async () => {
    setCreating(true);
    try {
      const challenge = await apiService.createPoorMansBetChallenge({
        name: formData.name,
        start_amount: formData.start_amount,
        days_target: formData.days_target,
      });
      await loadChallenges();
      // Select the newly created challenge
      setSelectedChallengeId(challenge.challenge_id);
      setFormData({
        name: "Poor Man's Bet Challenge",
        start_amount: 5.00,
        days_target: 14,
        target_amount: 5.00 * 200,
      });
      alert('Challenge created successfully!');
    } catch (error: any) {
      console.error('Error creating challenge:', error);
      alert(error.response?.data?.detail || 'Failed to create challenge');
    } finally {
      setCreating(false);
    }
  };

  const handlePlaceBet = async (suggestion?: BetSuggestion) => {
    const suggestionToUse = suggestion || betSuggestion;
    if (!suggestionToUse || !selectedChallenge) return;
    
    const timeSlotText = suggestionToUse.time_slot ? ` (${suggestionToUse.time_slot} games)` : '';
    if (!confirm(`Place bet of $${suggestionToUse.bet_amount.toFixed(2)} for Day ${suggestionToUse.day_number}${timeSlotText}?`)) {
      return;
    }

    try {
      // Extract prediction IDs from legs
      const predictionIds = suggestionToUse.legs.map(leg => leg.prediction_id);
      
      await apiService.placePoorMansBet({
        challenge_id: suggestionToUse.challenge_id,
        prediction_ids: predictionIds,
        bet_amount: suggestionToUse.bet_amount,
        game_date: suggestionToUse.bet_date,
      });
      alert('Bet placed successfully!');
      if (selectedChallengeId) {
        await loadChallengeDetails(selectedChallengeId);
        await loadBetSuggestion(selectedChallengeId);
      }
    } catch (error: any) {
      console.error('Error placing bet:', error);
      alert(error.response?.data?.detail || 'Failed to place bet');
    }
  };

  const calculateTargetAmount = (start: number) => {
    // Backend calculates 200x growth
    return start * 200;
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center h-64">
        <div className="text-gray-500">Loading...</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Poor Man's Bet Challenge</h1>
          <p className="mt-1 text-sm text-gray-500">Start with $1-$5 and compound it daily</p>
        </div>
      </div>

      {/* Create Challenge Form */}
      <div className="bg-white rounded-lg shadow-md p-6">
        <h2 className="text-xl font-semibold mb-4">Create New Challenge</h2>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
            <input
              type="text"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Start Amount ($)</label>
            <input
              type="number"
              step="0.01"
              min="1"
              max="10"
              value={formData.start_amount}
              onChange={(e) => {
                const val = parseFloat(e.target.value) || 0;
                setFormData({
                  ...formData,
                  start_amount: val,
                  target_amount: calculateTargetAmount(val),
                });
              }}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Days Target</label>
            <input
              type="number"
              min="1"
              max="30"
              value={formData.days_target}
              onChange={(e) => {
                const days = parseInt(e.target.value) || 14;
                setFormData({
                  ...formData,
                  days_target: days,
                  target_amount: calculateTargetAmount(formData.start_amount),
                });
              }}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Target Amount ($)</label>
            <input
              type="number"
              step="0.01"
              value={formData.target_amount.toFixed(2)}
              readOnly
              className="w-full px-3 py-2 border border-gray-300 rounded-md bg-gray-50"
            />
            <p className="text-xs text-gray-500 mt-1">
              {formData.target_amount > 0 ? `${((formData.target_amount / formData.start_amount) * 100).toFixed(0)}% return` : '200x growth'}
            </p>
          </div>
        </div>
        <button
          onClick={handleCreateChallenge}
          disabled={creating}
          className="mt-4 px-6 py-2 bg-primary-600 text-white rounded-md hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {creating ? 'Creating...' : 'Create Challenge'}
        </button>
      </div>

      {/* Challenges List */}
      {challenges.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {challenges.map((challenge) => (
            <div
              key={challenge.challenge_id}
              className={`bg-white rounded-lg shadow-md p-6 transition-all ${
                selectedChallenge?.challenge_id === challenge.challenge_id
                  ? 'ring-2 ring-primary-500 border-primary-500'
                  : 'hover:shadow-lg'
              }`}
            >
              <div className="flex justify-between items-start mb-2">
                <div 
                  onClick={() => setSelectedChallengeId(challenge.challenge_id)}
                  className="flex-1 cursor-pointer"
                >
                  <h3 className="text-lg font-semibold text-gray-900">{challenge.name}</h3>
                </div>
                <div className="flex gap-2 items-start">
                  <span
                    className={`px-2 py-1 rounded text-xs font-medium ${
                      challenge.status === 'active'
                        ? 'bg-green-100 text-green-800'
                        : challenge.status === 'completed'
                        ? 'bg-blue-100 text-blue-800'
                        : 'bg-red-100 text-red-800'
                    }`}
                  >
                    {challenge.status}
                  </span>
                  <button
                    onClick={async (e) => {
                      e.stopPropagation();
                      if (!confirm(`Are you sure you want to delete "${challenge.name}"? This action cannot be undone.`)) {
                        return;
                      }
                      try {
                        await apiService.deletePoorMansBetChallenge(challenge.challenge_id);
                        alert('Challenge deleted successfully');
                        if (selectedChallengeId === challenge.challenge_id) {
                          setSelectedChallengeId(null);
                          setSelectedChallenge(null);
                        }
                        await loadChallenges();
                      } catch (error: any) {
                        console.error('Error deleting challenge:', error);
                        alert(error.response?.data?.detail || 'Failed to delete challenge');
                      }
                    }}
                    className="text-red-600 hover:text-red-800 text-xs"
                    title="Delete challenge"
                  >
                    ✕
                  </button>
                </div>
              </div>
              <div 
                onClick={() => setSelectedChallengeId(challenge.challenge_id)}
                className="space-y-2 text-sm cursor-pointer"
              >
                <div className="flex justify-between">
                  <span className="text-gray-600">Start:</span>
                  <span className="font-medium">${challenge.start_amount.toFixed(2)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">Current:</span>
                  <span className="font-bold text-green-600">${challenge.current_bankroll.toFixed(2)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">Target:</span>
                  <span className="font-medium">${challenge.target_amount.toFixed(2)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">Day:</span>
                  <span className="font-medium">{challenge.current_day} / {challenge.days_target}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">Record:</span>
                  <span className="font-medium">
                    {challenge.wins}W - {challenge.losses}L
                  </span>
                </div>
                <div className="pt-2 border-t">
                  <div className="w-full bg-gray-200 rounded-full h-2">
                    <div
                      className="bg-primary-600 h-2 rounded-full transition-all"
                      style={{
                        width: `${Math.min(100, (challenge.current_bankroll / challenge.target_amount) * 100)}%`,
                      }}
                    />
                  </div>
                  <p className="text-xs text-gray-500 mt-1">
                    {((challenge.current_bankroll / challenge.target_amount) * 100).toFixed(1)}% to target
                  </p>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Selected Challenge Details */}
      {selectedChallenge && (
        <div className="bg-white rounded-lg shadow-md p-6">
          <div className="flex justify-between items-start mb-6">
            <div>
              <h2 className="text-2xl font-bold text-gray-900">{selectedChallenge.name}</h2>
              <p className="text-sm text-gray-500 mt-1">
                Started {format(new Date(selectedChallenge.start_date), 'MMM d, yyyy')} • Day {selectedChallenge.current_day} of {selectedChallenge.days_target}
              </p>
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => loadBetSuggestion(selectedChallenge.challenge_id)}
                disabled={suggesting}
                className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {suggesting ? 'Loading...' : 'Refresh Suggestion'}
              </button>
              <button
                onClick={async () => {
                  if (!confirm(`Are you sure you want to delete "${selectedChallenge.name}"? This action cannot be undone.`)) {
                    return;
                  }
                  try {
                    await apiService.deletePoorMansBetChallenge(selectedChallenge.challenge_id);
                    alert('Challenge deleted successfully');
                    setSelectedChallengeId(null);
                    setSelectedChallenge(null);
                    await loadChallenges();
                  } catch (error: any) {
                    console.error('Error deleting challenge:', error);
                    alert(error.response?.data?.detail || 'Failed to delete challenge');
                  }
                }}
                className="px-4 py-2 bg-red-600 text-white rounded-md hover:bg-red-700"
              >
                Delete Challenge
              </button>
            </div>
          </div>

          {/* Challenge Stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <div className="bg-gray-50 rounded-lg p-4">
              <div className="text-sm text-gray-600">Current Bankroll</div>
              <div className="text-2xl font-bold text-green-600">
                ${selectedChallenge.current_bankroll.toFixed(2)}
              </div>
            </div>
            <div className="bg-gray-50 rounded-lg p-4">
              <div className="text-sm text-gray-600">Target Amount</div>
              <div className="text-2xl font-bold text-gray-900">
                ${selectedChallenge.target_amount.toFixed(2)}
              </div>
            </div>
            <div className="bg-gray-50 rounded-lg p-4">
              <div className="text-sm text-gray-600">Win Rate</div>
              <div className="text-2xl font-bold text-blue-600">
                {selectedChallenge.total_bets > 0
                  ? ((selectedChallenge.wins / selectedChallenge.total_bets) * 100).toFixed(0)
                  : 0}%
              </div>
            </div>
            <div className="bg-gray-50 rounded-lg p-4">
              <div className="text-sm text-gray-600">Total Bets</div>
              <div className="text-2xl font-bold text-gray-900">
                {selectedChallenge.total_bets}
              </div>
            </div>
          </div>

          {/* Bet Suggestions */}
          {multipleSuggestions ? (
            <div className="space-y-4">
              <div className="flex justify-between items-center mb-2">
                <h3 className="text-xl font-bold text-gray-900">
                  Day {multipleSuggestions.day_number} Bet Suggestions
                </h3>
                <p className="text-sm text-gray-600">
                  {format(new Date(multipleSuggestions.game_date), 'MMM d, yyyy')}
                </p>
              </div>
              <p className="text-sm text-gray-600 mb-4">
                Multiple time slots available! Place bets for different game times to maximize your day.
              </p>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {multipleSuggestions.suggestions.map((suggestion, idx) => (
                  <div key={idx} className="border-2 border-green-200 rounded-lg p-6 bg-green-50">
                    <div className="flex justify-between items-start mb-4">
                      <div>
                        <h4 className="text-lg font-bold text-gray-900 capitalize">
                          {suggestion.time_slot} Games
                        </h4>
                        <div className="text-xs text-gray-500 mt-1">
                          {suggestion.reasoning}
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="text-xl font-bold text-green-600">
                          ${suggestion.bet_amount.toFixed(2)}
                        </div>
                        <div className="text-xs text-gray-600">Bet Amount</div>
                      </div>
                    </div>

                    <div className="mb-4">
                      <div className="flex justify-between items-center mb-2">
                        <span className="text-xs font-medium text-gray-700">Expected Return:</span>
                        <span className="text-md font-bold text-green-600">
                          ${suggestion.expected_return.toFixed(2)}
                        </span>
                      </div>
                      <div className="flex justify-between items-center mb-2">
                        <span className="text-xs font-medium text-gray-700">Probability:</span>
                        <span className="text-md font-bold text-blue-600">
                          {(suggestion.combined_probability * 100).toFixed(1)}%
                        </span>
                      </div>
                    </div>

                    <div className="mb-4">
                      <h5 className="font-semibold text-gray-900 mb-2 text-sm">
                        {suggestion.bet_type === 'parlay' ? 'Parlay' : 'Single'} ({suggestion.legs.length} legs)
                      </h5>
                      <div className="space-y-1 max-h-32 overflow-y-auto">
                        {suggestion.legs.map((leg, legIdx) => (
                          <div key={legIdx} className="bg-white rounded p-2 border border-green-200 text-xs">
                            <div className="font-medium text-gray-900">
                              {leg.player_name}
                              {leg.player_team && (
                                <span className="ml-1 text-gray-500">({leg.player_team})</span>
                              )}
                            </div>
                            <div className="text-gray-600">
                              {leg.stat_type === 'points' ? 'PTS' : leg.stat_type === 'rebounds' ? 'REB' : 'AST'} Over {leg.line.toFixed(1)} • 
                              <span className="ml-1 text-green-600 font-semibold">
                                {(leg.probability * 100).toFixed(0)}%
                              </span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>

                    <button
                      onClick={() => handlePlaceBet(suggestion)}
                      className="w-full px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 font-semibold text-sm"
                    >
                      Place Bet ({suggestion.time_slot})
                    </button>
                  </div>
                ))}
              </div>
            </div>
          ) : betSuggestion ? (
            <div className="border-2 border-green-200 rounded-lg p-6 bg-green-50">
              <div className="flex justify-between items-start mb-4">
                <div>
                  <h3 className="text-xl font-bold text-gray-900">
                    Day {betSuggestion.day_number} Bet Suggestion
                    {betSuggestion.time_slot && (
                      <span className="ml-2 text-sm font-normal text-gray-600 capitalize">
                        ({betSuggestion.time_slot} games)
                      </span>
                    )}
                  </h3>
                  <p className="text-sm text-gray-600 mt-1">
                    {format(new Date(betSuggestion.game_date || betSuggestion.bet_date || new Date()), 'MMM d, yyyy')}
                  </p>
                </div>
                <div className="text-right">
                  <div className="text-2xl font-bold text-green-600">
                    ${betSuggestion.bet_amount.toFixed(2)}
                  </div>
                  <div className="text-sm text-gray-600">Bet Amount</div>
                </div>
              </div>

              <div className="mb-4">
                <div className="flex justify-between items-center mb-2">
                  <span className="text-sm font-medium text-gray-700">Expected Return:</span>
                  <span className="text-lg font-bold text-green-600">
                    ${betSuggestion.expected_return.toFixed(2)}
                  </span>
                </div>
                <div className="flex justify-between items-center mb-2">
                  <span className="text-sm font-medium text-gray-700">Combined Probability:</span>
                  <span className="text-lg font-bold text-blue-600">
                    {(betSuggestion.combined_probability * 100).toFixed(1)}%
                  </span>
                </div>
                <div className="text-sm text-gray-600 mt-2 p-3 bg-white rounded">
                  <strong>Reasoning:</strong> {betSuggestion.reasoning}
                </div>
              </div>

              <div className="mb-4">
                <h4 className="font-semibold text-gray-900 mb-2">
                  {betSuggestion.bet_type === 'parlay' ? 'Parlay Legs' : 'Single Bet'} ({betSuggestion.legs.length})
                </h4>
                <div className="space-y-2">
                  {betSuggestion.legs.map((leg, idx) => (
                    <div key={idx} className="bg-white rounded p-3 border border-green-200">
                      <div className="font-medium text-gray-900">
                        {leg.player_name}
                        {leg.player_team && (
                          <span className="ml-2 text-sm font-normal text-gray-500">({leg.player_team})</span>
                        )}
                      </div>
                      <div className="text-sm text-gray-600">
                        {leg.stat_type === 'points' ? 'PTS' : leg.stat_type === 'rebounds' ? 'REB' : 'AST'} Over {leg.line.toFixed(1)} • 
                        <span className="ml-2 text-green-600 font-semibold">
                          {(leg.probability * 100).toFixed(0)}%
                        </span>
                      </div>
                      <div className="text-xs text-gray-500 mt-1">
                        {leg.confidence_level} confidence • {leg.volatility_level} volatility
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <button
                onClick={() => handlePlaceBet()}
                className="w-full px-6 py-3 bg-green-600 text-white rounded-md hover:bg-green-700 font-semibold text-lg"
              >
                Place Bet
              </button>
            </div>
          ) : (
            <div className="border-2 border-gray-200 rounded-lg p-6 bg-gray-50 text-center">
              <p className="text-gray-600 mb-2">No bet suggestion available</p>
              <p className="text-sm text-gray-500">
                Generate predictions first, then refresh to get a suggestion.
              </p>
            </div>
          )}

          {/* Bet History */}
          {selectedChallenge.days && selectedChallenge.days.length > 0 && (
            <div className="mt-6">
              <h3 className="text-xl font-semibold text-gray-900 mb-4">Bet History</h3>
              <div className="space-y-2">
                {selectedChallenge.days
                  .sort((a, b) => b.day_number - a.day_number)
                  .map((day) => (
                    <div
                      key={day.day_id}
                      className="flex justify-between items-center p-4 bg-gray-50 rounded-lg"
                    >
                      <div>
                        <div className="font-medium text-gray-900">
                          Day {day.day_number} - {format(new Date(day.bet_date), 'MMM d, yyyy')}
                        </div>
                        <div className="text-sm text-gray-600">
                          Bet: ${day.bet_amount.toFixed(2)} • {day.bet_type}
                        </div>
                      </div>
                      <div className="text-right">
                        <span
                          className={`px-3 py-1 rounded text-sm font-medium ${
                            day.status === 'hit'
                              ? 'bg-green-100 text-green-800'
                              : day.status === 'miss'
                              ? 'bg-red-100 text-red-800'
                              : day.status === 'void'
                              ? 'bg-yellow-100 text-yellow-800'
                              : 'bg-gray-100 text-gray-800'
                          }`}
                        >
                          {day.status}
                        </span>
                        {day.ending_bankroll && (
                          <div className="text-sm text-gray-600 mt-1">
                            ${day.ending_bankroll.toFixed(2)}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

