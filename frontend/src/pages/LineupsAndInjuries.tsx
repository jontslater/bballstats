import { useState, useEffect } from 'react';
import { format } from 'date-fns';
import apiService from '../services/api';
import { Game } from '../services/api';

interface Injury {
  injury_id: number;
  player_id: number;
  player_name: string;
  status: string;
  injury_type?: string;
  injury_date?: string;
  expected_return_date?: string;
  description?: string;
}

interface Lineup {
  team_id: number;
  team_name: string;
  team_abbreviation: string;
  is_confirmed: boolean;
  starters: Array<{
    player_id: number;
    player_name: string;
    position: string;
    confirmed_at?: string;
  }>;
  bench?: Array<{
    player_id: number;
    player_name: string;
    position: string;
    confirmed_at?: string;
  }>;
}

export default function LineupsAndInjuries() {
  const [injuries, setInjuries] = useState<Injury[]>([]);
  const [games, setGames] = useState<Game[]>([]);
  const [lineups, setLineups] = useState<Record<number, Record<number, Lineup>>>({});
  const [selectedGameId, setSelectedGameId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedTeamId, setSelectedTeamId] = useState<number | null>(null);

  useEffect(() => {
    loadData();
  }, []);

  useEffect(() => {
    if (selectedGameId) {
      loadLineups(selectedGameId);
    }
  }, [selectedGameId]);

  const loadData = async () => {
    try {
      setLoading(true);
      
      // Load injuries
      try {
        const injuriesData = await apiService.getInjuries();
        console.log('Injuries loaded:', injuriesData.length);
        setInjuries(injuriesData || []);
      } catch (injuryError) {
        console.error('Error loading injuries:', injuryError);
        setInjuries([]);
      }
      
      // Load today's games - use the exact same method as Dashboard
      // Use date-fns format to avoid timezone issues (toISOString can cause date shifts)
      const todayDate = format(new Date(), 'yyyy-MM-dd');
      const gamesData = await apiService.getGames(todayDate);
      
      // Filter to only scheduled and in_progress games (exclude finished)
      const activeGames = gamesData.filter(game => 
        game.game_status === 'scheduled' || game.game_status === 'in_progress'
      );
      
      console.log('Games loaded:', activeGames.length);
      setGames(activeGames);
      
      // Load lineups for first game if available
      if (activeGames.length > 0) {
        setSelectedGameId(activeGames[0].game_id);
      }
    } catch (error) {
      console.error('Error loading data:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadLineups = async (gameId: number) => {
    try {
      console.log('Loading lineups for game:', gameId);
      const lineupsData = await apiService.getGameLineups(gameId);
      console.log('Lineups data:', lineupsData);
      setLineups(prev => ({
        ...prev,
        [gameId]: lineupsData
      }));
    } catch (error) {
      console.error('Error loading lineups:', error);
      // Set empty lineups on error so UI doesn't show "Loading..."
      setLineups(prev => ({
        ...prev,
        [gameId]: {}
      }));
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'Out':
        return 'bg-red-100 text-red-800';
      case 'Doubtful':
        return 'bg-orange-100 text-orange-800';
      case 'Questionable':
        return 'bg-yellow-100 text-yellow-800';
      case 'Probable':
        return 'bg-blue-100 text-blue-800';
      case 'Available':
        return 'bg-green-100 text-green-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  const filteredInjuries = selectedTeamId
    ? injuries.filter(inj => {
        // Find player's team from games
        const game = games.find(g => 
          g.home_team_id === selectedTeamId || g.away_team_id === selectedTeamId
        );
        return game !== undefined;
      })
    : injuries;

  // Get unique teams from games
  const uniqueTeams = Array.from(
    new Map(
      games.flatMap(game => [
        [game.home_team_id, { id: game.home_team_id, name: game.home_team_name || game.home_team_abbreviation }],
        [game.away_team_id, { id: game.away_team_id, name: game.away_team_name || game.away_team_abbreviation }]
      ])
    ).values()
  );

  const selectedGame = games.find(g => g.game_id === selectedGameId);
  const gameLineups = selectedGameId ? lineups[selectedGameId] : null;

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
          <h1 className="text-3xl font-bold text-gray-900">Lineups & Injuries</h1>
          <p className="text-sm text-gray-500 mt-1">
            Showing games for {format(new Date(), 'MMMM d, yyyy')}
          </p>
        </div>
        <button
          onClick={loadData}
          className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700"
        >
          Refresh
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Injuries Section */}
        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-2xl font-bold text-gray-900">Injuries</h2>
            <select
              value={selectedTeamId || ''}
              onChange={(e) => setSelectedTeamId(e.target.value ? parseInt(e.target.value) : null)}
              className="px-3 py-1 border border-gray-300 rounded-md text-sm"
            >
              <option value="">All Teams</option>
              {uniqueTeams.map(team => (
                <option key={team.id} value={team.id}>
                  {team.name}
                </option>
              ))}
            </select>
          </div>

          {filteredInjuries.length === 0 ? (
            <div className="text-gray-500 text-center py-8">
              No active injuries found
            </div>
          ) : (
            <div className="space-y-3">
              {filteredInjuries.map(injury => (
                <div
                  key={injury.injury_id}
                  className="border border-gray-200 rounded-lg p-4 hover:bg-gray-50"
                >
                  <div className="flex justify-between items-start">
                    <div className="flex-1">
                      <div className="font-semibold text-gray-900">{injury.player_name}</div>
                      {injury.injury_type && (
                        <div className="text-sm text-gray-600 mt-1">{injury.injury_type}</div>
                      )}
                      {injury.description && (
                        <div className="text-sm text-gray-500 mt-1">{injury.description}</div>
                      )}
                      {injury.expected_return_date && (
                        <div className="text-xs text-gray-400 mt-1">
                          Expected return: {new Date(injury.expected_return_date).toLocaleDateString()}
                        </div>
                      )}
                    </div>
                    <span className={`px-3 py-1 rounded-full text-xs font-semibold ${getStatusColor(injury.status)}`}>
                      {injury.status}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Lineups Section */}
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-2xl font-bold text-gray-900 mb-4">Lineups</h2>

          {games.length === 0 ? (
            <div className="text-gray-500 text-center py-8">
              <div>No games found for today</div>
              <div className="text-xs mt-2">Make sure games are updated in the database</div>
            </div>
          ) : (
            <div className="space-y-4">
              {/* Game Selector */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Select Game
                </label>
                <select
                  value={selectedGameId || ''}
                  onChange={(e) => setSelectedGameId(parseInt(e.target.value))}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md"
                >
                  {games.map(game => (
                    <option key={game.game_id} value={game.game_id}>
                      {game.away_team_abbreviation || game.away_team_name} @ {game.home_team_abbreviation || game.home_team_name} - {new Date(game.game_date).toLocaleDateString()}
                    </option>
                  ))}
                </select>
              </div>

              {/* Lineup Display */}
              {selectedGame && gameLineups && Object.keys(gameLineups).length > 0 ? (
                <div className="space-y-4">
                  {Object.values(gameLineups).map((lineup) => (
                    <div key={lineup.team_id} className="border border-gray-200 rounded-lg p-4">
                      <div className="flex justify-between items-center mb-3">
                        <h3 className="font-bold text-lg text-gray-900">
                          {lineup.team_abbreviation || lineup.team_name}
                        </h3>
                        <span className={`px-3 py-1 rounded-full text-xs font-semibold ${
                          lineup.is_confirmed 
                            ? 'bg-green-100 text-green-800' 
                            : 'bg-yellow-100 text-yellow-800'
                        }`}>
                          {lineup.is_confirmed ? 'Confirmed' : 'Not Confirmed'}
                        </span>
                      </div>

                      {lineup.starters && lineup.starters.length === 0 ? (
                        <div className="text-gray-500 text-sm">No lineup data available</div>
                      ) : lineup.starters && lineup.starters.length > 0 ? (
                        <>
                          <div className="mb-3">
                            <div className="text-xs font-semibold text-gray-600 mb-2">STARTING LINEUP</div>
                            <div className="grid grid-cols-5 gap-2">
                              {lineup.starters.map((starter, idx) => (
                                <div
                                  key={`${lineup.team_id}-starter-${starter.player_id}-${idx}`}
                                  className="text-center p-2 bg-blue-50 rounded border border-blue-200"
                                >
                                  <div className="text-xs text-gray-500 mb-1">{starter.position || 'N/A'}</div>
                                  <div className="text-sm font-medium text-gray-900">
                                    {starter.player_name}
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                          
                          {lineup.bench && lineup.bench.length > 0 && (
                            <div className="mt-4">
                              <div className="text-xs font-semibold text-gray-600 mb-2">BENCH</div>
                              <div className="grid grid-cols-3 gap-2">
                                {lineup.bench.map((bench_player, idx) => (
                                  <div
                                    key={`${lineup.team_id}-bench-${bench_player.player_id}-${idx}`}
                                    className="text-center p-2 bg-gray-50 rounded border border-gray-200"
                                  >
                                    <div className="text-xs text-gray-500 mb-1">{bench_player.position || 'N/A'}</div>
                                    <div className="text-sm font-medium text-gray-700">
                                      {bench_player.player_name}
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                          
                          {lineup.starters[0]?.confirmed_at && (
                            <div className="text-xs text-gray-400 mt-2">
                              Confirmed: {new Date(lineup.starters[0].confirmed_at).toLocaleString()}
                            </div>
                          )}
                        </>
                      ) : (
                        <div className="text-gray-500 text-sm">No lineup data available</div>
                      )}
                    </div>
                  ))}
                </div>
              ) : selectedGame && gameLineups && Object.keys(gameLineups).length === 0 ? (
                <div className="text-gray-500 text-center py-8">
                  <div>No lineups available for this game</div>
                  <div className="text-xs mt-2">Lineups are typically confirmed 60-120 minutes before tipoff</div>
                </div>
              ) : selectedGame ? (
                <div className="text-gray-500 text-center py-8">
                  Loading lineups...
                </div>
              ) : null}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

