import { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { format } from 'date-fns';
import apiService, { Game, Prediction } from '../services/api';
import GenerationProgress from '../components/GenerationProgress';
import ParlayBuilder from '../components/ParlayBuilder';
import Last3Games from '../components/Last3Games';
import { parseDateString } from '../utils/dateUtils';
import { useSport } from '../contexts/SportContext';

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

// Helper function to get line and probability based on bet type
const getBetDetails = (bet: any) => {
  // The API returns line and probability directly, not nested under bet_type
  let line: number | null = bet.line;
  let probability: number | null = bet.probability;

  // If the API data doesn't have these fields, fall back to the old logic
  if (line === null || line === undefined) {
    switch (bet.bet_type) {
      case 'safe':
        line = bet.safe_line;
        probability = bet.safe_probability;
        break;
      case 'standard':
        line = bet.standard_line;
        probability = bet.standard_probability;
        break;
      case 'long_shot':
        line = bet.long_shot_line;
        probability = bet.long_shot_probability;
        break;
      default:
        // Fallback: try to use any available line/probability
        line = bet.safe_line || bet.standard_line || bet.long_shot_line;
        probability = bet.safe_probability || bet.standard_probability || bet.long_shot_probability;
        break;
    }
  }

  // If still null, provide reasonable defaults based on bet type and stat
  if (line === null) {
    // Default lines based on typical NBA stats for the bet type
    switch (bet.bet_type) {
      case 'safe':
        line = bet.stat_type === 'points' ? 20.5 : bet.stat_type === 'rebounds' ? 7.5 : 5.5;
        break;
      case 'standard':
        line = bet.stat_type === 'points' ? 25.5 : bet.stat_type === 'rebounds' ? 9.5 : 7.5;
        break;
      case 'long_shot':
        line = bet.stat_type === 'points' ? 30.5 : bet.stat_type === 'rebounds' ? 12.5 : 10.5;
        break;
      default:
        line = bet.stat_type === 'points' ? 22.5 : bet.stat_type === 'rebounds' ? 8.5 : 6.5;
    }
  }

  if (probability === null) {
    // Default probability based on bet type
    switch (bet.bet_type) {
      case 'safe':
        probability = 0.75;
        break;
      case 'standard':
        probability = 0.5;
        break;
      case 'long_shot':
        probability = 0.15;
        break;
      default:
        probability = 0.5;
    }
  }

  return { line, probability };
};

// Helper function to render reasoning with matchup highlights
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

export default function Dashboard() {
  const { sport } = useSport();
  const isLoadingRef = useRef(false);
  const [selectedDate, setSelectedDate] = useState(format(new Date(), 'yyyy-MM-dd'));
  const [games, setGames] = useState<Game[]>([]);
  const [safeBets, setSafeBets] = useState<any[]>([]);
  const [longShots, setLongShots] = useState<Prediction[]>([]);
  const [suggestedBets, setSuggestedBets] = useState<{[gameKey: string]: {game: any, bets: Prediction[]}}>({});
  const [suggestedParlays, setSuggestedParlays] = useState<any[]>([]);
  const [safeLongParlays, setSafeLongParlays] = useState<any[]>([]);
  const [builderPlays, setBuilderPlays] = useState<any[]>([]);
  const [matchupAdvantages, setMatchupAdvantages] = useState<{[playerName: string]: Prediction[]}>({});
  const [matchupAdvantageBets, setMatchupAdvantageBets] = useState<Prediction[]>([]);
  const [matchupAdvantageParlays, setMatchupAdvantageParlays] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [generationProgress, setGenerationProgress] = useState<{
    progress: number;
    message: string;
  } | null>(null);
  const [collectingResults, setCollectingResults] = useState(false);
  const [collectingPlayers, setCollectingPlayers] = useState(false);
  const [playerCollectionProgress, setPlayerCollectionProgress] = useState<{
    progress: number;
    message: string;
  } | null>(null);
  const [showParlayBuilder, setShowParlayBuilder] = useState(false);
  const [runningUpdate, setRunningUpdate] = useState(false);
  const [updateStatus, setUpdateStatus] = useState<string>('');
  const [updateProgress, setUpdateProgress] = useState<{
    progress: number;
    message: string;
  } | null>(null);

  const handleAddToParlay = (prediction: Prediction) => {
    // Dispatch custom event for ParlayBuilder to listen to
    const event = new CustomEvent('addToParlay', { detail: prediction });
    window.dispatchEvent(event);
    // Open parlay builder if not already open
    if (!showParlayBuilder) {
      setShowParlayBuilder(true);
    }
  };

  const handleAddSuggestedParlay = async (parlay: any) => {
    // For suggested parlays, we need to get the actual predictions for each leg
    // and add them to the parlay builder
    try {
      let addedCount = 0;
      for (const leg of parlay.legs) {
        if (!leg.game_id || !leg.player_id || !leg.stat_type) {
          console.warn('Leg missing required fields:', leg);
          continue;
        }
        
        try {
          // Try to find the prediction for this leg
          const gamePredictions = await apiService.getPredictionsForGame(leg.game_id);
          const matchingPrediction = gamePredictions.find((p: Prediction) => 
            p.player_id === leg.player_id && 
            p.stat_type === leg.stat_type &&
            (leg.bet_type ? p.bet_type === leg.bet_type : true) // bet_type is optional
          );
          
          if (matchingPrediction) {
            handleAddToParlay(matchingPrediction);
            addedCount++;
            // Small delay to allow parlay builder to process
            await new Promise(resolve => setTimeout(resolve, 100));
          }
        } catch (legError) {
          console.error(`Error adding leg for player ${leg.player_id}:`, legError);
        }
      }
      
      // Open parlay builder
      if (!showParlayBuilder) {
        setShowParlayBuilder(true);
      }
      
      if (addedCount === 0) {
        alert('Could not find predictions for this parlay. The predictions may need to be regenerated.');
      } else if (addedCount < parlay.legs.length) {
        alert(`Added ${addedCount} of ${parlay.legs.length} legs to parlay builder.`);
      }
    } catch (error) {
      console.error('Error adding suggested parlay:', error);
      alert('Error adding parlay. Please try adding individual bets instead.');
    }
  };

  useEffect(() => {
    // Small delay to prevent rapid successive calls
    const timeoutId = setTimeout(() => {
      loadData();
    }, 100);

    return () => clearTimeout(timeoutId);
  }, [selectedDate, sport]);

  const copySuggestedBetsToClipboard = () => {
    if (Object.keys(suggestedBets).length === 0) {
      alert('No suggested bets to copy');
      return;
    }

    const lines: string[] = [];
    lines.push(`⭐ NBA Suggested Bets - ${format(parseDateString(selectedDate), 'MMM d, yyyy')}`);
    lines.push('');

    // Group all bets by game
    Object.entries(suggestedBets).forEach(([gameKey, gameData]) => {
      const { game, bets } = gameData;
      const gameTitle = `${game.away_team?.abbreviation || game.away_team_abbreviation || 'UNK'} @ ${game.home_team?.abbreviation || game.home_team_abbreviation || 'UNK'}`;
      const gameDate = game.game_date ? format(parseDateString(game.game_date), 'MMM d') : '';

      lines.push(`🏀 ${gameTitle}${gameDate ? ` - ${gameDate}` : ''}`);
      lines.push('');

      // Group bets by player within each game
      const betsByPlayer: { [playerName: string]: any[] } = {};
      bets.forEach(bet => {
        const playerName = bet.player_name;
        if (!betsByPlayer[playerName]) {
          betsByPlayer[playerName] = [];
        }
        betsByPlayer[playerName].push(bet);
      });

      // Format each player's bets
      Object.entries(betsByPlayer).forEach(([playerName, playerBets]) => {
        playerBets.forEach(bet => {
          const betDetails = getBetDetails(bet);
          const statDisplay = getStatTypeDisplay(bet.stat_type);
          const lineText = betDetails.line !== null
            ? (betDetails.line > 0 ? 'Over' : 'Under') + ' ' + Math.abs(betDetails.line)
            : 'Line TBD';
          const probText = betDetails.probability ? `${(betDetails.probability * 100).toFixed(1)}%` : 'Prob TBD';
          const betTypeText = bet.bet_type ? bet.bet_type.toUpperCase() : 'UNKNOWN';

          lines.push(`${playerName}: ${statDisplay} ${lineText} (${probText} • ${betTypeText})`);
        });
      });

      lines.push(''); // Empty line between games
    });

    // Copy to clipboard
    const text = lines.join('\n');
    navigator.clipboard.writeText(text).then(() => {
      alert('Suggested bets copied to clipboard!');
    }).catch(err => {
      console.error('Failed to copy:', err);
      // Fallback method
      const textArea = document.createElement('textarea');
      textArea.value = text;
      document.body.appendChild(textArea);
      textArea.select();
      try {
        document.execCommand('copy');
        alert('Suggested bets copied to clipboard!');
      } catch (fallbackErr) {
        console.error('Fallback copy failed:', fallbackErr);
        alert('Failed to copy. Please try selecting and copying manually.');
      } finally {
        document.body.removeChild(textArea);
      }
    });
  };

  const copyParlaysToClipboard = () => {
    if (suggestedParlays.length === 0) {
      alert('No parlays to copy');
      return;
    }

    const lines: string[] = [];
    lines.push(`🎯 NBA Suggested Parlays - ${format(parseDateString(selectedDate), 'MMM d, yyyy')}`);
    lines.push('');

    suggestedParlays.forEach((parlay, idx) => {
      lines.push(`${idx + 1}. ${parlay.num_legs}-Leg Parlay (${parlay.odds_display})`);
      lines.push(`   Combined Probability: ${(parlay.combined_probability * 100).toFixed(1)}%`);
      lines.push('');

      parlay.legs.forEach((leg: any, legIdx: number) => {
        const statDisplay = getStatTypeDisplay(leg.stat_type);
        lines.push(`   ${legIdx + 1}. ${leg.player_name} (${leg.player_team}): ${statDisplay} Over ${leg.line} (${(leg.probability * 100).toFixed(1)}% • ${leg.bet_type})`);
      });

      lines.push(''); // Empty line between parlays
    });

    // Copy to clipboard
    const text = lines.join('\n');
    navigator.clipboard.writeText(text).then(() => {
      alert('Parlays copied to clipboard!');
    }).catch(err => {
      console.error('Failed to copy:', err);
      // Fallback method
      const textArea = document.createElement('textarea');
      textArea.value = text;
      document.body.appendChild(textArea);
      textArea.select();
      try {
        document.execCommand('copy');
        alert('Parlays copied to clipboard!');
      } catch (fallbackErr) {
        console.error('Fallback copy failed:', fallbackErr);
        alert('Failed to copy. Please try selecting and copying manually.');
      } finally {
        document.body.removeChild(textArea);
      }
    });
  };

  const copySafeLongParlaysToClipboard = () => {
    if (safeLongParlays.length === 0) {
      alert('No safe long parlays to copy');
      return;
    }

    const lines: string[] = [];
    lines.push(`🎰 NBA Safe Long Parlays - ${format(parseDateString(selectedDate), 'MMM d, yyyy')}`);
    lines.push('');

    safeLongParlays.forEach((parlay, idx) => {
      lines.push(`${idx + 1}. ${parlay.num_legs}-Leg Safe Long Parlay (${parlay.odds_display})`);
      lines.push(`   Combined Probability: ${(parlay.combined_probability * 100).toFixed(1)}%`);
      lines.push('');

      parlay.legs.forEach((leg: any, legIdx: number) => {
        const statDisplay = getStatTypeDisplay(leg.stat_type);
        lines.push(`   ${legIdx + 1}. ${leg.player_name} (${leg.player_team}): ${statDisplay} Over ${leg.line} (${(leg.probability * 100).toFixed(1)}% • ${leg.bet_type})`);
      });

      lines.push(''); // Empty line between parlays
    });

    // Copy to clipboard
    const text = lines.join('\n');
    navigator.clipboard.writeText(text).then(() => {
      alert('Safe long parlays copied to clipboard!');
    }).catch(err => {
      console.error('Failed to copy:', err);
      // Fallback method
      const textArea = document.createElement('textarea');
      textArea.value = text;
      document.body.appendChild(textArea);
      textArea.select();
      try {
        document.execCommand('copy');
        alert('Safe long parlays copied to clipboard!');
      } catch (fallbackErr) {
        console.error('Fallback copy failed:', fallbackErr);
        alert('Failed to copy. Please try selecting and copying manually.');
      } finally {
        document.body.removeChild(textArea);
      }
    });
  };

  const copyBuilderPlaysToClipboard = () => {
    if (builderPlays.length === 0) {
      alert('No builder plays to copy');
      return;
    }

    const lines: string[] = [];
    lines.push(`💰 NBA Builder Plays - ${format(parseDateString(selectedDate), 'MMM d, yyyy')}`);
    lines.push('');

    builderPlays.forEach((play, idx) => {
      lines.push(`${idx + 1}. ${play.num_legs}-Leg Builder Play (${play.odds_display})`);
      lines.push(`   Combined Probability: ${(play.combined_probability * 100).toFixed(1)}%`);
      lines.push('');

      play.legs.forEach((leg: any, legIdx: number) => {
        const statDisplay = getStatTypeDisplay(leg.stat_type);
        lines.push(`   ${legIdx + 1}. ${leg.player_name} (${leg.player_team}): ${statDisplay} Over ${leg.line} (${(leg.probability * 100).toFixed(1)}% • ${leg.bet_type})`);
      });

      lines.push(''); // Empty line between plays
    });

    // Copy to clipboard
    const text = lines.join('\n');
    navigator.clipboard.writeText(text).then(() => {
      alert('Builder plays copied to clipboard!');
    }).catch(err => {
      console.error('Failed to copy:', err);
      // Fallback method
      const textArea = document.createElement('textarea');
      textArea.value = text;
      document.body.appendChild(textArea);
      textArea.select();
      try {
        document.execCommand('copy');
        alert('Builder plays copied to clipboard!');
      } catch (fallbackErr) {
        console.error('Fallback copy failed:', fallbackErr);
        alert('Failed to copy. Please try selecting and copying manually.');
      } finally {
        document.body.removeChild(textArea);
      }
    });
  };

  const copyMatchupBetsToClipboard = () => {
    if (matchupAdvantageBets.length === 0) {
      alert('No matchup bets to copy');
      return;
    }

    const lines: string[] = [];
    lines.push(`🔥 NBA Hot Matchup Bets - ${format(parseDateString(selectedDate), 'MMM d, yyyy')}`);
    lines.push('');

    // Group matchup bets by player (since they're individual bets)
    const betsByPlayer: { [playerName: string]: any[] } = {};
    matchupAdvantageBets.forEach(bet => {
      const playerName = bet.player_name;
      if (!betsByPlayer[playerName]) {
        betsByPlayer[playerName] = [];
      }
      betsByPlayer[playerName].push(bet);
    });

    // Format each player's bets
    Object.entries(betsByPlayer).forEach(([playerName, playerBets]) => {
      playerBets.forEach(bet => {
        const betDetails = getBetDetails(bet);
        const statDisplay = getStatTypeDisplay(bet.stat_type);
        const lineText = betDetails.line !== null
          ? (betDetails.line > 0 ? 'Over' : 'Under') + ' ' + Math.abs(betDetails.line)
          : 'Line TBD';
        const probText = betDetails.probability ? `${(betDetails.probability * 100).toFixed(1)}%` : 'Prob TBD';
        const betTypeText = bet.bet_type ? bet.bet_type.toUpperCase() : 'UNKNOWN';

        lines.push(`${playerName}: ${statDisplay} ${lineText} (${probText} • ${betTypeText})`);
      });
    });

    // Copy to clipboard
    const text = lines.join('\n');
    navigator.clipboard.writeText(text).then(() => {
      alert('Hot matchup bets copied to clipboard!');
    }).catch(err => {
      console.error('Failed to copy:', err);
      // Fallback method
      const textArea = document.createElement('textarea');
      textArea.value = text;
      document.body.appendChild(textArea);
      textArea.select();
      try {
        document.execCommand('copy');
        alert('Hot matchup bets copied to clipboard!');
      } catch (fallbackErr) {
        console.error('Fallback copy failed:', fallbackErr);
        alert('Failed to copy. Please try selecting and copying manually.');
      } finally {
        document.body.removeChild(textArea);
      }
    });
  };

  const copyMatchupAdvantageParlaysToClipboard = () => {
    if (matchupAdvantageParlays.length === 0) {
      alert('No matchup advantage parlays to copy');
      return;
    }

    const lines: string[] = [];
    lines.push(`🔥 Matchup Advantage Parlays - ${format(parseDateString(selectedDate), 'MMM d, yyyy')}`);
    lines.push('');

    matchupAdvantageParlays.forEach((parlay, idx) => {
      lines.push(`${idx + 1}. ${parlay.num_legs}-Leg Matchup Parlay (${parlay.odds_display})`);
      lines.push(`   Combined Probability: ${(parlay.combined_probability * 100).toFixed(2)}%`);
      lines.push(`   Game Diversity: ${parlay.game_diversity} matchups`);
      lines.push('');

      parlay.legs.forEach((leg: any, legIdx: number) => {
        const statDisplay = getStatTypeDisplay(leg.stat_type);
        const legLine = leg.line !== null && leg.line !== undefined
          ? `${leg.line > 0 ? 'Over' : 'Under'} ${Math.abs(leg.line)}`
          : 'Line TBD';
        const probText = leg.probability
          ? `${(leg.probability * 100).toFixed(1)}%`
          : 'Prob TBD';
        const betTypeText = leg.bet_type || 'STANDARD';

        lines.push(`   ${legIdx + 1}. ${leg.player_name} (${leg.player_team}): ${statDisplay} ${legLine} (${probText} • ${betTypeText})`);
      });

      lines.push(''); // Spacer between parlays
    });

    const text = lines.join('\n');
    navigator.clipboard.writeText(text).then(() => {
      alert('Matchup advantage parlays copied to clipboard!');
    }).catch(err => {
      console.error('Failed to copy:', err);
      const textArea = document.createElement('textarea');
      textArea.value = text;
      document.body.appendChild(textArea);
      textArea.select();
      try {
        document.execCommand('copy');
        alert('Matchup advantage parlays copied to clipboard!');
      } catch (fallbackErr) {
        console.error('Fallback copy failed:', fallbackErr);
        alert('Failed to copy. Please try selecting and copying manually.');
      } finally {
        document.body.removeChild(textArea);
      }
    });
  };

  const copyMatchupAdvantagesToClipboard = () => {
    const entries = Object.entries(matchupAdvantages);
    if (entries.length === 0) {
      alert('No matchup advantages to copy');
      return;
    }

    const lines: string[] = [];
    lines.push(`🔥 Matchup Advantages - ${format(parseDateString(selectedDate), 'MMM d, yyyy')}`);
    lines.push('');

    entries.forEach(([playerName, bets]) => {
      const teamLabel = bets[0]?.player_team ? ` (${bets[0].player_team})` : '';
      lines.push(`${playerName}${teamLabel}`);

      bets.forEach(bet => {
        const betDetails = getBetDetails(bet);
        const statDisplay = getStatTypeDisplay(bet.stat_type);
        const lineText = betDetails.line !== null
          ? (betDetails.line > 0 ? 'Over' : 'Under') + ' ' + Math.abs(betDetails.line)
          : 'Line TBD';
        const probText = betDetails.probability ? `${(betDetails.probability * 100).toFixed(1)}%` : 'Prob TBD';
        const betTypeText = bet.bet_type ? bet.bet_type.toUpperCase() : 'UNKNOWN';

        lines.push(`   ${statDisplay} ${lineText} (${probText} • ${betTypeText})`);
      });

      lines.push('');
    });

    const text = lines.join('\n');
    navigator.clipboard.writeText(text).then(() => {
      alert('Matchup advantages copied to clipboard!');
    }).catch(err => {
      console.error('Failed to copy:', err);
      const textArea = document.createElement('textarea');
      textArea.value = text;
      document.body.appendChild(textArea);
      textArea.select();
      try {
        document.execCommand('copy');
        alert('Matchup advantages copied to clipboard!');
      } catch (fallbackErr) {
        console.error('Fallback copy failed:', fallbackErr);
        alert('Failed to copy. Please try selecting and copying manually.');
      } finally {
        document.body.removeChild(textArea);
      }
    });
  };

  const loadData = async () => {
    // Prevent multiple simultaneous loads
    if (isLoadingRef.current) return;

    isLoadingRef.current = true;
    setLoading(true);
    try {
      // If no date selected or today, show all upcoming games
      const dateToUse = selectedDate && selectedDate !== format(new Date(), 'yyyy-MM-dd')
        ? selectedDate
        : undefined;

      // Always show today's games and predictions when on today's date
      const todayDate = format(new Date(), 'yyyy-MM-dd');
      const isToday = selectedDate === todayDate;

      // Make API calls in smaller batches to avoid overwhelming the backend
      // First batch: Basic data
      const [gamesResult, safeBetsResult, longShotsResult] = await Promise.allSettled([
        apiService.getUpcomingGames(14, sport), // Load 14 days of upcoming games to cover all predictions
        apiService.getSafeBets(isToday ? todayDate : selectedDate, 50, sport),
        apiService.getLongShots(isToday ? todayDate : selectedDate, 50, sport),
      ]);

      // Second batch: Suggested bets and parlays
      const [suggestedBetsResult, suggestedParlaysResult, safeLongParlaysResult, builderPlaysResult] = await Promise.allSettled([
        apiService.getSuggestedBets(undefined, 50, sport), // Try without date filter first
        apiService.getSuggestedParlays(isToday ? todayDate : selectedDate, 5, true, sport),
        apiService.getSafeLongParlays(isToday ? todayDate : selectedDate, 3, 12, 0.75, sport),
        apiService.getBuilderPlays(isToday ? todayDate : selectedDate, 5, 2, sport),
      ]);

      // Third batch: Matchup advantages (skip expensive parlay generation for now)
      const [allMatchupAdvantagesResult, matchupAdvantageBetsResult] = await Promise.allSettled([
        apiService.getSuggestedBets(undefined, 100, sport), // Get all matchup advantages from any date
        apiService.getMatchupAdvantageBets(isToday ? todayDate : selectedDate, 10, true, sport),
      ]);

      // Skip matchup advantage parlays for now - causes timeouts
      const matchupAdvantageParlaysResult = { status: 'fulfilled', value: [] };
      
      // Extract data from results, using empty arrays/objects if failed
      let gamesData = gamesResult.status === 'fulfilled' ? gamesResult.value : [];
      console.log('🎮 Loaded games:', gamesData.length);
      gamesData.slice(0, 5).forEach(game => console.log(`  Game ${game.game_id}: ${game.away_team_abbreviation || game.away_team?.abbreviation} @ ${game.home_team_abbreviation || game.home_team?.abbreviation} on ${game.game_date}`));

      const safeBetsData = safeBetsResult.status === 'fulfilled' ? safeBetsResult.value : [];
      const longShotsData = longShotsResult.status === 'fulfilled' ? longShotsResult.value : [];
      const suggestedBetsData = suggestedBetsResult.status === 'fulfilled' ? suggestedBetsResult.value : [];
      console.log('⭐ Suggested bets data:', suggestedBetsData.length);
      console.log('🎯 Suggested bets API result:', suggestedBetsResult);
      console.log('📊 Suggested bets data:', suggestedBetsData);

      // Extract unique game IDs from suggested bets that we don't have yet
      const existingGameIds = new Set(gamesData.map((g: any) => g.game_id));
      const missingGameIds = [...new Set(suggestedBetsData.map((bet: any) => bet.game_id))].filter(
        (id: number) => !existingGameIds.has(id)
      );
      
      // Load missing games individually
      if (missingGameIds.length > 0) {
        console.log(`🔍 Loading ${missingGameIds.length} missing games for suggested bets...`);
        const missingGamesPromises = missingGameIds.map((gameId: number) =>
          apiService.getGame(gameId, sport).catch(() => null)
        );
        const missingGamesResults = await Promise.allSettled(missingGamesPromises);
        const missingGames = missingGamesResults
          .filter((r: any) => r.status === 'fulfilled' && r.value)
          .map((r: any) => {
            const game = r.value;
            // Normalize game structure to match getUpcomingGames format
            return {
              game_id: game.game_id,
              game_date: game.game_date,
              game_status: game.game_status,
              game_time: null, // getGame doesn't return game_time
              home_team_id: game.home_team?.team_id,
              home_team_name: game.home_team?.name,
              home_team_abbreviation: game.home_team?.abbreviation,
              away_team_id: game.away_team?.team_id,
              away_team_name: game.away_team?.name,
              away_team_abbreviation: game.away_team?.abbreviation,
              home_team: game.home_team,
              away_team: game.away_team,
              home_score: game.home_team?.score,
              away_score: game.away_team?.score
            };
          });
        
        console.log(`✅ Loaded ${missingGames.length} missing games`);
        gamesData = [...gamesData, ...missingGames];
      }
      const suggestedParlaysData = suggestedParlaysResult.status === 'fulfilled' ? suggestedParlaysResult.value : [];
      const safeLongParlaysData = safeLongParlaysResult.status === 'fulfilled' ? safeLongParlaysResult.value : [];
      const builderPlaysData = builderPlaysResult.status === 'fulfilled' ? builderPlaysResult.value : [];
      const allMatchupAdvantagesData = allMatchupAdvantagesResult.status === 'fulfilled' ? allMatchupAdvantagesResult.value : [];
      const matchupAdvantageBetsData = matchupAdvantageBetsResult.status === 'fulfilled' ? matchupAdvantageBetsResult.value : [];
      const matchupAdvantageParlaysData = matchupAdvantageParlaysResult.status === 'fulfilled' ? matchupAdvantageParlaysResult.value : [];
      
      // Log any failures
      if (gamesResult.status === 'rejected') console.error('Failed to load games:', gamesResult.reason);
      if (safeBetsResult.status === 'rejected') console.error('Failed to load safe bets:', safeBetsResult.reason);
      if (longShotsResult.status === 'rejected') console.error('Failed to load long shots:', longShotsResult.reason);
      if (suggestedBetsResult.status === 'rejected') console.error('Failed to load suggested bets:', suggestedBetsResult.reason);
      if (suggestedParlaysResult.status === 'rejected') console.error('Failed to load suggested parlays:', suggestedParlaysResult.reason);
      if (safeLongParlaysResult.status === 'rejected') console.error('Failed to load safe long parlays:', safeLongParlaysResult.reason);
      if (builderPlaysResult.status === 'rejected') console.error('Failed to load builder plays:', builderPlaysResult.reason);
      if (matchupAdvantageBetsResult.status === 'rejected') console.error('Failed to load matchup advantage bets:', matchupAdvantageBetsResult.reason);
      if (matchupAdvantageParlaysResult.status === 'rejected') console.error('Failed to load matchup advantage parlays:', matchupAdvantageParlaysResult.reason);
      
      // Remove duplicates by game_id
      const uniqueGamesMap = new Map();
      gamesData.forEach((game: any) => {
        if (!uniqueGamesMap.has(game.game_id)) {
          uniqueGamesMap.set(game.game_id, game);
        }
      });
      const uniqueGames = Array.from(uniqueGamesMap.values());
      
      // Filter games to only show games for the selected date (or today if no date selected)
      const dateToFilter = selectedDate || format(new Date(), 'yyyy-MM-dd');
      const filteredGames = uniqueGames.filter((game: Game) => {
        // Only show games for the selected date
        return game.game_date === dateToFilter;
      });
      
      console.log(`📅 Filtered games for ${dateToFilter}: ${filteredGames.length} games`);
      setGames(filteredGames);

      // Group safe bets by player for display
      const groupSafeBets = (bets: Prediction[]) => {
        const playerGroups = new Map<string, Map<string, { safe?: Prediction; standard?: Prediction }>>();

        bets.forEach((p: Prediction) => {
          if (p.bet_type === 'safe' || p.bet_type === 'standard') {
            const playerKey = `${p.player_id}-${p.game_id}`;
            if (!playerGroups.has(playerKey)) {
              playerGroups.set(playerKey, new Map());
            }
            const statMap = playerGroups.get(playerKey)!;

            if (!statMap.has(p.stat_type)) {
              statMap.set(p.stat_type, {});
            }
            const statGroup = statMap.get(p.stat_type)!;

            if (p.bet_type === 'safe') {
              statGroup.safe = p;
            } else {
              statGroup.standard = p;
            }
          }
        });

        return Array.from(playerGroups.entries()).map(([playerKey, statMap]) => {
          const firstPred = Array.from(statMap.values())[0]?.safe || Array.from(statMap.values())[0]?.standard;
          if (!firstPred) return null;

          const stats: any = {};
          statMap.forEach((group, statType) => {
            stats[statType] = {
              hasSafe: !!group.safe,
              hasStandard: !!group.standard,
              safePrediction: group.safe,
              standardPrediction: group.standard,
            };
          });

          return {
            ...firstPred,
            playerKey,
            stats,
          };
        }).filter(Boolean) as any[];
      };

      setSafeBets(groupSafeBets(safeBetsData));
      setLongShots(longShotsData);

      // Group suggested bets by game
      // Use uniqueGames (all dates) for matching, but filter suggested bets by selected date for display
      const groupedSuggestedBets: {[gameKey: string]: {game: any, bets: Prediction[]}} = {};

      console.log('🎯 Grouping suggested bets by game:');
      console.log('Available games (all dates):', uniqueGames.length);
      console.log('Suggested bets data:', suggestedBetsData.length);

      // Debug: Show all game IDs available
      const availableGameIds = uniqueGames.map((g: any) => g.game_id);
      console.log('Available game IDs:', availableGameIds);

      // Filter suggested bets to only show bets for the selected date (reuse dateToFilter from above)
      const filteredSuggestedBets = suggestedBetsData.filter((bet: any) => {
        return bet.game_date === dateToFilter;
      });
      console.log(`📅 Filtered suggested bets for ${dateToFilter}: ${filteredSuggestedBets.length} bets`);

      filteredSuggestedBets.forEach((bet: Prediction, index) => {
        console.log(`Bet ${index}:`, {
          player: bet.player_name,
          game_id: bet.game_id,
          stat_type: bet.stat_type
        });

        // Find the game this bet is for (use uniqueGames which has all dates)
        let game = uniqueGames.find((g: any) => g.game_id === bet.game_id);
        if (!game) {
          console.log(`⚠️ No game found for bet ${index} (game_id: ${bet.game_id})`);
          console.log(`   Available game IDs:`, availableGameIds);

          // Try to create a placeholder game object so the bet still shows
          // This will at least display the bet even if game details are missing
          game = {
            game_id: bet.game_id,
            game_date: bet.game_date || selectedDate,
            home_team: { abbreviation: 'UNK' },
            away_team: { abbreviation: 'UNK' },
            home_team_abbreviation: 'UNK',
            away_team_abbreviation: 'UNK',
            game_time: null
          };
          console.log(`   Using placeholder game for bet ${index}`);
        }

        // Create a unique key for this game
        const gameKey = `${game.game_id}_${game.game_date}`;

        if (!groupedSuggestedBets[gameKey]) {
          groupedSuggestedBets[gameKey] = {
            game: game,
            bets: []
          };
        }
        groupedSuggestedBets[gameKey].bets.push(bet);
      });

      console.log('Final grouped bets:', Object.keys(groupedSuggestedBets).length, 'games');

      setSuggestedBets(groupedSuggestedBets);
      setSuggestedParlays(suggestedParlaysData);
      setSafeLongParlays(safeLongParlaysData);
      setBuilderPlays(builderPlaysData);

      // Save suggested bets and parlays to historical tracking
      const dateToSave = selectedDate || format(new Date(), 'yyyy-MM-dd');
      
      // Save suggested bets
      if (suggestedBetsData.length > 0) {
        setTimeout(async () => {
          try {
            const betsToSave = suggestedBetsData.map((bet: any) => ({
              player_id: bet.player_id,
              player_name: bet.player_name,
              player_team: bet.player_team || 'UNK',
              game_id: bet.game_id,
              game_date: bet.game_date || dateToSave,
              stat_type: bet.stat_type,
              bet_type: bet.bet_type || 'standard',
              line: bet.line || bet.safe_line || bet.standard_line || bet.long_shot_line || 0,
              probability: bet.probability || bet.safe_probability || bet.standard_probability || bet.long_shot_probability || 0.5,
              confidence_level: bet.confidence_level || 'MEDIUM',
              volatility_level: bet.volatility_level || 'MEDIUM',
              reasoning: bet.reasoning || ''
            }));
            
            await apiService.saveSuggestedBets(betsToSave, dateToSave);
            console.log(`✅ Saved ${betsToSave.length} suggested bets to historical tracking`);
          } catch (error) {
            console.error('Failed to save suggested bets to historical tracking:', error);
          }
        }, 1000);
      }

      // Save suggested parlays
      if (suggestedParlaysData.length > 0) {
        setTimeout(async () => {
          try {
            for (const parlay of suggestedParlaysData) {
              await apiService.saveParlay(
                {
                  num_legs: parlay.num_legs,
                  combined_probability: parlay.combined_probability,
                  odds_display: parlay.odds_display
                },
                parlay.legs || [],
                'suggested'
              );
            }
            console.log(`✅ Saved ${suggestedParlaysData.length} suggested parlays to historical tracking`);
          } catch (error) {
            console.error('Failed to save suggested parlays to historical tracking:', error);
          }
        }, 1500);
      }

      // Save safe long parlays
      if (safeLongParlaysData.length > 0) {
        setTimeout(async () => {
          try {
            for (const parlay of safeLongParlaysData) {
              await apiService.saveParlay(
                {
                  num_legs: parlay.num_legs,
                  combined_probability: parlay.combined_probability,
                  odds_display: parlay.odds_display
                },
                parlay.legs || [],
                'safe_long'
              );
            }
            console.log(`✅ Saved ${safeLongParlaysData.length} safe long parlays to historical tracking`);
          } catch (error) {
            console.error('Failed to save safe long parlays to historical tracking:', error);
          }
        }, 2000);
      }

      // Save builder plays
      if (builderPlaysData.length > 0) {
        setTimeout(async () => {
          try {
            for (const parlay of builderPlaysData) {
              await apiService.saveParlay(
                {
                  num_legs: parlay.num_legs,
                  combined_probability: parlay.combined_probability,
                  odds_display: parlay.odds_display
                },
                parlay.legs || [],
                'builder'
              );
            }
            console.log(`✅ Saved ${builderPlaysData.length} builder plays to historical tracking`);
          } catch (error) {
            console.error('Failed to save builder plays to historical tracking:', error);
          }
        }, 2500);
      }

      // Save matchup advantage parlays
      if (matchupAdvantageParlaysData.length > 0) {
        setTimeout(async () => {
          try {
            for (const parlay of matchupAdvantageParlaysData) {
              await apiService.saveParlay(
                {
                  num_legs: parlay.num_legs,
                  combined_probability: parlay.combined_probability,
                  odds_display: parlay.odds_display,
                  game_diversity: parlay.game_diversity
                },
                parlay.legs || [],
                'matchup_advantage'
              );
            }
            console.log(`✅ Saved ${matchupAdvantageParlaysData.length} matchup advantage parlays to historical tracking`);
          } catch (error) {
            console.error('Failed to save matchup advantage parlays to historical tracking:', error);
          }
        }, 3000);
      }

      // Filter predictions with matchup advantages from ALL dates and group by player
      const matchupAdvantagePredictions = allMatchupAdvantagesData.filter((prediction: any) =>
        prediction.reasoning &&
        (prediction.reasoning.includes('Strong history vs opponent') ||
         prediction.reasoning.includes('Weak history vs opponent'))
      );

      // Group by player name
      const groupedByPlayer: {[playerName: string]: Prediction[]} = {};
      matchupAdvantagePredictions.forEach((prediction: Prediction) => {
        const playerName = prediction.player_name;
        if (!groupedByPlayer[playerName]) {
          groupedByPlayer[playerName] = [];
        }
        groupedByPlayer[playerName].push(prediction);
      });

      setMatchupAdvantages(groupedByPlayer);
      setMatchupAdvantageBets(matchupAdvantageBetsData);
      setMatchupAdvantageParlays(matchupAdvantageParlaysData);
    } catch (error) {
      console.error('Error loading data:', error);
    } finally {
      setLoading(false);
      isLoadingRef.current = false;
    }
  };

  const handleCollectGameResults = async () => {
    setCollectingResults(true);
    try {
      // Show user that this may take a while
      alert('Collecting game results... This may take 30-60 seconds. Please wait.');
      const result = await apiService.collectGameResults();
      alert(`Game results collected! Games processed: ${result.games_processed}, Stats created: ${result.stats_created}`);
      loadData(); // Reload to show updated data
    } catch (error: any) {
      console.error('Error collecting game results:', error);
      if (error.code === 'ECONNABORTED') {
        alert('Request timed out. The collection may still be processing. Try refreshing the page in a minute.');
      } else {
        alert(`Error collecting game results: ${error.message || 'Check console for details'}`);
      }
    } finally {
      setCollectingResults(false);
    }
  };

  const handleCollectPlayers = async () => {
    if (!confirm(`Collect all ${sport} players from ESPN? This should take 2-3 minutes (no rate limits!).`)) {
      return;
    }
    
    setCollectingPlayers(true);
    setPlayerCollectionProgress({ progress: 0, message: 'Starting player collection from ESPN...' });
    try {
      const result = await apiService.collectPlayers(
        sport,
        true, // Use ESPN scraping (default, no rate limits)
        (progress) => {
          setPlayerCollectionProgress({
            progress: progress.progress || 0,
            message: progress.message || 'Collecting players...'
          });
        }
      );
      
      setPlayerCollectionProgress({ progress: 100, message: 'Complete!' });
      
      setTimeout(() => {
        setPlayerCollectionProgress(null);
        if (result.success) {
          const message = (result as any).api_failed 
            ? `⚠️ NBA API rate limit hit. Please try again in 5-10 minutes.\n${result.message || ''}`
            : `✅ Players collected successfully!\nCreated: ${(result as any).created || 0}, Updated: ${(result as any).updated || 0}, Skipped: ${(result as any).skipped || 0}`;
          alert(message);
        } else {
          const message = (result as any).api_failed
            ? `⚠️ NBA API rate limit or connectivity issue.\nPlease wait 5-10 minutes and try again.\n\n${result.message || ''}`
            : `⚠️ Player collection completed with errors.\n${result.message || ''}`;
          alert(message);
        }
        console.log('Player collection result:', result);
        loadData(); // Reload data after collection
      }, 1000);
    } catch (error: any) {
      console.error('Error collecting players:', error);
      setPlayerCollectionProgress(null);
      if (error.code === 'ECONNABORTED') {
        alert('Request timed out. The collection may still be processing. This is normal for player collection (takes 5-10 minutes).');
      } else {
        alert(`Error collecting players: ${error.message || 'Check console for details'}`);
      }
    } finally {
      setCollectingPlayers(false);
    }
  };

  const handleGeneratePredictions = async () => {
    setGenerating(true);
    setGenerationProgress({ progress: 0, message: 'Starting prediction generation...' });
    try {
      // Use appropriate stat types for the sport
      const statTypes = sport === 'NFL'
        ? ['passing_yards', 'rushing_yards', 'receiving_yards']
        : ['points', 'rebounds', 'assists'];

      const result = await apiService.generatePredictions(
        undefined,
        1,
        statTypes,
        sport,
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
        loadData();
      }, 1000);
    } catch (error: any) {
      console.error('Error generating predictions:', error);
      setGenerationProgress(null);
      alert(`Error generating predictions: ${error.message || 'Check console for details'}`);
    } finally {
      setGenerating(false);
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center h-64">
        <div className="text-gray-500">Loading...</div>
      </div>
    );
  }

  const handleQuickUpdate = async () => {
    if (!confirm('Run quick update? This will collect yesterday\'s box scores, evaluate predictions, and generate today\'s predictions. This takes 30-60 seconds.')) {
      return;
    }

    setRunningUpdate(true);
    setUpdateStatus('Running quick update...');
    setUpdateProgress({ message: 'Starting...', progress: 0 });
    try {
      const result = await apiService.runQuickUpdate((progress) => {
        // Update progress if provided
        if (progress.progress !== undefined && progress.progress !== null) {
          setUpdateProgress(prev => ({
            ...prev,
            progress: progress.progress,
            message: progress.message || prev?.message || 'Processing...'
          }));
        }
        // Update status message
        if (progress.message) {
          setUpdateStatus(progress.message);
          // Also update progress message if progress wasn't provided
          if (progress.progress === undefined || progress.progress === null) {
            setUpdateProgress(prev => ({
              ...prev || { progress: 0, message: '' },
              message: progress.message
            }));
          }
        }
      });
      if (result && !result.error) {
        setUpdateStatus('✅ Quick update completed! Refreshing data...');
        setUpdateProgress({ message: 'Completed', progress: 100 });
        await loadData();
        setTimeout(() => {
          setUpdateStatus('');
          setUpdateProgress(null);
          setRunningUpdate(false);
        }, 2000);
      } else {
        setUpdateStatus(`⚠️ ${result?.error || 'Update completed with warnings'}`);
        setRunningUpdate(false);
      }
    } catch (error: any) {
      console.error('Update failed:', error);
      setUpdateStatus(`❌ Error: ${error.response?.data?.detail || error.message}`);
      setRunningUpdate(false);
    }
  };

  const handleOneButtonUpdate = async () => {
    if (!confirm('Run complete refresh? This will:\n1. Collect latest NBA schedules\n2. Update all player data\n3. Generate fresh predictions with proper lines\n\nThis takes 3-5 minutes. Continue?')) {
      return;
    }

    setRunningUpdate(true);
    setUpdateStatus('🚀 Starting complete refresh...');
    setUpdateProgress({ message: 'Initializing...', progress: 0 });

    try {
      // Step 1: Collect schedules
      setUpdateStatus('📅 Step 1/4: Collecting schedules...');
      setUpdateProgress({ message: 'Getting NBA schedules...', progress: 10 });

      // For now, manually run quick update which includes some schedule updates
      await apiService.runQuickUpdate((progress) => {
        setUpdateProgress(prev => ({
          ...prev,
          message: progress.message || 'Processing schedules...',
          progress: 10 + Math.min(progress.progress || 0, 20)
        }));
      });

      // Step 2: Collect players
      setUpdateStatus('👥 Step 2/4: Updating players...');
      setUpdateProgress({ message: 'Collecting player data...', progress: 35 });
      await apiService.collectPlayers(sport, true, (progress) => {
        setUpdateProgress(prev => ({
          ...prev,
          message: `Collecting players: ${progress.message || ''}`,
          progress: 35 + Math.min(progress.progress || 0, 20)
        }));
      });

      // Step 3: Run full update to get complete data
      setUpdateStatus('🔄 Step 3/4: Running full data update...');
      setUpdateProgress({ message: 'Updating all data...', progress: 60 });
      await apiService.runFullUpdate(sport, (progress) => {
        setUpdateProgress(prev => ({
          ...prev,
          message: progress.message || 'Updating data...',
          progress: 60 + Math.min(progress.progress || 0, 20)
        }));
      });

      // Step 4: Generate predictions
      setUpdateStatus('🎯 Step 4/4: Generating predictions...');
      setUpdateProgress({ message: 'Generating predictions...', progress: 85 });

      const statTypes = sport === 'NFL'
        ? ['passing_yards', 'rushing_yards', 'receiving_yards']
        : ['points', 'rebounds', 'assists'];

      await apiService.generatePredictions(
        undefined, // No specific game
        1, // Days ahead
        statTypes,
        sport,
        (progress) => {
          setUpdateProgress(prev => ({
            ...prev,
            message: progress.message || 'Processing predictions...',
            progress: 85 + Math.min(progress.progress || 0, 10)
          }));
        }
      );

      // Final step: Refresh dashboard data
      setUpdateStatus('✅ Refreshing dashboard...');
      setUpdateProgress({ message: 'Loading updated data...', progress: 95 });
      await loadData();

      setUpdateStatus('🎉 Complete refresh finished! All data is up to date.');
      setUpdateProgress({ message: 'Complete!', progress: 100 });

      setTimeout(() => {
        setUpdateStatus('');
        setUpdateProgress(null);
        setRunningUpdate(false);
      }, 3000);

    } catch (error: any) {
      console.error('One-button update failed:', error);
      setUpdateStatus(`❌ Error: ${error.response?.data?.detail || error.message}`);
      setRunningUpdate(false);
    }
  };

  const handleFullUpdate = async () => {
    if (!confirm('Run full update? This will update everything (box scores, stats, analytics, injuries, predictions). This takes 2-5 minutes. Continue?')) {
      return;
    }

    setRunningUpdate(true);
    setUpdateStatus('Running full update (this may take 2-5 minutes)...');
    setUpdateProgress({ message: 'Starting...', progress: 0 });
    try {
      const result = await apiService.runFullUpdate(sport, (progress) => {
        // Update progress if provided
        if (progress.progress !== undefined && progress.progress !== null) {
          setUpdateProgress(prev => ({
            ...prev,
            progress: progress.progress,
            message: progress.message || prev?.message || 'Processing...'
          }));
        }
        // Update status message
        if (progress.message) {
          setUpdateStatus(progress.message);
          // Also update progress message if progress wasn't provided
          if (progress.progress === undefined || progress.progress === null) {
            setUpdateProgress(prev => ({
              ...prev || { progress: 0, message: '' },
              message: progress.message
            }));
          }
        }
      });
      if (result && !result.error) {
        setUpdateStatus('✅ Full update completed! Refreshing data...');
        setUpdateProgress({ message: 'Completed', progress: 100 });
        await loadData();
        setTimeout(() => {
          setUpdateStatus('');
          setUpdateProgress(null);
          setRunningUpdate(false);
        }, 2000);
      } else {
        setUpdateStatus(`⚠️ ${result?.error || 'Update completed with warnings'}`);
        setRunningUpdate(false);
      }
    } catch (error: any) {
      console.error('Update failed:', error);
      setUpdateStatus(`❌ Error: ${error.response?.data?.detail || error.message}`);
      setRunningUpdate(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Update Buttons */}
      <div className="bg-white rounded-lg shadow-md p-4">
        <div className="flex justify-between items-center">
          <div>
            <h2 className="text-xl font-semibold mb-1">Data Updates</h2>
            <p className="text-sm text-gray-600">Run update scripts to collect box scores and refresh predictions</p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={handleOneButtonUpdate}
              disabled={runningUpdate}
              className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:bg-gray-400 disabled:cursor-not-allowed text-sm font-medium mr-4"
            >
              {runningUpdate ? 'Updating...' : '🔄 Full Refresh'}
            </button>
            <button
              onClick={handleQuickUpdate}
              disabled={runningUpdate}
              className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:bg-gray-400 disabled:cursor-not-allowed text-sm font-medium"
            >
              {runningUpdate ? 'Updating...' : 'Quick Update'}
            </button>
            <button
              onClick={handleFullUpdate}
              disabled={runningUpdate}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed text-sm font-medium"
            >
              {runningUpdate ? 'Updating...' : 'Full Update'}
            </button>
          </div>
        </div>
        {updateStatus && (
          <div className="mt-3 space-y-2">
            <div className={`p-3 rounded-lg text-sm ${
              updateStatus.includes('✅') ? 'bg-green-50 text-green-800' :
              updateStatus.includes('⚠️') ? 'bg-yellow-50 text-yellow-800' :
              updateStatus.includes('❌') ? 'bg-red-50 text-red-800' :
              'bg-blue-50 text-blue-800'
            }`}>
              {updateStatus}
            </div>
            {updateProgress && (
              <div className="bg-white rounded-lg shadow p-4 border-2 border-blue-500">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="font-semibold text-gray-900">
                    {runningUpdate ? 'Updating...' : 'Update Status'}
                  </h3>
                  {updateProgress.progress !== null && updateProgress.progress !== undefined && (
                    <span className="text-sm font-semibold text-blue-600">{updateProgress.progress}%</span>
                  )}
                </div>
                {updateProgress.progress !== null && updateProgress.progress !== undefined && (
                  <div className="w-full bg-gray-200 rounded-full h-2.5 mb-2">
                    <div 
                      className="bg-blue-600 h-2.5 rounded-full transition-all duration-300"
                      style={{ width: `${updateProgress.progress}%` }}
                    />
                  </div>
                )}
                <p className="text-sm text-gray-600">{updateProgress.message}</p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Dashboard</h1>
          <p className="mt-1 text-sm text-gray-500">View games and betting picks</p>
        </div>
        <div className="flex gap-4">
          <input
            type="date"
            value={selectedDate}
            onChange={(e) => setSelectedDate(e.target.value)}
            className="px-4 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
          />
          <button
            onClick={() => setShowParlayBuilder(true)}
            className="px-4 py-2 bg-purple-600 text-white rounded-md hover:bg-purple-700 flex items-center gap-2"
          >
            <span>🎯</span>
            <span>Parlay Builder</span>
          </button>
          <button
            onClick={handleCollectPlayers}
            disabled={collectingPlayers}
            className="px-4 py-2 bg-orange-600 text-white rounded-md hover:bg-orange-700 disabled:opacity-50 disabled:cursor-not-allowed"
            title={`Collect all ${sport} players from API (takes 5-10 minutes)`}
          >
            {collectingPlayers ? 'Collecting Players...' : `Collect ${sport} Players`}
          </button>
          <button
            onClick={handleCollectGameResults}
            disabled={collectingResults}
            className="px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {collectingResults ? 'Collecting...' : 'Collect Yesterday\'s Results'}
          </button>
          <button
            onClick={handleGeneratePredictions}
            disabled={generating}
            className="px-4 py-2 bg-primary-600 text-white rounded-md hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {generating ? 'Generating...' : 'Generate Predictions'}
          </button>
        </div>
      </div>

      {/* Generation Progress Indicator - Fixed position, visible across tabs */}
      {generating && generationProgress && (
        <GenerationProgress progress={generationProgress} title="Generating Predictions" color="blue" />
      )}
      {collectingPlayers && playerCollectionProgress && (
        <GenerationProgress progress={playerCollectionProgress} title={`Collecting ${sport} Players`} color="orange" />
      )}

      {/* Quick Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-white rounded-lg shadow p-6">
          <div className="text-sm font-medium text-gray-500">
            {selectedDate === format(new Date(), 'yyyy-MM-dd') || !selectedDate 
              ? 'Games Today' 
              : `Games on ${format(parseDateString(selectedDate), 'MMM d')}`}
          </div>
          <div className="mt-2 text-3xl font-bold text-gray-900">{games.length}</div>
        </div>
        <div className="bg-white rounded-lg shadow p-6">
          <div className="text-sm font-medium text-gray-500">Safe Bets</div>
          <div className="mt-2 text-3xl font-bold text-green-600">{safeBets.length}</div>
        </div>
        <div className="bg-white rounded-lg shadow p-6">
          <div className="text-sm font-medium text-gray-500">Long Shots</div>
          <div className="mt-2 text-3xl font-bold text-orange-600">{longShots.length}</div>
        </div>
      </div>

      {/* Suggested Bets */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold text-gray-900">⭐ Suggested Bets</h2>
          {Object.keys(suggestedBets).length > 0 && (
            <button
              onClick={copySuggestedBetsToClipboard}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg flex items-center space-x-2"
            >
              <span>📋</span>
              <span>Copy All</span>
            </button>
          )}
        </div>
        {Object.keys(suggestedBets).length > 0 ? (
          <div className="space-y-6">
            {Object.entries(suggestedBets).map(([gameKey, gameData]) => {
              const { game, bets } = gameData;
              return (
                <div key={gameKey} className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
                  {/* Game Header */}
                  <div className="bg-gradient-to-r from-blue-500 to-indigo-600 px-6 py-4 text-white">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center space-x-4">
                        <div className="text-lg font-semibold">
                          {game.away_team?.abbreviation || game.away_team_abbreviation || 'UNK'} @ {game.home_team?.abbreviation || game.home_team_abbreviation || 'UNK'}
                        </div>
                        <div className="text-sm text-blue-100">
                          {format(parseDateString(game.game_date), 'MMM dd, yyyy')}
                          {game.game_time && ` • ${game.game_time}`}
                        </div>
                      </div>
                      <div className="text-sm bg-white bg-opacity-20 px-3 py-1 rounded-full">
                        {bets.length} suggestion{bets.length !== 1 ? 's' : ''}
                      </div>
                    </div>
                  </div>

                  {/* Bets Grid */}
                  <div className="p-6">
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                      {bets.map((bet) => {
                        const betDetails = getBetDetails(bet);
                        return (
                          <div
                            key={bet.prediction_id}
                            className="bg-gray-50 rounded-lg p-4 hover:bg-gray-100 transition-colors relative"
                          >
                            <div className="mb-3">
                              <div className="font-semibold text-gray-900 text-lg">{bet.player_name}</div>
                              <div className="text-sm text-gray-500">{bet.player_team}</div>
                            </div>

                            <div className="space-y-2">
                              <div className="flex justify-between items-start">
                                <div className="flex-1">
                                  <div className="text-sm font-medium text-gray-700">
                                    {getStatTypeDisplay(bet.stat_type)} {betDetails.line !== null ? (betDetails.line > 0 ? 'Over' : 'Under') + ' ' + Math.abs(betDetails.line) : 'Line TBD'}
                                  </div>
                                  <div className="text-xs text-gray-500 mt-1">
                                    {betDetails.probability ? (betDetails.probability * 100).toFixed(1) + '%' : 'Prob TBD'} • {bet.bet_type || 'pending'}
                                  </div>
                                </div>
                                <button
                                  onClick={() => handleAddToParlay(bet as Prediction)}
                                  className="w-6 h-6 bg-purple-600 text-white rounded-full hover:bg-purple-700 flex items-center justify-center text-sm font-bold shadow-sm ml-2"
                                  title="Add to parlay"
                                >
                                  +
                                </button>
                              </div>

                              <div className="text-xs text-gray-600">
                                Conf: {bet.confidence_level} • Vol: {bet.volatility_level}
                              </div>

                              <Last3Games last3Games={bet.last_3_games} statType={bet.stat_type} />

                              <div className="mt-2">
                                {renderReasoningWithHighlights(bet.reasoning)}
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="bg-white rounded-lg shadow p-8 text-center">
            <p className="text-gray-500 mb-2">No suggested bets available yet.</p>
            <p className="text-sm text-gray-400">
              {games.length > 0
                ? "Generate predictions to see suggested bets organized by game matchups."
                : "No games scheduled for this date."}
            </p>
          </div>
        )}
      </div>

      {/* Hot Matchup Bets */}
      {matchupAdvantageBets.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-semibold text-gray-900">🔥 Hot Matchup Bets</h2>
            <button
              onClick={copyMatchupBetsToClipboard}
              className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white text-sm font-medium rounded-lg flex items-center space-x-2"
            >
              <span>📋</span>
              <span>Copy All</span>
            </button>
          </div>
          <p className="text-sm text-gray-600 mb-4">
            Individual suggested bets for players with strong historical performance against their opponents.
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {matchupAdvantageBets.map((bet, idx) => {
              const betDetails = getBetDetails(bet);
              return (
              <div
                key={bet.prediction_id || idx}
                className="bg-gradient-to-r from-red-50 to-orange-50 rounded-lg shadow p-4 border-l-4 border-red-500"
              >
                <div className="mb-3">
                  <div className="font-semibold text-gray-900 text-lg">{bet.player_name}</div>
                  <div className="text-sm text-gray-500">{bet.player_team}</div>
                </div>

                <div className="space-y-2">
                  <div className="flex justify-between items-start mb-2">
                    <div className="flex-1">
                      <div className="text-sm font-medium text-gray-700">
                        {getStatTypeDisplay(bet.stat_type)} {betDetails.line !== null ? (betDetails.line > 0 ? 'Over' : 'Under') + ' ' + Math.abs(betDetails.line) : 'Line TBD'}
                      </div>
                      <div className="text-xs text-gray-500 mt-1">
                        {betDetails.probability ? (betDetails.probability * 100).toFixed(1) + '%' : 'Prob TBD'} • {bet.bet_type || 'pending'}
                      </div>
                    </div>
                    <div className="flex flex-col items-end gap-1 ml-2">
                      <button
                        onClick={() => handleAddToParlay(bet as Prediction)}
                        className="w-6 h-6 bg-purple-600 text-white rounded-full hover:bg-purple-700 flex items-center justify-center text-sm font-bold shadow-sm"
                        title="Add to parlay"
                      >
                        +
                      </button>
                      <span className="px-1.5 py-0.5 rounded text-xs font-medium bg-red-100 text-red-800 flex items-center gap-1">
                        🔥 Hot Matchup
                      </span>
                    </div>
                  </div>

                  <div className="text-xs text-gray-600">
                    Conf: {bet.confidence_level} • Vol: {bet.volatility_level}
                  </div>

                  <Last3Games last3Games={bet.last_3_games} statType={bet.stat_type} />

                  <div className="mt-1">
                    {renderReasoningWithHighlights(bet.reasoning)}
                  </div>
                </div>
              </div>
            );
            })}
          </div>
        </div>
      )}

      {/* Matchup Advantages */}
      {Object.keys(matchupAdvantages).length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-3">
            <div>
              <h2 className="text-xl font-semibold text-gray-900">🔥 Matchup Advantages</h2>
              <p className="text-sm text-gray-600">
                Players with strong or weak historical performance against their opponents.
              </p>
            </div>
            <button
              onClick={copyMatchupAdvantagesToClipboard}
              className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium rounded-lg flex items-center space-x-1"
            >
              <span>📋</span>
              <span>Copy</span>
            </button>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {Object.entries(matchupAdvantages).map(([playerName, predictions]) => (
              <div
                key={playerName}
                className="bg-white rounded-lg shadow p-4 hover:shadow-md transition-shadow relative border-l-4 border-green-500"
              >
                <div className="mb-3">
                  <div className="font-semibold text-gray-900 text-lg">{playerName}</div>
                  <div className="text-sm text-gray-500">{predictions[0].player_team}</div>
                </div>

                <div className="space-y-3">
                  {predictions.map((bet, index) => {
                    const betDetails = getBetDetails(bet);
                    return (
                    <div key={bet.prediction_id} className="border-t border-gray-100 pt-3 first:border-t-0 first:pt-0">
                      <div className="flex justify-between items-start mb-2">
                        <div className="flex-1">
                          <div className="text-sm font-medium text-gray-700">
                            {getStatTypeDisplay(bet.stat_type)} {betDetails.line !== null ? (betDetails.line > 0 ? 'Over' : 'Under') + ' ' + Math.abs(betDetails.line) : 'Line TBD'}
                          </div>
                          <div className="text-xs text-gray-500 mt-1">
                            {betDetails.probability ? (betDetails.probability * 100).toFixed(1) + '%' : 'Prob TBD'} • {bet.bet_type || 'pending'}
                          </div>
                        </div>
                        <div className="flex flex-col items-end gap-1 ml-2">
                          <button
                            onClick={() => handleAddToParlay(bet as Prediction)}
                            className="w-6 h-6 bg-purple-600 text-white rounded-full hover:bg-purple-700 flex items-center justify-center text-sm font-bold shadow-sm"
                            title="Add to parlay"
                          >
                            +
                          </button>
                          {/* Matchup advantage indicator */}
                          {bet.reasoning && bet.reasoning.includes('Strong history vs opponent') && (
                            <span className="px-1.5 py-0.5 rounded text-xs font-medium bg-green-100 text-green-800 flex items-center gap-1">
                              🔥
                            </span>
                          )}
                          {bet.reasoning && bet.reasoning.includes('Weak history vs opponent') && (
                            <span className="px-1.5 py-0.5 rounded text-xs font-medium bg-red-100 text-red-800 flex items-center gap-1">
                              ❄️
                            </span>
                          )}
                        </div>
                      </div>

                      <div className="text-xs text-gray-600">
                        Conf: {bet.confidence_level} • Vol: {bet.volatility_level}
                      </div>

                      <Last3Games last3Games={bet.last_3_games} statType={bet.stat_type} />

                      <div className="mt-1">
                        {renderReasoningWithHighlights(bet.reasoning)}
                      </div>
                    </div>
                  );
                  })}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Matchup Advantage Parlays */}
      {matchupAdvantageParlays.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-3">
            <div>
              <h2 className="text-xl font-semibold text-gray-900">🔥 Hot Matchup Parlays</h2>
              <p className="text-sm text-gray-600">
                Suggested parlays featuring players with strong historical performance against their opponents.
              </p>
            </div>
            <button
              onClick={copyMatchupAdvantageParlaysToClipboard}
              className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium rounded-lg flex items-center space-x-1"
            >
              <span>📋</span>
              <span>Copy All</span>
            </button>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {matchupAdvantageParlays.map((parlay, idx) => (
              <div
                key={parlay.parlay_id || idx}
                className="bg-gradient-to-r from-orange-50 to-red-50 rounded-lg shadow-lg p-6 border-2 border-orange-200 relative"
              >
                <div className="absolute top-4 right-4 flex gap-2 z-[60]">
                  <button
                    onClick={() => handleAddSuggestedParlay(parlay)}
                    className="w-10 h-10 bg-purple-600 text-white rounded-full hover:bg-purple-700 flex items-center justify-center text-xl font-bold shadow-md"
                    title="Add all legs to parlay builder"
                  >
                    +
                  </button>
                </div>
                <div className="flex justify-between items-start mb-4 pr-14">
                  <div>
                    <h3 className="text-xl font-bold text-gray-900">
                      {parlay.num_legs}-Leg Matchup Parlay
                    </h3>
                    <div className="text-sm text-gray-600 mt-1">
                      Combined Probability: {(parlay.combined_probability * 100).toFixed(2)}%
                    </div>
                    <div className="text-xs text-gray-500 mt-1">
                      Game Diversity: {parlay.game_diversity} different matchups
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-3xl font-bold text-orange-600">
                      {parlay.odds_display}
                    </div>
                    <div className="text-xs text-gray-500">Odds</div>
                  </div>
                </div>
                <div className="space-y-3">
                  {parlay.legs.map((leg: any, legIdx: number) => (
                    <div key={legIdx} className="border-l-4 border-orange-500 pl-3 py-2 bg-white rounded">
                      <div className="font-medium text-gray-900">{leg.player_name} ({leg.player_team})</div>
                      <div className="text-sm text-gray-600">
                        {getStatTypeDisplay(leg.stat_type)} {leg.line !== null && leg.line !== undefined ? (leg.line > 0 ? 'Over' : 'Under') + ' ' + Math.abs(leg.line) : 'N/A'} • {leg.bet_type || 'standard'} • {leg.probability ? (leg.probability * 100).toFixed(1) + '%' : 'N/A'}
                      </div>
                      <div className="text-xs text-gray-500 mt-1">
                        Conf: {leg.confidence_level} • Vol: {leg.volatility_level}
                      </div>
                      <Last3Games last3Games={leg.last_3_games} statType={leg.stat_type} />
                      <div className="mt-1">
                        {renderReasoningWithHighlights(leg.reasoning)}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Safe Long Parlays (10-15 legs) */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold text-gray-900">🎰 Safe Long Parlays (10-15 Legs)</h2>
          {safeLongParlays.length > 0 && (
            <button
              onClick={copySafeLongParlaysToClipboard}
              className="px-4 py-2 bg-green-600 hover:bg-green-700 text-white text-sm font-medium rounded-lg flex items-center space-x-2"
            >
              <span>📋</span>
              <span>Copy All</span>
            </button>
          )}
        </div>
        <p className="text-sm text-gray-600 mb-4">
          Long parlays made of very safe bets. Each leg is 75%+ likely to hit, but combining 12+ legs creates long shot odds.
        </p>
        {safeLongParlays.length > 0 ? (
          <div className="grid grid-cols-1 gap-4">
            {safeLongParlays.map((parlay, idx) => (
              <div
                key={idx}
                className="bg-gradient-to-r from-green-50 to-blue-50 rounded-lg shadow-lg p-6 border-2 border-green-200 relative"
              >
                <div className="absolute top-4 right-4 flex gap-2 z-[60]">
                  <button
                    onClick={async () => {
                      try {
                        const excludePlayerIds = parlay.legs.map((leg: any) => leg.player_id);
                        const newParlay = await apiService.refreshSafeLongParlay(
                          selectedDate,
                          12,
                          0.75,
                          excludePlayerIds
                        );
                        setSafeLongParlays(prev => {
                          const updated = [...prev];
                          updated[idx] = newParlay;
                          return updated;
                        });
                      } catch (error: any) {
                        console.error('Error refreshing parlay:', error);
                        alert(error.response?.data?.detail || 'Failed to refresh parlay. Try again.');
                      }
                    }}
                    className="w-10 h-10 bg-blue-600 text-white rounded-full hover:bg-blue-700 flex items-center justify-center text-sm font-bold shadow-md"
                    title="Refresh this parlay"
                  >
                    🔄
                  </button>
                  <button
                    onClick={() => handleAddSuggestedParlay(parlay)}
                    className="w-10 h-10 bg-purple-600 text-white rounded-full hover:bg-purple-700 flex items-center justify-center text-xl font-bold shadow-md"
                    title="Add all legs to parlay builder"
                  >
                    +
                  </button>
                </div>
                <div className="flex justify-between items-start mb-4 pr-14">
                  <div>
                    <h3 className="text-xl font-bold text-gray-900">
                      {parlay.num_legs}-Leg Safe Parlay
                    </h3>
                    <div className="text-sm text-gray-600 mt-1">
                      Combined Probability: {(parlay.combined_probability * 100).toFixed(2)}%
                    </div>
                    <div className="text-xs text-gray-500 mt-1">
                      Each leg: {parlay.min_leg_probability ? (parlay.min_leg_probability * 100).toFixed(0) : 'N/A'}%+ likely • 
                      Avg: {parlay.avg_leg_probability ? (parlay.avg_leg_probability * 100).toFixed(0) : 'N/A'}% • 
                      Games: {parlay.game_diversity}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-3xl font-bold text-green-600">
                      {parlay.odds_display}
                    </div>
                    <div className="text-xs text-gray-500">Odds</div>
                  </div>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2 max-h-96 overflow-y-auto">
                  {parlay.legs.map((leg: any, legIdx: number) => (
                    <div key={legIdx} className="bg-white rounded p-3 border border-green-200">
                      <div className="font-semibold text-sm text-gray-900">
                        {leg.player_name}
                        {leg.player_team && (
                          <span className="ml-2 text-xs font-normal text-gray-500">({leg.player_team})</span>
                        )}
                      </div>
                      <div className="text-xs text-gray-600">
                        {getStatTypeDisplay(leg.stat_type)} Over {leg.line}
                        <span className="ml-2 text-green-600 font-semibold">
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
        ) : (
          <div className="bg-white rounded-lg shadow p-8 text-center">
            <p className="text-gray-500 mb-2">No safe long parlays available yet.</p>
            <p className="text-sm text-gray-400">
              Generate predictions first. Need at least 12 players with 75%+ safe bet probability.
            </p>
          </div>
        )}
      </div>

      {/* Builder Plays - Double Your Money */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold text-gray-900">💰 Builder Plays - Double Your Money</h2>
          {builderPlays.length > 0 && (
            <button
              onClick={copyBuilderPlaysToClipboard}
              className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-medium rounded-lg flex items-center space-x-2"
            >
              <span>📋</span>
              <span>Copy All</span>
            </button>
          )}
        </div>
        <p className="text-sm text-gray-600 mb-4">
          Safe 2-3 leg parlays designed to roughly double your money. Bet $10 to win $8-9.
        </p>
        {builderPlays.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {builderPlays.map((play, idx) => (
              <div
                key={idx}
                className="bg-gradient-to-r from-green-50 to-emerald-50 rounded-lg shadow-lg p-6 border-2 border-green-200 relative"
              >
                <div className="absolute top-4 right-4 flex gap-2 z-[60]">
                  <button
                    onClick={async () => {
                      try {
                        const excludePlayerIds = play.legs.map((leg: any) => leg.player_id);
                        const newPlay = await apiService.refreshBuilderPlay(
                          selectedDate,
                          play.num_legs,
                          excludePlayerIds
                        );
                        setBuilderPlays(prev => {
                          const updated = [...prev];
                          updated[idx] = newPlay;
                          return updated;
                        });
                      } catch (error: any) {
                        console.error('Error refreshing builder play:', error);
                        alert(error.response?.data?.detail || 'Failed to refresh builder play. Try again.');
                      }
                    }}
                    className="w-8 h-8 bg-blue-600 text-white rounded-full hover:bg-blue-700 flex items-center justify-center text-xs font-bold shadow-md"
                    title="Refresh this builder play"
                  >
                    🔄
                  </button>
                </div>
                <div className="flex justify-between items-start mb-4 pr-12">
                  <div>
                    <h3 className="text-lg font-bold text-gray-900">
                      {play.num_legs}-Leg Builder Play
                    </h3>
                    <div className="text-sm text-gray-600 mt-1">
                      Combined Probability: {(play.combined_probability * 100).toFixed(1)}%
                    </div>
                    <div className="text-xs text-gray-500 mt-1">
                      Bet ${play.payout_example.bet_amount} → Win ${play.payout_example.win_amount} (Total: ${play.payout_example.total_return})
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-2xl font-bold text-green-600">
                      {play.odds_display}
                    </div>
                    <div className="text-xs text-gray-500">Odds</div>
                  </div>
                </div>
                <div className="space-y-2 mb-4">
                  {play.legs.map((leg: any, legIdx: number) => (
                    <div key={legIdx} className="bg-white rounded p-3 border border-green-200">
                      <div className="font-medium text-sm text-gray-900">
                        {leg.player_name}
                        {leg.player_team && (
                          <span className="ml-2 text-xs font-normal text-gray-500">({leg.player_team})</span>
                        )}
                      </div>
                      <div className="text-xs text-gray-600">
                        {getStatTypeDisplay(leg.stat_type)} {leg.bet_line} •
                        <span className="ml-2 text-green-600 font-semibold">
                          {(leg.probability * 100).toFixed(0)}%
                        </span>
                      </div>
                      <Last3Games last3Games={leg.last_3_games} statType={leg.stat_type} />
                    </div>
                  ))}
                </div>
                <button
                  onClick={() => handleAddSuggestedParlay(play)}
                  className="w-full px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 text-sm font-medium"
                >
                  Add to Parlay Builder
                </button>
              </div>
            ))}
          </div>
        ) : (
          <div className="bg-white rounded-lg shadow p-8 text-center">
            <p className="text-gray-500 mb-2">No builder plays available yet.</p>
            <p className="text-sm text-gray-400">
              {games.length > 0
                ? "Need at least 2-3 players with 75%+ safe bet probability to create builder plays. Generate predictions first."
                : "No games scheduled for this date."}
            </p>
          </div>
        )}
      </div>

      {/* Suggested Parlays (2-4 legs) */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold text-gray-900">🎯 Suggested Parlays (2-4 Legs)</h2>
          {suggestedParlays.length > 0 && (
            <button
              onClick={copyParlaysToClipboard}
              className="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white text-sm font-medium rounded-lg flex items-center space-x-2"
            >
              <span>📋</span>
              <span>Copy All</span>
            </button>
          )}
        </div>
        {suggestedParlays.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {suggestedParlays.map((parlay, idx) => (
              <div
                key={idx}
                className="bg-white rounded-lg shadow p-6 hover:shadow-md transition-shadow relative"
              >
                <button
                  onClick={() => handleAddSuggestedParlay(parlay)}
                  className="absolute top-4 right-4 w-10 h-10 bg-purple-600 text-white rounded-full hover:bg-purple-700 flex items-center justify-center text-xl font-bold shadow-md z-[60]"
                  title="Add all legs to parlay builder"
                >
                  +
                </button>
                <div className="flex justify-between items-start mb-4 pr-14">
                  <div>
                    <h3 className="text-lg font-semibold text-gray-900">
                      {parlay.num_legs}-Leg Parlay
                    </h3>
                    <div className="text-sm text-gray-500">
                      Combined Probability: {(parlay.combined_probability * 100).toFixed(1)}%
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-2xl font-bold text-primary-600">
                      {parlay.odds_display}
                    </div>
                    <div className="text-xs text-gray-500">Odds</div>
                  </div>
                </div>
                <div className="space-y-3">
                  {parlay.legs.map((leg: any, legIdx: number) => (
                    <div key={legIdx} className="border-l-4 border-primary-500 pl-3 py-2 bg-gray-50 rounded">
                      <div className="font-medium text-gray-900">{leg.player_name} ({leg.player_team})</div>
                      <div className="text-sm text-gray-600">
                        {getStatTypeDisplay(leg.stat_type)} Over {leg.line} • {leg.bet_type} • {(leg.probability * 100).toFixed(1)}%
                      </div>
                      <Last3Games last3Games={leg.last_3_games} statType={leg.stat_type} />
                      {renderReasoningWithHighlights(leg.reasoning)}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="bg-white rounded-lg shadow p-8 text-center">
            <p className="text-gray-500 mb-2">No suggested parlays available yet.</p>
            <p className="text-sm text-gray-400">
              {games.length > 0
                ? "Generate predictions first to see suggested parlay combinations."
                : "No games scheduled for this date."}
            </p>
          </div>
        )}
      </div>

      {/* Games List */}
      <div>
        <h2 className="text-xl font-semibold text-gray-900 mb-4">
          {selectedDate === format(new Date(), 'yyyy-MM-dd') ? "Today's Games" : "Upcoming Games"}
        </h2>
        {games.length === 0 ? (
          <div className="bg-white rounded-lg shadow p-8 text-center text-gray-500">
            No games scheduled for this date
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4">
            {games.map((game) => (
              <Link
                key={game.game_id}
                to={`/games/${game.game_id}`}
                className="bg-white rounded-lg shadow hover:shadow-md transition-shadow p-6"
              >
                <div className="flex justify-between items-center">
                  <div>
                    <div className="text-lg font-semibold text-gray-900">
                      {(game.away_team_abbreviation || game.away_team?.abbreviation) || 'Away'} @ {(game.home_team_abbreviation || game.home_team?.abbreviation) || 'Home'}
                    </div>
                    <div className="text-sm text-gray-500 mt-1">
                      {format(parseDateString(game.game_date), 'MMM d, yyyy')}
                      {game.game_time && (() => {
                        const gameTime = new Date(game.game_time);
                        // Check if time is midnight (likely means time not available)
                        const isMidnight = gameTime.getHours() === 0 && gameTime.getMinutes() === 0;
                        if (!isMidnight) {
                          return ` • ${gameTime.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', timeZoneName: 'short' })}`;
                        }
                        return null;
                      })()}
                      {` • ${game.game_status || 'scheduled'}`}
                    </div>
                  </div>
                  <div className="flex gap-4 text-sm">
                    {game.safe_bets_count !== undefined && (
                      <span className="px-3 py-1 bg-green-100 text-green-800 rounded-full">
                        {game.safe_bets_count} Safe
                      </span>
                    )}
                    {game.long_shots_count !== undefined && (
                      <span className="px-3 py-1 bg-orange-100 text-orange-800 rounded-full">
                        {game.long_shots_count} Long Shots
                      </span>
                    )}
                    <span className="text-gray-500">→</span>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>

      {/* Quick Picks */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Safe Bets */}
        <div>
          <h2 className="text-xl font-semibold text-gray-900 mb-4">Top Safe Bets</h2>
          {safeBets.length === 0 ? (
            <div className="bg-white rounded-lg shadow p-8 text-center text-gray-500">
              No safe bets available. Generate predictions to see picks.
            </div>
          ) : (
            <div className="space-y-3">
              {safeBets.slice(0, 5).map((playerCard: any) => {
                const statTypes = Object.keys(playerCard.stats || {});
                const statLabels: { [key: string]: string } = {
                  points: 'PTS',
                  rebounds: 'REB',
                  assists: 'AST',
                  three_pointers_made: '3PM',
                };
                
                return (
                  <div key={playerCard.playerKey} className="bg-white rounded-lg shadow p-4">
                    <div className="mb-3">
                      <div className="font-semibold text-gray-900">{playerCard.player_name}</div>
                      <div className="text-sm text-gray-500">
                        {statTypes.map(st => statLabels[st] || st.toUpperCase()).join(' • ')}
                        {playerCard.player_team && ` • ${playerCard.player_team}`}
                        {playerCard.game_time && ` • ${new Date(playerCard.game_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`}
                      </div>
                    </div>
                    <div className="space-y-2">
                      {statTypes.map((statType: string) => {
                        const statData = playerCard.stats[statType];
                        const safePred = statData.safePrediction;
                        const standardPred = statData.standardPrediction;
                        const hasSafe = statData.hasSafe;
                        const hasStandard = statData.hasStandard;
                        
                        return (
                          <div key={statType} className="border rounded p-2 bg-gray-50">
                            <div className="text-xs font-semibold text-gray-700 mb-1.5 uppercase">
                              {statLabels[statType] || statType}
                            </div>
                            <div className="space-y-1.5">
                              {hasSafe && safePred && (
                                <div className="flex justify-between items-center p-1.5 bg-green-50 rounded">
                                  <div>
                                    <span className="text-xs font-medium text-green-700">SAFE:</span>
                                    <div className="text-xs font-semibold text-gray-900">
                                      Over {safePred.safe_line?.toFixed(1)}
                                    </div>
                                  </div>
                                  <span className="text-xs font-semibold text-green-600">
                                    {(safePred.safe_probability * 100).toFixed(0)}%
                                  </span>
                                </div>
                              )}
                              {hasStandard && standardPred && (
                                <div className="flex justify-between items-center p-1.5 bg-blue-50 rounded">
                                  <div>
                                    <span className="text-xs font-medium text-blue-700">STANDARD:</span>
                                    <div className="text-xs font-semibold text-gray-900">
                                      Over {standardPred.standard_line?.toFixed(1)}
                                    </div>
                                  </div>
                                  <span className="text-xs font-semibold text-blue-600">
                                    {(standardPred.standard_probability * 100).toFixed(0)}%
                                  </span>
                                </div>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Long Shots */}
        <div>
          <h2 className="text-xl font-semibold text-gray-900 mb-4">Top Long Shots</h2>
          {longShots.length === 0 ? (
            <div className="bg-white rounded-lg shadow p-8 text-center text-gray-500">
              No long shots available. Generate predictions to see picks.
            </div>
          ) : (
            <div className="space-y-3">
              {longShots.slice(0, 5).map((bet) => (
                <div key={bet.prediction_id} className="bg-white rounded-lg shadow p-4">
                  <div className="flex justify-between items-start">
                    <div>
                      <div className="font-semibold text-gray-900">{bet.player_name}</div>
                      <div className="text-sm text-gray-500">
                        {bet.stat_type}
                        {bet.player_team && ` • ${bet.player_team}`}
                        {bet.game_time && ` • ${new Date(bet.game_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="font-bold text-orange-600">Over {bet.long_shot_line.toFixed(1)}</div>
                      <div className="text-xs text-gray-500">
                        {(bet.long_shot_probability * 100).toFixed(0)}% probability
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Parlay Builder */}
      <ParlayBuilder
        isOpen={showParlayBuilder}
        onClose={() => setShowParlayBuilder(false)}
      />
    </div>
  );
}

