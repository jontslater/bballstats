import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { format } from 'date-fns';
import apiService, { Game, Prediction } from '../services/api';
import CreatePlayModal from '../components/CreatePlayModal';
import GenerationProgress from '../components/GenerationProgress';
import ParlayBuilder from '../components/ParlayBuilder';
import Last3Games from '../components/Last3Games';
import { parseDateString } from '../utils/dateUtils';
import { useSport } from '../contexts/SportContext';

// Helper function to extract hot/cold streak info
const getStreakInfo = (reasoning: string) => {
  if (!reasoning) return null;

  const parts = reasoning.split(' | ');
  for (const part of parts) {
    if (part.includes('Hot streak')) {
      return { type: 'hot', text: part };
    }
    if (part.includes('Cold streak')) {
      return { type: 'cold', text: part };
    }
  }
  return null;
};

// Helper function to render reasoning with highlights
const renderReasoningWithHighlights = (reasoning: string) => {
  if (!reasoning) return null;

  return (
    <div className="text-xs text-gray-500 mt-1">
      {reasoning.split(' | ').map((part, idx) => {
        const isMatchupAdvantage = part.includes('Strong history vs opponent');
        const isMatchupDisadvantage = part.includes('Weak history vs opponent');
        const isHotStreak = part.includes('Hot streak');
        const isColdStreak = part.includes('Cold streak');

        return (
          <span key={idx}>
            {idx > 0 && ' | '}
            {isMatchupAdvantage && (
              <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-semibold bg-green-100 text-green-800 mr-1 border border-green-200">
                🔥 Hot vs Opp
              </span>
            )}
            {isMatchupDisadvantage && (
              <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-semibold bg-red-100 text-red-800 mr-1 border border-red-200">
                ❄️ Cold vs Opp
              </span>
            )}
            {isHotStreak && (
              <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-semibold bg-orange-100 text-orange-800 mr-1 border border-orange-200">
                🔥 HOT STREAK
              </span>
            )}
            {isColdStreak && (
              <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-semibold bg-blue-100 text-blue-800 mr-1 border border-blue-200">
                ❄️ COLD STREAK
              </span>
            )}
            {part}
          </span>
        );
      })}
    </div>
  );
};

// Helper function to render over/under options
const renderOverUnderOptions = (prediction: any, betType: string) => {
  if (!prediction) return null;

  const line = betType === 'safe' ? prediction.safe_line :
              betType === 'standard' ? prediction.standard_line :
              prediction.long_shot_line;

  const overProb = betType === 'safe' ? prediction.safe_probability :
                  betType === 'standard' ? prediction.standard_probability :
                  prediction.long_shot_probability;

  const underProb = betType === 'safe' ? prediction.safe_under_probability :
                  betType === 'standard' ? prediction.standard_under_probability :
                  prediction.long_shot_under_probability;

  if (!line || overProb === undefined) return null;

  // If under probability is not available, show the over option only
  if (underProb === undefined || underProb === null) {
    return (
      <div className="space-y-1">
        <div className="flex justify-between items-center p-1 rounded text-xs bg-gray-50">
          <span className="font-medium">Over {line.toFixed(1)}</span>
          <span className="font-semibold text-gray-600">
            {(overProb * 100).toFixed(0)}%
          </span>
        </div>
      </div>
    );
  }

  const overBetter = overProb > underProb;
  const underBetter = underProb > overProb;

  return (
    <div className="space-y-1">
      <div className={`flex justify-between items-center p-1 rounded text-xs ${
        overBetter ? 'bg-green-100 border border-green-200' : 'bg-gray-50'
      }`}>
        <span className="font-medium">Over {line.toFixed(1)}</span>
        <span className={`font-semibold ${overBetter ? 'text-green-700' : 'text-gray-600'}`}>
          {overProb ? (overProb * 100).toFixed(0) : 'N/A'}%
          {overBetter && <span className="ml-1 text-green-600">★</span>}
        </span>
      </div>
      <div className={`flex justify-between items-center p-1 rounded text-xs ${
        underBetter ? 'bg-blue-100 border border-blue-200' : 'bg-gray-50'
      }`}>
        <span className="font-medium">Under {line.toFixed(1)}</span>
        <span className={`font-semibold ${underBetter ? 'text-blue-700' : 'text-gray-600'}`}>
          {underProb ? (underProb * 100).toFixed(0) : 'N/A'}%
          {underBetter && <span className="ml-1 text-blue-600">★</span>}
        </span>
      </div>
    </div>
  );
};

