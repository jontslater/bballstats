import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { format } from 'date-fns';
import apiService, { Game, Prediction } from '../services/api';
import GenerationProgress from '../components/GenerationProgress';
import ParlayBuilder from '../components/ParlayBuilder';
import { parseDateString } from '../utils/dateUtils';

export default function Dashboard() {
  const [selectedDate, setSelectedDate] = useState(format(new Date(), 'yyyy-MM-dd'));
  const [games, setGames] = useState<Game[]>([]);
  const [safeBets, setSafeBets] = useState<Prediction[]>([]);
  const [longShots, setLongShots] = useState<Prediction[]>([]);
  const [suggestedBets, setSuggestedBets] = useState<any[]>([]);
  const [suggestedParlays, setSuggestedParlays] = useState<any[]>([]);
  const [safeLongParlays, setSafeLongParlays] = useState<any[]>([]);
  const [builderPlays, setBuilderPlays] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [generationProgress, setGenerationProgress] = useState<{
    progress: number;
    message: string;
  } | null>(null);
  const [collectingResults, setCollectingResults] = useState(false);
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
    loadData();
  }, [selectedDate]);

  const loadData = async () => {
    setLoading(true);
    try {
      // If no date selected or today, show all upcoming games
      const dateToUse = selectedDate && selectedDate !== format(new Date(), 'yyyy-MM-dd') 
        ? selectedDate 
        : undefined;
      
      // Always show today's games and predictions when on today's date
      const todayDate = format(new Date(), 'yyyy-MM-dd');
      const isToday = selectedDate === todayDate;
      
      // Always use today's date for games when on today
      // Use Promise.allSettled to prevent one failing request from blocking the entire page
      const [gamesResult, safeBetsResult, longShotsResult, suggestedBetsResult, suggestedParlaysResult, safeLongParlaysResult, builderPlaysResult] = await Promise.allSettled([
        isToday ? apiService.getGames(todayDate) : (dateToUse ? apiService.getGames(dateToUse) : apiService.getUpcomingGames(7)), // Show 7 days ahead
        apiService.getSafeBets(isToday ? todayDate : selectedDate),
        apiService.getLongShots(isToday ? todayDate : selectedDate),
        apiService.getSuggestedBets(isToday ? todayDate : selectedDate, 10),
        apiService.getSuggestedParlays(isToday ? todayDate : selectedDate, 5, true),
        apiService.getSafeLongParlays(isToday ? todayDate : selectedDate, 3, 12, 0.75),
        apiService.getBuilderPlays(isToday ? todayDate : selectedDate, 5, 2),
      ]);
      
      // Extract data from results, using empty arrays/objects if failed
      const gamesData = gamesResult.status === 'fulfilled' ? gamesResult.value : [];
      const safeBetsData = safeBetsResult.status === 'fulfilled' ? safeBetsResult.value : [];
      const longShotsData = longShotsResult.status === 'fulfilled' ? longShotsResult.value : [];
      const suggestedBetsData = suggestedBetsResult.status === 'fulfilled' ? suggestedBetsResult.value : [];
      const suggestedParlaysData = suggestedParlaysResult.status === 'fulfilled' ? suggestedParlaysResult.value : [];
      const safeLongParlaysData = safeLongParlaysResult.status === 'fulfilled' ? safeLongParlaysResult.value : [];
      const builderPlaysData = builderPlaysResult.status === 'fulfilled' ? builderPlaysResult.value : [];
      
      // Log any failures
      if (gamesResult.status === 'rejected') console.error('Failed to load games:', gamesResult.reason);
      if (safeBetsResult.status === 'rejected') console.error('Failed to load safe bets:', safeBetsResult.reason);
      if (longShotsResult.status === 'rejected') console.error('Failed to load long shots:', longShotsResult.reason);
      if (suggestedBetsResult.status === 'rejected') console.error('Failed to load suggested bets:', suggestedBetsResult.reason);
      if (suggestedParlaysResult.status === 'rejected') console.error('Failed to load suggested parlays:', suggestedParlaysResult.reason);
      if (safeLongParlaysResult.status === 'rejected') console.error('Failed to load safe long parlays:', safeLongParlaysResult.reason);
      if (builderPlaysResult.status === 'rejected') console.error('Failed to load builder plays:', builderPlaysResult.reason);
      
      // Filter out finished games from past dates (but keep today's finished games)
      const todayOnly = format(new Date(), 'yyyy-MM-dd');
      const filteredGames = gamesData.filter((game: Game) => {
        // Keep all games from today or future
        if (game.game_date >= todayOnly) {
          return true;
        }
        // For past dates, only show if they're not finished (might be in progress)
        return game.game_status !== 'finished';
      });
      
      setGames(filteredGames);
      
      // Group all predictions by player_id + game_id (all stat types together)
      const groupSafeBets = (bets: Prediction[]) => {
        // Structure: Map<player_id-game_id, Map<stat_type, { safe?, standard? }>>
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
        
        // Convert to array of player prediction objects
        return Array.from(playerGroups.entries()).map(([playerKey, statMap]) => {
          // Get first prediction as base (for player info)
          const firstPred = Array.from(statMap.values())[0]?.safe || Array.from(statMap.values())[0]?.standard;
          if (!firstPred) return null;
          
          // Build stats object
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
            stats, // Object with stat_type as keys
          };
        }).filter(Boolean);
      };
      
      setSafeBets(groupSafeBets(safeBetsData));
      setLongShots(longShotsData);
      setSuggestedBets(suggestedBetsData);
      setSuggestedParlays(suggestedParlaysData);
      setSafeLongParlays(safeLongParlaysData);
      setBuilderPlays(builderPlaysData);
    } catch (error) {
      console.error('Error loading data:', error);
    } finally {
      setLoading(false);
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

  const handleGeneratePredictions = async () => {
    setGenerating(true);
    setGenerationProgress({ progress: 0, message: 'Starting prediction generation...' });
    try {
      const result = await apiService.generatePredictions(
        undefined, 
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

  const handleFullUpdate = async () => {
    if (!confirm('Run full update? This will update everything (box scores, stats, analytics, injuries, predictions). This takes 2-5 minutes. Continue?')) {
      return;
    }

    setRunningUpdate(true);
    setUpdateStatus('Running full update (this may take 2-5 minutes)...');
    setUpdateProgress({ message: 'Starting...', progress: 0 });
    try {
      const result = await apiService.runFullUpdate((progress) => {
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
      <GenerationProgress progress={generationProgress} />

      {/* Quick Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-white rounded-lg shadow p-6">
          <div className="text-sm font-medium text-gray-500">Games Today</div>
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
        <h2 className="text-xl font-semibold text-gray-900 mb-4">⭐ Suggested Bets</h2>
        {suggestedBets.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {suggestedBets.map((bet) => (
              <div
                key={bet.prediction_id}
                className="bg-white rounded-lg shadow p-4 hover:shadow-md transition-shadow relative"
              >
                <button
                  onClick={() => handleAddToParlay(bet as Prediction)}
                  className="absolute top-2 right-2 w-8 h-8 bg-purple-600 text-white rounded-full hover:bg-purple-700 flex items-center justify-center text-lg font-bold shadow-md z-[60]"
                  title="Add to parlay"
                >
                  +
                </button>
                <div className="flex justify-between items-start mb-2 pr-10">
                  <div>
                    <div className="font-semibold text-gray-900">{bet.player_name}</div>
                    <div className="text-sm text-gray-500">
                      {bet.player_team} • {bet.stat_type}
                    </div>
                  </div>
                  <span className={`px-2 py-1 rounded text-xs font-medium ${
                    bet.bet_type === 'safe' ? 'bg-green-100 text-green-800' :
                    bet.bet_type === 'standard' ? 'bg-blue-100 text-blue-800' :
                    'bg-orange-100 text-orange-800'
                  }`}>
                    {bet.bet_type}
                  </span>
                </div>
                <div className="mt-2 space-y-1">
                  <div className="text-sm">
                    <span className="font-medium">Line:</span> {bet.stat_type === 'points' ? 'PTS' : bet.stat_type === 'rebounds' ? 'REB' : 'AST'} {bet.line > 0 ? 'Over' : 'Under'} {Math.abs(bet.line)}
                  </div>
                  <div className="text-sm">
                    <span className="font-medium">Probability:</span> {(bet.probability * 100).toFixed(1)}%
                  </div>
                  <div className="text-xs text-gray-500">
                    Confidence: {bet.confidence_level} • Volatility: {bet.volatility_level}
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="bg-white rounded-lg shadow p-8 text-center">
            <p className="text-gray-500 mb-2">No suggested bets available yet.</p>
            <p className="text-sm text-gray-400">
              {games.length > 0 
                ? "Click 'Generate Predictions' above to create predictions for today's games."
                : "No games scheduled for this date."}
            </p>
          </div>
        )}
      </div>

      {/* Safe Long Parlays (10-15 legs) */}
      <div>
        <h2 className="text-xl font-semibold text-gray-900 mb-4">🎰 Safe Long Parlays (10-15 Legs)</h2>
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
                        {leg.stat_type === 'points' ? 'PTS' : leg.stat_type === 'rebounds' ? 'REB' : 'AST'} Over {leg.line} 
                        <span className="ml-2 text-green-600 font-semibold">
                          {(leg.probability * 100).toFixed(0)}%
                        </span>
                      </div>
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
        <h2 className="text-xl font-semibold text-gray-900 mb-4">💰 Builder Plays - Double Your Money</h2>
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
                        {leg.stat_type === 'points' ? 'PTS' : leg.stat_type === 'rebounds' ? 'REB' : 'AST'} {leg.bet_line} • 
                        <span className="ml-2 text-green-600 font-semibold">
                          {(leg.probability * 100).toFixed(0)}%
                        </span>
                      </div>
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
        <h2 className="text-xl font-semibold text-gray-900 mb-4">🎯 Suggested Parlays (2-4 Legs)</h2>
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
                        {leg.stat_type === 'points' ? 'PTS' : leg.stat_type === 'rebounds' ? 'REB' : 'AST'} Over {leg.line} • {leg.bet_type} • {(leg.probability * 100).toFixed(1)}%
                      </div>
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

