import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { format } from 'date-fns';
import apiService, { Game } from '../services/api';
import { parseDateString } from '../utils/dateUtils';
import { useSport } from '../contexts/SportContext';

export default function GamesList() {
  const { sport } = useSport();
  const [selectedDate, setSelectedDate] = useState(format(new Date(), 'yyyy-MM-dd'));
  const [games, setGames] = useState<Game[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<'all' | 'scheduled' | 'finished'>('all');

  useEffect(() => {
    loadGames();
  }, [selectedDate, filter, sport]);

  const loadGames = async () => {
    setLoading(true);
    try {
      const status = filter === 'all' ? undefined : filter;
      const gamesData = await apiService.getGames(selectedDate, status, sport);
      setGames(gamesData);
    } catch (error) {
      console.error('Error loading games:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center h-64">
        <div className="text-gray-500">Loading games...</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Games</h1>
          <p className="mt-1 text-sm text-gray-500">Browse all NBA games</p>
        </div>
        <input
          type="date"
          value={selectedDate}
          onChange={(e) => setSelectedDate(e.target.value)}
          className="px-4 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
        />
      </div>

      {/* Filters */}
      <div className="flex gap-2">
        <button
          onClick={() => setFilter('all')}
          className={`px-4 py-2 rounded-md ${
            filter === 'all'
              ? 'bg-primary-600 text-white'
              : 'bg-white text-gray-700 hover:bg-gray-100'
          }`}
        >
          All
        </button>
        <button
          onClick={() => setFilter('scheduled')}
          className={`px-4 py-2 rounded-md ${
            filter === 'scheduled'
              ? 'bg-primary-600 text-white'
              : 'bg-white text-gray-700 hover:bg-gray-100'
          }`}
        >
          Scheduled
        </button>
        <button
          onClick={() => setFilter('finished')}
          className={`px-4 py-2 rounded-md ${
            filter === 'finished'
              ? 'bg-primary-600 text-white'
              : 'bg-white text-gray-700 hover:bg-gray-100'
          }`}
        >
          Finished
        </button>
      </div>

      {/* Games List */}
      {games.length === 0 ? (
        <div className="bg-white rounded-lg shadow p-8 text-center text-gray-500">
          No games found for this date
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
                <div className="flex-1">
                  <div className="flex items-center gap-4">
                    <div className="text-lg font-semibold text-gray-900">
                      {game.away_team_abbreviation} @ {game.home_team_abbreviation}
                    </div>
                    <span className={`px-2 py-1 text-xs rounded-full ${
                      game.game_status === 'finished'
                        ? 'bg-green-100 text-green-800'
                        : game.game_status === 'in_progress'
                        ? 'bg-blue-100 text-blue-800'
                        : 'bg-gray-100 text-gray-800'
                    }`}>
                      {game.game_status}
                    </span>
                  </div>
                  <div className="text-sm text-gray-500 mt-1">
                    {format(parseDateString(game.game_date), 'MMM d, yyyy')}
                    {game.home_score !== null && game.away_score !== null && (
                      <span className="ml-4">
                        {game.away_score} - {game.home_score}
                      </span>
                    )}
                  </div>
                </div>
                <div className="flex gap-4 items-center">
                  {game.prediction_count !== undefined && game.prediction_count > 0 && (
                    <div className="text-sm text-gray-500">
                      {game.prediction_count} predictions
                    </div>
                  )}
                  <span className="text-gray-400">→</span>
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