export default function GameDetail() {
  const { sport } = useSport();
  const { gameId } = useParams<{ gameId: string }>();
  const [game, setGame] = useState<Game | null>(null);
  const [safeBets, setSafeBets] = useState<Prediction[]>([]);
  const [longShots, setLongShots] = useState<Prediction[]>([]);
  const [sameGameParlays, setSameGameParlays] = useState<any[]>([]);
  const [advancedBets, setAdvancedBets] = useState<any>({});
  const [loading, setLoading] = useState(true);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [selectedPrediction, setSelectedPrediction] = useState<Prediction | null>(null);
  const [statFilter, setStatFilter] = useState<string>('all');
  const [showAdvancedBets, setShowAdvancedBets] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [generationProgress, setGenerationProgress] = useState<{
    progress: number;
    message: string;
  } | null>(null);
  const [showParlayBuilder, setShowParlayBuilder] = useState(false);

  useEffect(() => {
    if (gameId) {
      loadGameData();
    }
  }, [gameId, statFilter, sport]);

  const loadGameData = async () => {
    if (!gameId) return;
    setLoading(true);
    try {
      const [gameData, predictionsData, sameGameParlaysData, advancedBetsData] = await Promise.allSettled([
        apiService.getGame(Number(gameId), sport),
        apiService.getPredictionsForGame(Number(gameId), statFilter === 'all' ? undefined : statFilter, undefined, sport),
        apiService.getSameGameParlays(Number(gameId), 5, 3, 0.70, sport),
        apiService.getAdvancedBetsForGame(Number(gameId), 5, sport),
      ]);
      
      if (gameData.status === 'fulfilled') {
        setGame(gameData.value as any);
      }
      
      if (predictionsData.status === 'fulfilled') {
        const preds = predictionsData.value;
        
        // Group predictions by player_id + game_id (all stat types and bet types together)
        // Structure: Map<player_id-game_id, { player_info, stats: Map<stat_type, { safe?, standard?, long_shot? }> }>
        const playerGroups = new Map<string, { player_info: any, stats: Map<string, { safe?: Prediction; standard?: Prediction; long_shot?: Prediction }> }>();

        preds.forEach((p: Prediction) => {
          const playerKey = `${p.player_id}-${p.game_id}`;
          if (!playerGroups.has(playerKey)) {
            playerGroups.set(playerKey, {
              player_info: {
                player_id: p.player_id,
                player_name: p.player_name,
                player_team: p.player_team,
                game_id: p.game_id,
                game_date: p.game_date,
                opponent_team_abbreviation: p.opponent_team_abbreviation
              },
              stats: new Map()
            });
          }

          const playerGroup = playerGroups.get(playerKey)!;
          const statMap = playerGroup.stats;

          if (!statMap.has(p.stat_type)) {
            statMap.set(p.stat_type, {});
          }
          const statGroup = statMap.get(p.stat_type)!;

          if (p.bet_type === 'safe') {
            statGroup.safe = p;
          } else if (p.bet_type === 'standard') {
            statGroup.standard = p;
          } else if (p.bet_type === 'long_shot') {
            statGroup.long_shot = p;
          }
        });
        
        // Convert to array of player prediction objects (including all bet types)
        const allPlayerBets: any[] = Array.from(playerGroups.entries()).map(([playerKey, playerData]) => {
          const { player_info, stats: statMap } = playerData;

          // Build stats object with all bet types
          const stats: any = {};
          statMap.forEach((group, statType) => {
            stats[statType] = {
              hasSafe: !!group.safe,
              hasStandard: !!group.standard,
              hasLongShot: !!group.long_shot,
              safePrediction: group.safe,
              standardPrediction: group.standard,
              longShotPrediction: group.long_shot,
            };
          });

          // Get reasoning from any prediction
          const reasoning = (statMap.get('points')?.safe?.reasoning) ||
            (statMap.get('points')?.standard?.reasoning) ||
            (statMap.get('points')?.long_shot?.reasoning) ||
            (statMap.get('rebounds')?.safe?.reasoning) ||
            (statMap.get('rebounds')?.standard?.reasoning) ||
            (statMap.get('assists')?.safe?.reasoning) ||
            (statMap.get('assists')?.standard?.reasoning);

          return {
            ...player_info,
            playerKey,
            stats, // Object with stat_type as keys
            reasoning, // Include reasoning in the grouped object
          };
        }).filter(Boolean);

        setSafeBets(allPlayerBets);

        // Filter long shots to only show those not already included in player cards
        const playerIdsWithCards = new Set(allPlayerBets.map(p => p.player_id));
        const additionalLongShots = preds.filter((p: Prediction) =>
          p.bet_type === 'long_shot' && !playerIdsWithCards.has(p.player_id)
        );
        setLongShots(additionalLongShots);
      }
      
      if (sameGameParlaysData.status === 'fulfilled') {
        setSameGameParlays(sameGameParlaysData.value);
      }
      
      if (advancedBetsData.status === 'fulfilled') {
        setAdvancedBets(advancedBetsData.value);
      }
    } catch (error) {
      console.error('Error loading game data:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleGeneratePredictions = async () => {
    if (!gameId) return;
    setGenerating(true);
    setGenerationProgress({ progress: 0, message: 'Starting prediction generation...' });
    try {
      const result = await apiService.generatePredictions(
        Number(gameId),
        1,
        ['points', 'rebounds', 'assists'],
        (progress) => {
          setGenerationProgress({
            progress: progress.progress || 0,
            message: progress.message || 'Processing...'
          });
        }
      );
      
      setGenerationProgress({ progress: 100, message: 'Complete!' });
      setTimeout(() => {
        setGenerationProgress(null);
        alert(`Predictions generated successfully! Created: ${result.created || 0}, Updated: ${result.updated || 0}`);
        loadGameData(); // Reload to show new predictions
      }, 1000);
    } catch (error: any) {
      console.error('Error generating predictions:', error);
      setGenerationProgress(null);
      alert(`Error generating predictions: ${error.message || 'Check console for details'}`);
    } finally {
      setGenerating(false);
    }
  };

  const handleCreatePlay = (prediction: Prediction) => {
    setSelectedPrediction(prediction);
    setShowCreateModal(true);
  };

  const handleAddToParlay = (prediction: Prediction) => {
    // Dispatch custom event for ParlayBuilder to listen to
    const event = new CustomEvent('addToParlay', { detail: prediction });
    window.dispatchEvent(event);
    // Open parlay builder if not already open
    if (!showParlayBuilder) {
      setShowParlayBuilder(true);
    }
  };

  const handleAddAdvancedBetToParlay = async (bet: any, betType: string) => {
    try {
      // For team totals with selected line, use the line info
      if (betType === 'team_totals' && bet.selected_line) {
        bet = {
          ...bet,
          display: bet.display || `${bet.team_name || 'Team'} Total - Over ${bet.selected_line.line}`,
          probability: bet.selected_line.over_probability,
          bet_line: `Over ${bet.selected_line.line}`
        };
      }

      // Convert advanced bet to UserPlay format and save it
      let playData: any = {
        game_id: bet.game_id || Number(gameId),
        bet_line: bet.bet_line || bet.display || bet.label || '',
        notes: `Advanced bet: ${betType}`
      };

      // Set player_id and stat_type based on bet type
      if (betType === 'combo_props' || betType === 'milestone_props' || betType === 'double_doubles' || betType === 'triple_doubles') {
        if (!bet.player_id) {
          alert('Error: Player ID not found for this bet');
          return;
        }
        playData.player_id = bet.player_id;
        playData.stat_type = bet.stat_type || 'combo'; // Use 'combo' for combo bets
      } else if (betType === 'player_vs_player') {
        // For PvP, we'll use player1 as the primary player
        if (!bet.player1_id) {
          alert('Error: Player IDs not found for this bet');
          return;
        }
        playData.player_id = bet.player1_id;
        playData.stat_type = bet.stat_type || 'points';
        playData.notes = `PvP: ${bet.player1_name} vs ${bet.player2_name} - ${betType}`;
      } else if (betType === 'team_totals') {
        // For team totals, we can't create a UserPlay without a player_id
        // Instead, we'll create a prediction-like object directly for the parlay
        const predictionLike = {
          player_id: 0, // Special ID for team bets
          game_id: bet.game_id || Number(gameId),
          stat_type: bet.stat_type || 'points',
          bet_line: bet.bet_line || bet.display || `Team Total - Over ${bet.selected_line?.line || bet.expected_total?.toFixed(1) || 'N/A'}`,
          player_name: bet.team_name || bet.display || 'Team Total',
          distribution_mean: bet.expected_total || 0,
          safe_probability: bet.selected_line?.over_probability || bet.probability || 0.5,
          bet_type: 'standard',
          advanced_bet_type: betType,
          advanced_bet_data: bet,
          prediction_id: -1 // Special ID to indicate this is an advanced bet
        };

        // Dispatch event to add to parlay
        const event = new CustomEvent('addToParlay', { detail: predictionLike });
        window.dispatchEvent(event);
        
        // Open parlay builder if not already open
        if (!showParlayBuilder) {
          setShowParlayBuilder(true);
        }
        return; // Don't create UserPlay for team totals
      }

      // Create the play for bets with player_id
      const createdPlay = await apiService.createPlay(playData);
      
      // Now add it to parlay builder by creating a prediction-like object
      const predictionLike = {
        player_id: playData.player_id,
        game_id: playData.game_id,
        stat_type: playData.stat_type,
        bet_line: playData.bet_line,
        player_name: bet.player_name || bet.player1_name || 'N/A',
        distribution_mean: bet.expected_total || bet.expected_difference || bet.distribution_mean || 0,
        safe_probability: bet.probability || bet.player1_win_probability || bet.selected_line?.over_probability || 0.5,
        bet_type: bet.bet_type || 'standard',
        // Add bet metadata
        advanced_bet_type: betType,
        advanced_bet_data: bet,
        prediction_id: createdPlay.play_id // Use play_id as prediction_id for advanced bets
      };

      // Dispatch event to add to parlay
      const event = new CustomEvent('addToParlay', { detail: predictionLike });
      window.dispatchEvent(event);
      
      // Open parlay builder if not already open
      if (!showParlayBuilder) {
        setShowParlayBuilder(true);
      }
    } catch (error: any) {
      console.error('Error adding advanced bet to parlay:', error);
      alert(`Error adding bet to parlay: ${error.message || 'Unknown error'}`);
    }
  };

  const handlePlayCreated = () => {
    setShowCreateModal(false);
    setSelectedPrediction(null);
  };

  const copySameGameParlaysToClipboard = () => {
    if (sameGameParlays.length === 0) {
      alert('No same-game parlays to copy');
      return;
    }

    const lines: string[] = [];
    lines.push(`🎯 Same Game Parlays - ${format(parseDateString(game?.game_date || format(new Date(), 'yyyy-MM-dd')), 'MMM d, yyyy')}`);
    lines.push('');

    sameGameParlays.forEach((parlay, idx) => {
      lines.push(`${idx + 1}. ${parlay.num_legs}-Leg Same Game Parlay (${parlay.odds_display})`);
      lines.push(`   Combined Probability: ${(parlay.combined_probability * 100).toFixed(2)}%`);
      lines.push(`   Game Diversity: ${parlay.game_diversity || 'N/A'} matchups`);
      lines.push('');

      parlay.legs.forEach((leg: any, legIdx: number) => {
        const statDisplay = getStatTypeDisplay(leg.stat_type);
        const lineText = leg.line !== null && leg.line !== undefined
          ? `${leg.line > 0 ? 'Over' : 'Under'} ${Math.abs(leg.line)}`
          : 'Line TBD';
        const probText = leg.probability
          ? `${(leg.probability * 100).toFixed(1)}%`
          : 'Prob TBD';

        lines.push(`   ${legIdx + 1}. ${leg.player_name}${leg.player_team ? ` (${leg.player_team})` : ''}: ${statDisplay} ${lineText} (${probText})`);
      });

      lines.push('');
    });

    const text = lines.join('\n');
    navigator.clipboard.writeText(text).then(() => {
      alert('Same game parlays copied to clipboard!');
    }).catch(err => {
      console.error('Failed to copy same game parlays:', err);
      const textArea = document.createElement('textarea');
      textArea.value = text;
      document.body.appendChild(textArea);
      textArea.select();
      try {
        document.execCommand('copy');
        alert('Same game parlays copied to clipboard!');
      } catch (fallbackErr) {
        console.error('Fallback copy failed:', fallbackErr);
        alert('Failed to copy. Please try selecting and copying manually.');
      } finally {
        document.body.removeChild(textArea);
      }
    });
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center h-64">
        <div className="text-gray-500">Loading game details...</div>
      </div>
    );
  }

  if (!game) {
    return (
      <div className="text-center py-12">
        <div className="text-gray-500">Game not found</div>
        <Link to="/games" className="text-primary-600 hover:underline mt-4 inline-block">
          ← Back to Games
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Generation Progress Indicator - Fixed position, visible across tabs */}
      <GenerationProgress progress={generationProgress} />
      
      {/* Header */}
      <div>
        <Link to="/games" className="text-primary-600 hover:underline text-sm mb-2 inline-block">
          ← Back to Games
        </Link>
        <div className="flex justify-between items-start">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">
              {game.away_team_abbreviation} @ {game.home_team_abbreviation}
            </h1>
            <p className="mt-1 text-sm text-gray-500">
              {format(parseDateString(game.game_date), 'MMMM d, yyyy')} • {game.game_status}
            </p>
          </div>
          <button
            onClick={handleGeneratePredictions}
            disabled={generating}
            className="px-4 py-2 bg-primary-600 text-white rounded-md hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {generating ? 'Generating...' : 'Generate Predictions'}
          </button>
        </div>
      </div>

      {/* Stat Filter */}
      <div className="flex gap-2">
        {['all', 'points', 'rebounds', 'assists', 'minutes'].map((stat) => (
          <button
            key={stat}
            onClick={() => setStatFilter(stat)}
            className={`px-4 py-2 rounded-md capitalize ${
              statFilter === stat
                ? 'bg-primary-600 text-white'
                : 'bg-white text-gray-700 hover:bg-gray-100'
            }`}
          >
            {stat}
          </button>
        ))}
      </div>

      {/* Same Game Parlays */}
      {sameGameParlays.length > 0 && (
        <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-2xl font-semibold text-gray-900">
          🎯 Same Game Parlays ({sameGameParlays.length})
        </h2>
        <button
          onClick={copySameGameParlaysToClipboard}
          className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium rounded-lg flex items-center space-x-1"
        >
          <span>📋</span>
          <span>Copy All</span>
        </button>
      </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {sameGameParlays.map((parlay, idx) => (
              <div
                key={idx}
                className="bg-gradient-to-r from-blue-50 to-purple-50 rounded-lg shadow-lg p-6 border-2 border-blue-200"
              >
                <div className="flex justify-between items-start mb-4">
                  <div>
                    <h3 className="text-lg font-bold text-gray-900">
                      {parlay.num_legs}-Leg Same Game Parlay
                    </h3>
                    <div className="text-sm text-gray-600 mt-1">
                      Combined Probability: {(parlay.combined_probability * 100).toFixed(2)}%
                    </div>
                    <div className="text-xs text-gray-500 mt-1">
                      Each leg: {parlay.min_leg_probability ? (parlay.min_leg_probability * 100).toFixed(0) : 'N/A'}%+ likely • 
                      Avg: {parlay.avg_leg_probability ? (parlay.avg_leg_probability * 100).toFixed(0) : 'N/A'}%
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-2xl font-bold text-blue-600">
                      {parlay.odds_display}
                    </div>
                    <div className="text-xs text-gray-500">Odds</div>
                  </div>
                </div>
                <div className="space-y-2">
                  {parlay.legs.map((leg: any, legIdx: number) => (
                    <div key={legIdx} className="bg-white rounded p-3 border border-blue-200">
                      <div className="font-medium text-sm text-gray-900">
                        {leg.player_name}
                        {leg.player_team && (
                          <span className="ml-2 text-xs font-normal text-gray-500">({leg.player_team})</span>
                        )}
                      </div>
                      <div className="text-xs text-gray-600">
                        {leg.stat_type === 'points' ? 'PTS' : leg.stat_type === 'rebounds' ? 'REB' : 'AST'} Over {leg.line} • 
                        <span className="ml-2 text-blue-600 font-semibold">
                          {(leg.probability * 100).toFixed(0)}%
                        </span>
                      </div>
                      <Last3Games last3Games={leg.last_3_games} statType={leg.stat_type} />
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Advanced Bets Toggle */}
      <div className="mb-4">
        <button
          onClick={() => setShowAdvancedBets(!showAdvancedBets)}
          className="px-4 py-2 bg-purple-600 text-white rounded-md hover:bg-purple-700"
        >
          {showAdvancedBets ? 'Hide' : 'Show'} Advanced Bets
        </button>
      </div>

      {/* Advanced Bets Section */}
      {showAdvancedBets && (
        <div className="space-y-6 mb-6">
          {/* Combo Props */}
          {advancedBets.combo_props && advancedBets.combo_props.length > 0 && (
            <div>
              <h2 className="text-2xl font-semibold text-gray-900 mb-4">
                🎯 Combo Props ({advancedBets.combo_props.length})
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {advancedBets.combo_props.slice(0, 9).map((bet: any, idx: number) => (
                  <div key={idx} className="bg-gradient-to-r from-purple-50 to-pink-50 rounded-lg shadow p-4 border border-purple-200 relative">
                    <button
                      onClick={() => handleAddAdvancedBetToParlay(bet, 'combo_props')}
                      className="absolute top-2 right-2 w-8 h-8 bg-purple-600 text-white rounded-full flex items-center justify-center hover:bg-purple-700 text-lg font-bold"
                      title="Add to parlay"
                    >
                      +
                    </button>
                    <div className="font-semibold text-gray-900 pr-8">{bet.display}</div>
                    <div className="text-sm text-gray-600 mt-1">
                      Probability: {(bet.probability * 100).toFixed(1)}%
                    </div>
                    {bet.last_3_games && bet.last_3_games.length > 0 && (
                      <Last3Games 
                        last3Games={bet.last_3_games} 
                        statType={`${bet.stat1}+${bet.stat2}`}
                        isCombo={true}
                      />
                    )}
                    <div className={`text-xs mt-1 px-2 py-1 rounded inline-block ${
                      bet.bet_type === 'safe' ? 'bg-green-100 text-green-800' :
                      bet.bet_type === 'standard' ? 'bg-blue-100 text-blue-800' :
                      'bg-orange-100 text-orange-800'
                    }`}>
                      {bet.bet_type.toUpperCase()}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Double-Doubles */}
          {advancedBets.double_doubles && advancedBets.double_doubles.length > 0 && (
            <div>
              <h2 className="text-2xl font-semibold text-gray-900 mb-4">
                🎯 Double-Doubles ({advancedBets.double_doubles.length})
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {advancedBets.double_doubles.map((bet: any, idx: number) => (
                  <div key={idx} className="bg-gradient-to-r from-purple-50 to-indigo-50 rounded-lg shadow p-4 border border-purple-200 relative">
                    <button
                      onClick={() => handleAddAdvancedBetToParlay(bet, 'double_doubles')}
                      className="absolute top-2 right-2 w-8 h-8 bg-purple-600 text-white rounded-full flex items-center justify-center hover:bg-purple-700 text-lg font-bold"
                      title="Add to parlay"
                    >
                      +
                    </button>
                    <div className="font-semibold text-gray-900 pr-8">{bet.player_name}</div>
                    <div className="text-sm text-gray-600 mt-1">
                      Double-Double: {(bet.probability * 100).toFixed(1)}% likely
                    </div>
                    {bet.last_3_games && bet.last_3_games.length > 0 && (
                      <Last3Games 
                        last3Games={bet.last_3_games} 
                        statType="DD"
                        isCombo={false}
                        isMilestone={true}
                      />
                    )}
                    <div className="text-xs text-gray-500 mt-1">{bet.label}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Triple-Doubles */}
          {advancedBets.triple_doubles && advancedBets.triple_doubles.length > 0 && (
            <div>
              <h2 className="text-2xl font-semibold text-gray-900 mb-4">
                ⭐ Triple-Doubles ({advancedBets.triple_doubles.length})
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {advancedBets.triple_doubles.map((bet: any, idx: number) => (
                  <div key={idx} className="bg-gradient-to-r from-yellow-50 to-amber-50 rounded-lg shadow p-4 border border-yellow-300 relative">
                    <button
                      onClick={() => handleAddAdvancedBetToParlay(bet, 'triple_doubles')}
                      className="absolute top-2 right-2 w-8 h-8 bg-yellow-600 text-white rounded-full flex items-center justify-center hover:bg-yellow-700 text-lg font-bold"
                      title="Add to parlay"
                    >
                      +
                    </button>
                    <div className="font-semibold text-gray-900 pr-8">{bet.player_name}</div>
                    <div className="text-sm text-gray-600 mt-1">
                      Triple-Double: {(bet.probability * 100).toFixed(1)}% likely
                    </div>
                    {bet.last_3_games && bet.last_3_games.length > 0 && (
                      <Last3Games 
                        last3Games={bet.last_3_games} 
                        statType="TD"
                        isCombo={false}
                        isMilestone={true}
                      />
                    )}
                    <div className="text-xs text-gray-500 mt-1">{bet.label}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Milestone Props */}
          {advancedBets.milestone_props && advancedBets.milestone_props.length > 0 && (
            <div>
              <h2 className="text-2xl font-semibold text-gray-900 mb-4">
                🏆 Milestone Props ({advancedBets.milestone_props.length})
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                {advancedBets.milestone_props.slice(0, 12).map((bet: any, idx: number) => (
                  <div key={idx} className="bg-gradient-to-r from-yellow-50 to-orange-50 rounded-lg shadow p-4 border border-yellow-200 relative">
                    <button
                      onClick={() => handleAddAdvancedBetToParlay(bet, 'milestone_props')}
                      className="absolute top-2 right-2 w-8 h-8 bg-yellow-600 text-white rounded-full flex items-center justify-center hover:bg-yellow-700 text-lg font-bold"
                      title="Add to parlay"
                    >
                      +
                    </button>
                    <div className="font-semibold text-gray-900 pr-8">{bet.display}</div>
                    <div className="text-sm text-gray-600 mt-1">
                      {(bet.probability * 100).toFixed(1)}% likely
                    </div>
                    {bet.last_3_games && bet.last_3_games.length > 0 && (
                      <Last3Games 
                        last3Games={bet.last_3_games} 
                        statType={bet.type === 'points_milestone' ? 'points' : bet.type === 'rebounds_milestone' ? 'rebounds' : 'assists'}
                        isCombo={false}
                        isMilestone={true}
                        threshold={bet.milestone}
                      />
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Player vs Player */}
          {advancedBets.player_vs_player && advancedBets.player_vs_player.length > 0 && (
            <div>
              <h2 className="text-2xl font-semibold text-gray-900 mb-4">
                ⚔️ Player vs Player ({advancedBets.player_vs_player.length})
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {advancedBets.player_vs_player.slice(0, 6).map((bet: any, idx: number) => (
                  <div key={idx} className="bg-gradient-to-r from-blue-50 to-cyan-50 rounded-lg shadow p-4 border border-blue-200 relative">
                    <button
                      onClick={() => handleAddAdvancedBetToParlay(bet, 'player_vs_player')}
                      className="absolute top-2 right-2 w-8 h-8 bg-blue-600 text-white rounded-full flex items-center justify-center hover:bg-blue-700 text-lg font-bold"
                      title="Add to parlay"
                    >
                      +
                    </button>
                    <div className="font-semibold text-gray-900 pr-8">{bet.display}</div>
                    <div className="text-sm text-gray-600 mt-2">
                      <div>Expected Difference: {bet.expected_difference > 0 ? '+' : ''}{bet.expected_difference.toFixed(1)}</div>
                      <div className="mt-1">
                        {bet.player1_name} Win: {(bet.player1_win_probability * 100).toFixed(1)}%
                      </div>
                      {bet.player1_win_by_5_probability >= 0.20 && (
                        <div className="text-xs text-blue-600 mt-1">
                          Win by 5+: {(bet.player1_win_by_5_probability * 100).toFixed(1)}%
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Team Totals */}
          {advancedBets.team_totals && advancedBets.team_totals.length > 0 && (
            <div>
              <h2 className="text-2xl font-semibold text-gray-900 mb-4">
                📊 Team Totals ({advancedBets.team_totals.length})
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {advancedBets.team_totals.map((team: any, idx: number) => (
                  <div key={idx} className="bg-gradient-to-r from-green-50 to-emerald-50 rounded-lg shadow p-4 border border-green-200">
                    <div className="font-semibold text-gray-900">{team.display}</div>
                    <div className="text-sm text-gray-600 mt-2">
                      Expected: {team.expected_total.toFixed(1)}
                    </div>
                    {team.last_3_games && team.last_3_games.length > 0 && (
                      <Last3Games 
                        last3Games={team.last_3_games} 
                        statType={team.stat_type}
                        isCombo={false}
                        isTeamTotal={true}
                      />
                    )}
                    <div className="mt-3 space-y-2">
                      {team.lines.slice(0, 5).map((line: any, lineIdx: number) => (
                        <div key={lineIdx} className="flex justify-between items-center text-sm">
                          <span>Over {line.line}:</span>
                          <span className="font-semibold text-green-600">
                            {(line.over_probability * 100).toFixed(1)}% ({line.over_odds})
                          </span>
                          <button
                            onClick={() => handleAddAdvancedBetToParlay({
                              ...team, 
                              selected_line: line, 
                              display: `${team.display || team.team_name || 'Team'} Total - Over ${line.line}`,
                              bet_line: `Over ${line.line}`,
                              probability: line.over_probability
                            }, 'team_totals')}
                            className="ml-2 w-6 h-6 bg-green-600 text-white rounded-full flex items-center justify-center hover:bg-green-700 text-xs font-bold"
                            title="Add this line to parlay"
                          >
                            +
                          </button>
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

      {/* Parlay Builder Button */}
      <div className="mb-4 flex justify-end">
        <button
          onClick={() => setShowParlayBuilder(true)}
          className="px-4 py-2 bg-purple-600 text-white rounded-md hover:bg-purple-700 flex items-center gap-2"
        >
          <span>🎯</span>
          <span>Parlay Builder</span>
        </button>
      </div>

      {/* Safe Bets Section */}
      <div>
        <h2 className="text-2xl font-semibold text-gray-900 mb-4">
          Safe & Standard Bets ({safeBets.length})
        </h2>
        {safeBets.length === 0 ? (
          <div className="bg-white rounded-lg shadow p-8 text-center text-gray-500">
            No safe bets available. Generate predictions to see picks.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {safeBets.map((playerCard: any) => {
              const statTypes = Object.keys(playerCard.stats || {});
              const statLabels: { [key: string]: string } = {
                points: 'PTS',
                rebounds: 'REB',
                assists: 'AST',
              };
              
              return (
                <div key={playerCard.playerKey} className="bg-white rounded-lg shadow p-6 relative">
                  <button
                    onClick={() => handleAddToParlay(playerCard)}
                    className="absolute top-4 right-4 w-8 h-8 bg-purple-600 text-white rounded-full hover:bg-purple-700 flex items-center justify-center text-lg font-bold shadow-md z-[60]"
                    title="Add to parlay"
                  >
                    +
                  </button>
                  <div className="mb-4 pr-10">
                    <div className="font-bold text-lg text-gray-900">{playerCard.player_name}</div>
                    <div className="text-sm text-gray-500">
                      {statTypes.map(st => statLabels[st] || st.toUpperCase()).join(' • ')}
                    </div>
                  </div>
                  
                  <div className="space-y-4 mb-4">
                    {statTypes.map((statType: string) => {
                      const statData = playerCard.stats[statType];
                      const safePred = statData.safePrediction;
                      const standardPred = statData.standardPrediction;
                      const longShotPred = statData.longShotPrediction;
                      const hasSafe = statData.hasSafe;
                      const hasStandard = statData.hasStandard;
                      const hasLongShot = statData.hasLongShot;
                      
                      return (
                        <div key={statType} className="border rounded-lg p-3 bg-gray-50">
                          <div className="font-semibold text-sm text-gray-700 mb-2 uppercase">
                            {statLabels[statType] || statType}
                          </div>
                          <div className="space-y-2">
                            {hasSafe && safePred && (
                              <div className="border-l-4 border-green-500 pl-2 py-1.5 bg-green-50 rounded">
                                <div className="flex justify-between items-center mb-2">
                                  <div className="flex items-center gap-2">
                                    <span className="text-xs font-medium text-green-700">SAFE BET</span>
                                    {(() => {
                                      const streakInfo = getStreakInfo(safePred.reasoning);
                                      if (streakInfo) {
                                        return (
                                          <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium ${
                                            streakInfo.type === 'hot'
                                              ? 'bg-green-200 text-green-900'
                                              : 'bg-red-200 text-red-900'
                                          }`} title={`${streakInfo.type === 'hot' ? 'Hot' : 'Cold'} streak: Player performing ${streakInfo.type === 'hot' ? 'above' : 'below'} average recently`}>
                                            {streakInfo.type === 'hot' ? '🔥' : '❄️'} {streakInfo.type === 'hot' ? 'Hot' : 'Cold'}
                                          </span>
                                        );
                                      }
                                      return null;
                                    })()}
                                  </div>
                                </div>
                                {renderOverUnderOptions(safePred, 'safe')}
                                <Last3Games last3Games={safePred.last_3_games} statType={statType} />
                              </div>
                            )}
                            {hasStandard && standardPred && (
                              <div className="border-l-4 border-blue-500 pl-2 py-1.5 bg-blue-50 rounded">
                                <div className="flex justify-between items-center mb-2">
                                  <div className="flex items-center gap-2">
                                    <span className="text-xs font-medium text-blue-700">STANDARD BET</span>
                                    {(() => {
                                      const streakInfo = getStreakInfo(standardPred.reasoning);
                                      if (streakInfo) {
                                        return (
                                          <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium ${
                                            streakInfo.type === 'hot'
                                              ? 'bg-blue-200 text-blue-900'
                                              : 'bg-red-200 text-red-900'
                                          }`} title={`${streakInfo.type === 'hot' ? 'Hot' : 'Cold'} streak: Player performing ${streakInfo.type === 'hot' ? 'above' : 'below'} average recently`}>
                                            {streakInfo.type === 'hot' ? '🔥' : '❄️'} {streakInfo.type === 'hot' ? 'Hot' : 'Cold'}
                                          </span>
                                        );
                                      }
                                      return null;
                                    })()}
                                  </div>
                                </div>
                                {renderOverUnderOptions(standardPred, 'standard')}
                                <Last3Games last3Games={standardPred.last_3_games} statType={statType} />
                              </div>
                            )}
                            {hasLongShot && longShotPred && (
                              <div className="border-l-4 border-orange-500 pl-2 py-1.5 bg-orange-50 rounded">
                                <div className="flex justify-between items-center mb-2">
                                  <div className="flex items-center gap-2">
                                    <span className="text-xs font-medium text-orange-700">LONG SHOT</span>
                                    {(() => {
                                      const streakInfo = getStreakInfo(longShotPred.reasoning);
                                      if (streakInfo) {
                                        return (
                                          <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium ${
                                            streakInfo.type === 'hot'
                                              ? 'bg-orange-200 text-orange-900'
                                              : 'bg-red-200 text-red-900'
                                          }`} title={`${streakInfo.type === 'hot' ? 'Hot' : 'Cold'} streak: Player performing ${streakInfo.type === 'hot' ? 'above' : 'below'} average recently`}>
                                            {streakInfo.type === 'hot' ? '🔥' : '❄️'} {streakInfo.type === 'hot' ? 'Hot' : 'Cold'}
                                          </span>
                                        );
                                      }
                                      return null;
                                    })()}
                                  </div>
                                </div>
                                {renderOverUnderOptions(longShotPred, 'long_shot')}
                                <Last3Games last3Games={longShotPred.last_3_games} statType={statType} />
                              </div>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                  
                  {/* Show reasoning if available (from any prediction) */}
                  {(playerCard.reasoning || safePred?.reasoning || standardPred?.reasoning) && (
                    <div className="mt-4 pt-4 border-t">
                      <div className="text-xs text-gray-600 font-medium mb-1">Why this prediction:</div>
                      {renderReasoningWithHighlights(playerCard.reasoning || safePred?.reasoning || standardPred?.reasoning)}
                    </div>
                  )}
                  
                  <button
                    onClick={() => handleCreatePlay(playerCard)}
                    className="w-full px-4 py-2 bg-primary-600 text-white rounded-md hover:bg-primary-700 mt-4"
                  >
                    Create Play
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Long Shots Section */}
      <div>
        <h2 className="text-2xl font-semibold text-gray-900 mb-4">
          Long Shots ({longShots.length})
        </h2>
        {longShots.length === 0 ? (
          <div className="bg-white rounded-lg shadow p-8 text-center text-gray-500">
            No long shots available. Generate predictions to see picks.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {longShots.map((prediction) => (
              <div key={prediction.prediction_id} className="bg-white rounded-lg shadow p-6">
                <div className="flex justify-between items-start mb-4">
                  <div>
                    <div className="font-bold text-lg text-gray-900">{prediction.player_name}</div>
                    <div className="text-sm text-gray-500 capitalize">
                      {prediction.stat_type}
                      {prediction.player_team && ` • ${prediction.player_team}`}
                    </div>
                  </div>
                  <span className="px-2 py-1 bg-orange-100 text-orange-800 text-xs rounded-full">
                    Long Shot
                  </span>
                </div>
                <div className="mb-4">
                  <div className="flex justify-between items-center mb-2">
                    <span className="text-xs font-medium text-orange-700">LONG SHOT BET</span>
                    {(() => {
                      const streakInfo = getStreakInfo(prediction.reasoning);
                      if (streakInfo) {
                        return (
                          <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium ${
                            streakInfo.type === 'hot'
                              ? 'bg-orange-200 text-orange-900'
                              : 'bg-red-200 text-red-900'
                          }`} title={`${streakInfo.type === 'hot' ? 'Hot' : 'Cold'} streak: Player performing ${streakInfo.type === 'hot' ? 'above' : 'below'} average recently`}>
                            {streakInfo.type === 'hot' ? '🔥' : '❄️'} {streakInfo.type === 'hot' ? 'Hot' : 'Cold'}
                          </span>
                        );
                      }
                      return null;
                    })()}
                  </div>
                  {renderOverUnderOptions(prediction, 'long_shot')}
                  <div className="flex justify-between text-xs mt-2">
                    <span className="text-gray-600">Expected:</span>
                    <span>{prediction.distribution_mean.toFixed(1)}</span>
                  </div>
                  <Last3Games last3Games={prediction.last_3_games} statType={prediction.stat_type} />
                  {prediction.reasoning && (
                    <div className="mt-2">
                      {renderReasoningWithHighlights(prediction.reasoning)}
                    </div>
                  )}
                </div>
                <button
                  onClick={() => handleCreatePlay(prediction)}
                  className="w-full px-4 py-2 bg-primary-600 text-white rounded-md hover:bg-primary-700"
                >
                  Create Play
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Create Play Modal */}
      {showCreateModal && selectedPrediction && (
        <CreatePlayModal
          prediction={selectedPrediction}
          onClose={() => {
            setShowCreateModal(false);
            setSelectedPrediction(null);
          }}
          onSuccess={handlePlayCreated}
        />
      )}

      {/* Parlay Builder */}
      <ParlayBuilder
        isOpen={showParlayBuilder}
        onClose={() => setShowParlayBuilder(false)}
      />
    </div>
  );
}

