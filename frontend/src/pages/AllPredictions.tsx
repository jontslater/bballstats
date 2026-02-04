import { useState, useEffect } from 'react';
import { format } from 'date-fns';
import { Link } from 'react-router-dom';
import apiService, { Prediction } from '../services/api';
import { parseDateString } from '../utils/dateUtils';
import Last3Games from '../components/Last3Games';

interface ComboBet {
  player_id: number;
  player_name: string;
  combo_type?: string;
  stat1?: string;
  stat2?: string;
  line?: number;
  probability: number;
  bet_type: string;
  display: string;
  type?: string;
  milestone?: number;
  label?: string;
}

export default function AllPredictions() {
  const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [comboBets, setComboBets] = useState<{ games: any[] } | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedDate, setSelectedDate] = useState(() => {
    // Use a reliable date formatting method
    const today = new Date();
    const year = today.getFullYear();
    const month = String(today.getMonth() + 1).padStart(2, '0');
    const day = String(today.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  });
  const [statFilter, setStatFilter] = useState<string>('all');
  const [betTypeFilter, setBetTypeFilter] = useState<string>('all');
  const [sortBy, setSortBy] = useState<string>('probability'); // probability, mean, player
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');

  useEffect(() => {
    if (statFilter === 'combo') {
      loadComboBets();
    } else {
      loadPredictions();
    }
  }, [selectedDate, statFilter, betTypeFilter]);

  const loadPredictions = async () => {
    setLoading(true);
    setComboBets(null);
    try {
      // Get games for the selected date
      const games = await apiService.getGames(selectedDate);
      
      if (games.length === 0) {
        setPredictions([]);
        setLoading(false);
        return;
      }

      // Create a map of game_id to game info for easy lookup
      const gameMap = new Map<number, any>();
      games.forEach(game => {
        gameMap.set(game.game_id, game);
      });

      // Get predictions for all games in parallel
      const predictionPromises = games.map(game =>
        apiService.getPredictionsForGame(
          game.game_id,
          statFilter === 'all' ? undefined : statFilter,
          betTypeFilter === 'all' ? undefined : betTypeFilter
        ).then(preds => {
          // Enrich predictions with game info
          return preds.map((pred: any) => ({
            ...pred,
            game_date: game.game_date,
            away_team_abbreviation: game.away_team_abbreviation || game.away_team?.abbreviation,
            home_team_abbreviation: game.home_team_abbreviation || game.home_team?.abbreviation,
          }));
        }).catch(error => {
          console.error(`Error loading predictions for game ${game.game_id}:`, error);
          return [];
        })
      );

      const predictionArrays = await Promise.all(predictionPromises);
      const allPredictions = predictionArrays.flat();

      setPredictions(allPredictions);
    } catch (error) {
      console.error('Error loading predictions:', error);
      setPredictions([]);
    } finally {
      setLoading(false);
    }
  };

  const loadComboBets = async () => {
    setLoading(true);
    setPredictions([]);
    try {
      const data = await apiService.getAdvancedBetsForDate(selectedDate, 10);
      setComboBets(data);
    } catch (error) {
      console.error('Error loading combo bets:', error);
      setComboBets(null);
    } finally {
      setLoading(false);
    }
  };

  const getLine = (prediction: Prediction): number => {
    if (prediction.bet_type === 'safe' && prediction.safe_line) {
      return prediction.safe_line;
    } else if (prediction.bet_type === 'standard' && prediction.standard_line) {
      return prediction.standard_line;
    } else if (prediction.bet_type === 'long_shot' && prediction.long_shot_line) {
      return prediction.long_shot_line;
    }
    return prediction.distribution_mean;
  };

  const getProbability = (prediction: Prediction): number => {
    if (prediction.bet_type === 'safe' && prediction.safe_probability) {
      return prediction.safe_probability;
    } else if (prediction.bet_type === 'standard' && prediction.standard_probability) {
      return prediction.standard_probability;
    } else if (prediction.bet_type === 'long_shot' && prediction.long_shot_probability) {
      return prediction.long_shot_probability;
    }
    return 0.5;
  };

  // Group predictions by game first (only if not showing combo bets)
  const predictionsByGame = new Map<number, Prediction[]>();
  if (statFilter !== 'combo') {
    predictions.forEach(pred => {
      if (!predictionsByGame.has(pred.game_id)) {
        predictionsByGame.set(pred.game_id, []);
      }
      predictionsByGame.get(pred.game_id)!.push(pred);
    });
  }

  // Sort predictions within each game (only if not showing combo bets)
  const sortedPredictionsByGame = new Map<number, Prediction[]>();
  if (statFilter !== 'combo') {
    predictionsByGame.forEach((preds, gameId) => {
    const sorted = [...preds].sort((a, b) => {
      let aValue: number | string;
      let bValue: number | string;

      if (sortBy === 'probability') {
        aValue = getProbability(a);
        bValue = getProbability(b);
      } else if (sortBy === 'mean') {
        aValue = a.distribution_mean;
        bValue = b.distribution_mean;
      } else {
        aValue = a.player_name || '';
        bValue = b.player_name || '';
      }

      if (typeof aValue === 'number' && typeof bValue === 'number') {
        return sortOrder === 'asc' ? aValue - bValue : bValue - aValue;
      } else {
        const aStr = String(aValue).toLowerCase();
        const bStr = String(bValue).toLowerCase();
        if (sortOrder === 'asc') {
          return aStr.localeCompare(bStr);
        } else {
          return bStr.localeCompare(aStr);
        }
      }
    });
    sortedPredictionsByGame.set(gameId, sorted);
    });
  }

  // Flatten for copy function (maintains game grouping)
  const sortedPredictions = statFilter === 'combo' ? [] : Array.from(sortedPredictionsByGame.values()).flat();

  const handleSort = (newSortBy: string) => {
    if (sortBy === newSortBy) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
    } else {
      setSortBy(newSortBy);
      setSortOrder('desc');
    }
  };

  const copyToClipboard = () => {
    if (statFilter === 'combo') {
      copyComboBetsToClipboard();
      return;
    }

    if (sortedPredictions.length === 0) {
      alert('No predictions to copy');
      return;
    }

    // Format predictions for Discord (plain text, no special formatting)
    // Use the already-grouped-by-game structure from sortedPredictionsByGame
    const lines: string[] = [];
    lines.push(`📊 NBA Predictions - ${format(parseDateString(selectedDate), 'MMM d, yyyy')}`);
    lines.push('');
    
    // Iterate through games (already grouped)
    Array.from(sortedPredictionsByGame.entries()).forEach(([gameId, preds]) => {
      // Get game info from first prediction (enriched with game data)
      const firstPred = preds[0] as any;
      const gameKey = `${firstPred.away_team_abbreviation || 'Away'} @ ${firstPred.home_team_abbreviation || 'Home'}`;
      const gameDate = firstPred.game_date ? format(parseDateString(firstPred.game_date), 'MMM d') : '';
      
      lines.push(`🏀 ${gameKey}${gameDate ? ` - ${gameDate}` : ''}`);
      
      // Group by player
      const byPlayer: { [key: string]: Prediction[] } = {};
      preds.forEach(pred => {
        const playerKey = pred.player_name || `Player ${pred.player_id}`;
        if (!byPlayer[playerKey]) {
          byPlayer[playerKey] = [];
        }
        byPlayer[playerKey].push(pred);
      });

      // Format each player's predictions
      Object.entries(byPlayer).forEach(([playerName, playerPreds]) => {
        playerPreds.forEach(pred => {
          const line = getLine(pred);
          const probability = getProbability(pred);
          const statType = pred.stat_type === 'points' ? 'PTS' : 
                          pred.stat_type === 'rebounds' ? 'REB' : 
                          pred.stat_type === 'assists' ? 'AST' : 
                          pred.stat_type.toUpperCase();
          const betType = pred.bet_type === 'safe' ? 'SAFE' : 
                         pred.bet_type === 'standard' ? 'STD' : 
                         'LONG';
          
          lines.push(`  ${playerName} (${pred.player_team || 'N/A'}) - ${statType} Over ${line.toFixed(1)} - ${(probability * 100).toFixed(1)}% (${betType})`);
        });
      });
      
      lines.push('');
    });

    // Join with newlines and copy to clipboard
    const text = lines.join('\n');
    
    // Use the Clipboard API
    navigator.clipboard.writeText(text).then(() => {
      alert(`Copied ${sortedPredictions.length} predictions to clipboard! Ready to paste in Discord.`);
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
        alert(`Copied ${sortedPredictions.length} predictions to clipboard! Ready to paste in Discord.`);
      } catch (err) {
        alert('Failed to copy. Please try selecting and copying manually.');
      }
      document.body.removeChild(textarea);
    });
  };

  const copyComboBetsToClipboard = () => {
    if (!comboBets || !comboBets.games || comboBets.games.length === 0) {
      alert('No combo bets to copy');
      return;
    }

    const lines: string[] = [];
    lines.push(`📊 NBA Combo Bets - ${format(parseDateString(selectedDate), 'MMM d, yyyy')}`);
    lines.push('');
    
    comboBets.games.forEach((game: any) => {
      const gameKey = `${game.away_team || 'Away'} @ ${game.home_team || 'Home'}`;
      lines.push(`🏀 ${gameKey}`);
      lines.push('');
      
      // Group bets by player
      const byPlayer: { [key: string]: ComboBet[] } = {};
      
      // Add combo props
      if (game.combo_props && game.combo_props.length > 0) {
        game.combo_props.forEach((bet: ComboBet) => {
          const playerKey = bet.player_name;
          if (!byPlayer[playerKey]) {
            byPlayer[playerKey] = [];
          }
          byPlayer[playerKey].push(bet);
        });
      }
      
      // Add double-doubles
      if (game.double_doubles && game.double_doubles.length > 0) {
        game.double_doubles.forEach((bet: ComboBet) => {
          const playerKey = bet.player_name;
          if (!byPlayer[playerKey]) {
            byPlayer[playerKey] = [];
          }
          byPlayer[playerKey].push({ ...bet, type: 'double_double' });
        });
      }
      
      // Add triple-doubles
      if (game.triple_doubles && game.triple_doubles.length > 0) {
        game.triple_doubles.forEach((bet: ComboBet) => {
          const playerKey = bet.player_name;
          if (!byPlayer[playerKey]) {
            byPlayer[playerKey] = [];
          }
          byPlayer[playerKey].push({ ...bet, type: 'triple_double' });
        });
      }
      
      // Format each player's bets
      Object.entries(byPlayer).forEach(([playerName, playerBets]) => {
        playerBets.forEach(bet => {
          let betLine = '';
          
          if (bet.type === 'double_double') {
            betLine = `DD - ${(bet.probability * 100).toFixed(1)}%`;
          } else if (bet.type === 'triple_double') {
            betLine = `TD - ${(bet.probability * 100).toFixed(1)}%`;
          } else if (bet.combo_type) {
            // Combo prop (Points + Assists, etc.)
            const stat1 = bet.stat1 === 'points' ? 'PTS' : bet.stat1 === 'rebounds' ? 'REB' : 'AST';
            const stat2 = bet.stat2 === 'points' ? 'PTS' : bet.stat2 === 'rebounds' ? 'REB' : 'AST';
            const line = bet.line ? bet.line.toFixed(1) : '';
            const prob = (bet.probability * 100).toFixed(1);
            const betType = bet.bet_type === 'safe' ? 'SAFE' : bet.bet_type === 'standard' ? 'STD' : 'LONG';
            betLine = `${stat1} + ${stat2} Over ${line} - ${prob}% (${betType})`;
          } else if (bet.display) {
            // Use display field if available
            const prob = (bet.probability * 100).toFixed(1);
            const betType = bet.bet_type === 'safe' ? 'SAFE' : bet.bet_type === 'standard' ? 'STD' : 'LONG';
            betLine = `${bet.display} - ${prob}% (${betType})`;
          }
          
          if (betLine) {
            lines.push(`  ${playerName} - ${betLine}`);
          }
        });
      });
      
      lines.push('');
    });

    // Join with newlines and copy to clipboard
    const text = lines.join('\n');
    
    navigator.clipboard.writeText(text).then(() => {
      const totalBets = comboBets.games.reduce((sum: number, game: any) => {
        return sum + 
          (game.combo_props?.length || 0) + 
          (game.double_doubles?.length || 0) + 
          (game.triple_doubles?.length || 0);
      }, 0);
      alert(`Copied ${totalBets} combo bets to clipboard! Ready to paste in Discord.`);
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
        const totalBets = comboBets.games.reduce((sum: number, game: any) => {
          return sum + 
            (game.combo_props?.length || 0) + 
            (game.double_doubles?.length || 0) + 
            (game.triple_doubles?.length || 0);
        }, 0);
        alert(`Copied ${totalBets} combo bets to clipboard! Ready to paste in Discord.`);
      } catch (err) {
        alert('Failed to copy. Please try selecting and copying manually.');
      }
      document.body.removeChild(textarea);
    });
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center h-64">
        <div className="text-gray-500">Loading predictions...</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">All Predictions</h1>
          <p className="mt-1 text-sm text-gray-500">Complete list of all betting predictions</p>
        </div>
        {((statFilter === 'combo' && comboBets && comboBets.games.length > 0) || 
          (statFilter !== 'combo' && sortedPredictions.length > 0)) && (
          <button
            onClick={copyToClipboard}
            className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 flex items-center gap-2"
            title="Copy all predictions/combo bets in Discord-friendly format"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
            </svg>
            Copy for Discord
          </button>
        )}
      </div>

      {/* Filters */}
      <div className="bg-white rounded-lg shadow p-4">
        <div className="flex flex-wrap gap-4 items-center">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Date</label>
            <input
              type="date"
              value={selectedDate}
              onChange={(e) => setSelectedDate(e.target.value)}
              className="px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Stat Type</label>
            <select
              value={statFilter}
              onChange={(e) => setStatFilter(e.target.value)}
              className="px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
            >
              <option value="all">All</option>
              <option value="points">Points</option>
              <option value="rebounds">Rebounds</option>
              <option value="assists">Assists</option>
              <option value="combo">Combo (P+A, P+R, R+A, DD, TD)</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Bet Type</label>
            <select
              value={betTypeFilter}
              onChange={(e) => setBetTypeFilter(e.target.value)}
              className="px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
            >
              <option value="all">All</option>
              <option value="safe">Safe</option>
              <option value="standard">Standard</option>
              <option value="long_shot">Long Shot</option>
            </select>
          </div>
          <div className="flex-1"></div>
          <div className="text-sm text-gray-600">
            {statFilter === 'combo' 
              ? comboBets ? `Showing combo bets for ${comboBets.games.length} games` : 'No combo bets'
              : `Showing ${sortedPredictions.length} predictions`
            }
          </div>
        </div>
      </div>

      {/* Combo Bets Display */}
      {statFilter === 'combo' ? (
        !comboBets || comboBets.games.length === 0 ? (
          <div className="bg-white rounded-lg shadow p-8 text-center text-gray-500">
            No combo bets found for this date. Generate predictions first.
          </div>
        ) : (
          <div className="space-y-6">
            {comboBets.games.map((game: any) => (
              <div key={game.game_id} className="bg-white rounded-lg shadow overflow-hidden">
                <div className="bg-gray-50 px-6 py-3 border-b border-gray-200">
                  <div className="flex items-center justify-between">
                    <div>
                      <Link
                        to={`/games/${game.game_id}`}
                        className="text-lg font-semibold text-gray-900 hover:text-blue-600"
                      >
                        {game.away_team} @ {game.home_team}
                      </Link>
                    </div>
                  </div>
                </div>
                
                <div className="p-6 space-y-6">
                  {/* Combo Props */}
                  {game.combo_props && game.combo_props.length > 0 && (
                    <div>
                      <h3 className="text-md font-semibold text-gray-900 mb-3">Combo Props</h3>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                        {game.combo_props.map((bet: ComboBet, idx: number) => (
                          <div key={idx} className="border border-gray-200 rounded p-3 hover:bg-gray-50">
                            <div className="flex justify-between items-start">
                              <div className="flex-1">
                                <div className="font-medium text-gray-900">{bet.player_name}</div>
                                <div className="text-sm text-gray-600">
                                  {bet.display || `${bet.stat1?.toUpperCase()} + ${bet.stat2?.toUpperCase()} Over ${bet.line?.toFixed(1)}`}
                                </div>
                                {bet.last_3_games && bet.last_3_games.length > 0 && (
                                  <Last3Games 
                                    last3Games={bet.last_3_games} 
                                    statType={`${bet.stat1}+${bet.stat2}`}
                                    isCombo={true}
                                  />
                                )}
                              </div>
                              <div className="text-right ml-4">
                                <div className="text-sm font-semibold text-blue-600">
                                  {(bet.probability * 100).toFixed(1)}%
                                </div>
                                <div className="text-xs text-gray-500 capitalize">{bet.bet_type}</div>
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  
                  {/* Double Doubles */}
                  {game.double_doubles && game.double_doubles.length > 0 && (
                    <div>
                      <h3 className="text-md font-semibold text-gray-900 mb-3">Double-Doubles (DD)</h3>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                        {game.double_doubles.map((bet: ComboBet, idx: number) => (
                          <div key={idx} className="border border-gray-200 rounded p-3 hover:bg-gray-50">
                            <div className="flex justify-between items-start">
                              <div className="flex-1">
                                <div className="font-medium text-gray-900">{bet.player_name}</div>
                                <div className="text-sm text-gray-600">
                                  {bet.display || bet.label || 'Double-Double'}
                                </div>
                                {bet.last_3_games && bet.last_3_games.length > 0 && (
                                  <Last3Games 
                                    last3Games={bet.last_3_games} 
                                    statType="DD"
                                    isCombo={false}
                                    isMilestone={true}
                                  />
                                )}
                              </div>
                              <div className="text-right ml-4">
                                <div className="text-sm font-semibold text-blue-600">
                                  {(bet.probability * 100).toFixed(1)}%
                                </div>
                                <div className="text-xs text-gray-500">DD</div>
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  
                  {/* Triple Doubles */}
                  {game.triple_doubles && game.triple_doubles.length > 0 && (
                    <div>
                      <h3 className="text-md font-semibold text-gray-900 mb-3">Triple-Doubles (TD)</h3>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                        {game.triple_doubles.map((bet: ComboBet, idx: number) => (
                          <div key={idx} className="border border-gray-200 rounded p-3 hover:bg-gray-50">
                            <div className="flex justify-between items-start">
                              <div className="flex-1">
                                <div className="font-medium text-gray-900">{bet.player_name}</div>
                                <div className="text-sm text-gray-600">
                                  {bet.display || bet.label || 'Triple-Double'}
                                </div>
                                {bet.last_3_games && bet.last_3_games.length > 0 && (
                                  <Last3Games 
                                    last3Games={bet.last_3_games} 
                                    statType="TD"
                                    isCombo={false}
                                    isMilestone={true}
                                  />
                                )}
                              </div>
                              <div className="text-right ml-4">
                                <div className="text-sm font-semibold text-blue-600">
                                  {(bet.probability * 100).toFixed(1)}%
                                </div>
                                <div className="text-xs text-gray-500">TD</div>
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )
      ) : sortedPredictions.length === 0 ? (
        <div className="bg-white rounded-lg shadow p-8 text-center text-gray-500">
          No predictions found for this date. Generate predictions first.
        </div>
      ) : (
        <div className="space-y-6">
          {Array.from(sortedPredictionsByGame.entries()).map(([gameId, gamePredictions]) => {
            // Get game info from first prediction (enriched with game data)
            const firstPred = gamePredictions[0] as any;
            const gameMatchup = `${firstPred.away_team_abbreviation || 'Away'} @ ${firstPred.home_team_abbreviation || 'Home'}`;
            const gameDate = firstPred.game_date ? format(parseDateString(firstPred.game_date), 'MMM d, yyyy') : 'N/A';
            
            return (
              <div key={gameId} className="bg-white rounded-lg shadow overflow-hidden">
                {/* Game Header */}
                <div className="bg-gray-50 px-6 py-3 border-b border-gray-200">
                  <div className="flex items-center justify-between">
                    <div>
                      <Link
                        to={`/games/${gameId}`}
                        className="text-lg font-semibold text-gray-900 hover:text-primary-600"
                      >
                        🏀 {gameMatchup}
                      </Link>
                      <div className="text-sm text-gray-500 mt-1">{gameDate}</div>
                    </div>
                    <div className="text-sm text-gray-600">
                      {gamePredictions.length} prediction{gamePredictions.length !== 1 ? 's' : ''}
                    </div>
                  </div>
                </div>
                
                {/* Predictions Table for this Game */}
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gray-50">
                      <tr>
                        <th
                          onClick={() => handleSort('player')}
                          className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
                        >
                          Player {sortBy === 'player' && (sortOrder === 'asc' ? '↑' : '↓')}
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                          Team
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                          Stat
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                          Bet Type
                        </th>
                        <th
                          onClick={() => handleSort('probability')}
                          className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
                        >
                          Line {sortBy === 'probability' && (sortOrder === 'asc' ? '↑' : '↓')}
                        </th>
                        <th
                          onClick={() => handleSort('probability')}
                          className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
                        >
                          Probability {sortBy === 'probability' && (sortOrder === 'asc' ? '↑' : '↓')}
                        </th>
                        <th
                          onClick={() => handleSort('mean')}
                          className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
                        >
                          Mean {sortBy === 'mean' && (sortOrder === 'asc' ? '↑' : '↓')}
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                          Confidence
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                          Last 3 Games
                        </th>
                      </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-200">
                      {gamePredictions.map((prediction) => {
                        const line = getLine(prediction);
                        const probability = getProbability(prediction);
                        
                        return (
                          <tr key={prediction.prediction_id} className="hover:bg-gray-50">
                            <td className="px-6 py-4 whitespace-nowrap">
                              <div className="text-sm font-medium text-gray-900">
                                {prediction.player_name || `Player ${prediction.player_id}`}
                              </div>
                            </td>
                            <td className="px-6 py-4 whitespace-nowrap">
                              <div className="text-sm text-gray-600">
                                {prediction.player_team || 'N/A'}
                              </div>
                            </td>
                            <td className="px-6 py-4 whitespace-nowrap">
                              <div className="text-sm text-gray-900 capitalize">
                                {prediction.stat_type === 'points' ? 'PTS' : 
                                 prediction.stat_type === 'rebounds' ? 'REB' : 
                                 prediction.stat_type === 'assists' ? 'AST' : 
                                 prediction.stat_type}
                              </div>
                            </td>
                            <td className="px-6 py-4 whitespace-nowrap">
                              <span className={`px-2 py-1 text-xs rounded-full ${
                                prediction.bet_type === 'safe'
                                  ? 'bg-green-100 text-green-800'
                                  : prediction.bet_type === 'standard'
                                  ? 'bg-blue-100 text-blue-800'
                                  : 'bg-orange-100 text-orange-800'
                              }`}>
                                {prediction.bet_type === 'safe' ? 'Safe' : 
                                 prediction.bet_type === 'standard' ? 'Standard' : 
                                 'Long Shot'}
                              </span>
                            </td>
                            <td className="px-6 py-4 whitespace-nowrap">
                              <div className="text-sm font-semibold text-gray-900">
                                Over {line.toFixed(1)}
                              </div>
                            </td>
                            <td className="px-6 py-4 whitespace-nowrap">
                              <div className="text-sm font-semibold text-gray-900">
                                {(probability * 100).toFixed(1)}%
                              </div>
                            </td>
                            <td className="px-6 py-4 whitespace-nowrap">
                              <div className="text-sm text-gray-600">
                                {prediction.distribution_mean.toFixed(1)}
                              </div>
                              <div className="text-xs text-gray-500">
                                ±{prediction.distribution_std_dev.toFixed(1)}
                              </div>
                            </td>
                            <td className="px-6 py-4 whitespace-nowrap">
                              <div className="text-sm text-gray-600">
                                {prediction.confidence_level || 'N/A'}
                              </div>
                              <div className="text-xs text-gray-500">
                                {prediction.volatility_level || 'N/A'}
                              </div>
                            </td>
                            <td className="px-6 py-4">
                              <Last3Games last3Games={prediction.last_3_games} statType={prediction.stat_type} />
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

