import { useState } from 'react';
import { Prediction } from '../services/api';
import apiService from '../services/api';

interface CreatePlayModalProps {
  prediction: Prediction;
  onClose: () => void;
  onSuccess: () => void;
}

export default function CreatePlayModal({ prediction, onClose, onSuccess }: CreatePlayModalProps) {
  const [betLine, setBetLine] = useState(`Over ${prediction.safe_line.toFixed(1)}`);
  const [notes, setNotes] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      await apiService.createPlay({
        player_id: prediction.player_id,
        game_id: prediction.game_id,
        stat_type: prediction.stat_type,
        bet_line: betLine,
        notes: notes || undefined,
      });
      onSuccess();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to create play');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl max-w-md w-full mx-4">
        <div className="p-6">
          <h2 className="text-2xl font-bold text-gray-900 mb-4">Create Play</h2>
          
          <div className="mb-4">
            <div className="text-sm text-gray-500">Player</div>
            <div className="font-semibold">{prediction.player_name}</div>
          </div>
          
          <div className="mb-4">
            <div className="text-sm text-gray-500">Stat Type</div>
            <div className="font-semibold capitalize">{prediction.stat_type}</div>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="betLine" className="block text-sm font-medium text-gray-700 mb-1">
                Bet Line
              </label>
              <input
                id="betLine"
                type="text"
                value={betLine}
                onChange={(e) => setBetLine(e.target.value)}
                placeholder="e.g., Over 24.5"
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
                required
              />
            </div>

            <div>
              <label htmlFor="notes" className="block text-sm font-medium text-gray-700 mb-1">
                Notes (optional)
              </label>
              <textarea
                id="notes"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                rows={3}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
                placeholder="Add any notes about this play..."
              />
            </div>

            {error && (
              <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">
                {error}
              </div>
            )}

            <div className="flex gap-3 pt-4">
              <button
                type="button"
                onClick={onClose}
                className="flex-1 px-4 py-2 border border-gray-300 rounded-md text-gray-700 hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={loading}
                className="flex-1 px-4 py-2 bg-primary-600 text-white rounded-md hover:bg-primary-700 disabled:opacity-50"
              >
                {loading ? 'Creating...' : 'Create Play'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}





