import { useState } from 'react';
import { format } from 'date-fns';
import apiService from '../services/api';

export default function PredictionManagement() {
  const [updating, setUpdating] = useState(false);
  const [updateResult, setUpdateResult] = useState<any>(null);
  const [updateDate, setUpdateDate] = useState('');
  const [loadingStats, setLoadingStats] = useState(false);
  const [stats, setStats] = useState<any>(null);
  const [curves, setCurves] = useState<any>(null);
  const [showCurves, setShowCurves] = useState(false);

  const handleUpdateResults = async () => {
    setUpdating(true);
    setUpdateResult(null);
    try {
      const result = await apiService.updatePredictionResults(updateDate || undefined);
      setUpdateResult(result);
      
      // Refresh stats after update
      await loadStats();
    } catch (error: any) {
      setUpdateResult({
        error: error.response?.data?.detail || error.message || 'Failed to update results'
      });
    } finally {
      setUpdating(false);
    }
  };

  const loadStats = async () => {
    setLoadingStats(true);
    try {
      const [statsData, curvesData] = await Promise.all([
        apiService.getCalibrationStats(),
        apiService.getCalibrationCurves()
      ]);
      setStats(statsData);
      setCurves(curvesData);
    } catch (error: any) {
      console.error('Error loading stats:', error);
    } finally {
      setLoadingStats(false);
    }
  };

  const handleLoadStats = async () => {
    await loadStats();
    setShowCurves(true);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-gray-900">Prediction Management</h1>
        <p className="mt-1 text-sm text-gray-500">
          Update predictions with actual results and view calibration statistics
        </p>
      </div>

      {/* Update Results Section */}
      <div className="bg-white rounded-lg shadow-md p-6">
        <h2 className="text-xl font-semibold text-gray-900 mb-4">Update Prediction Results</h2>
        <p className="text-sm text-gray-600 mb-4">
          Update predictions with actual game results. Leave date empty to update all finished games.
        </p>
        
        <div className="flex gap-4 items-end">
          <div className="flex-1">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Game Date (Optional)
            </label>
            <input
              type="date"
              value={updateDate}
              onChange={(e) => setUpdateDate(e.target.value)}
              className="px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
          </div>
          <button
            onClick={handleUpdateResults}
            disabled={updating}
            className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {updating ? 'Updating...' : 'Update Results'}
          </button>
        </div>

        {updateResult && (
          <div className={`mt-4 p-4 rounded-md ${
            updateResult.error ? 'bg-red-50 border border-red-200' : 'bg-green-50 border border-green-200'
          }`}>
            {updateResult.error ? (
              <div className="text-red-800">
                <p className="font-semibold">Error:</p>
                <p>{updateResult.error}</p>
              </div>
            ) : (
              <div className="text-green-800">
                <p className="font-semibold mb-2">✅ Update Complete!</p>
                <ul className="list-disc list-inside space-y-1">
                  <li><strong>Total processed:</strong> {updateResult.total}</li>
                  <li className="text-green-700"><strong>✅ Updated:</strong> {updateResult.updated}</li>
                  <li className="text-yellow-700"><strong>⏭️ Skipped:</strong> {updateResult.skipped}</li>
                  {updateResult.skipped_details && (
                    <ul className="list-none ml-4 mt-1 space-y-1 text-sm">
                      <li>• No player stat record (player didn't play): {updateResult.skipped_details.no_stat_record || 0}</li>
                      <li>• No stat value (NULL): {updateResult.skipped_details.no_value || 0}</li>
                      <li>• Unsupported stat type: {updateResult.skipped_details.unsupported_type || 0}</li>
                    </ul>
                  )}
                  {updateResult.errors > 0 && (
                    <li className="text-red-700"><strong>❌ Errors:</strong> {updateResult.errors}</li>
                  )}
                </ul>
                {updateResult.skipped > 0 && updateResult.updated === 0 && (
                  <div className="mt-3 p-3 bg-yellow-50 border border-yellow-300 rounded text-yellow-800 text-sm">
                    <p><strong>Note:</strong> All predictions were skipped, likely because:</p>
                    <ul className="list-disc list-inside mt-1 space-y-1">
                      <li>Predictions are for players who didn't play (DNP - Did Not Play)</li>
                      <li>Game results haven't been collected yet for those games</li>
                    </ul>
                    <p className="mt-2">If you have historical data, make sure game results are collected first using the game results collection script.</p>
                  </div>
                )}
                {updateResult.updated > 0 && (
                  <div className="mt-3 p-3 bg-blue-50 border border-blue-300 rounded text-blue-800 text-sm">
                    <p><strong>✅ Success!</strong> {updateResult.updated} predictions were updated with actual results.</p>
                    <p className="mt-1">Click "Load Statistics" below to see updated calibration statistics.</p>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Calibration Statistics Section */}
      <div className="bg-white rounded-lg shadow-md p-6">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-semibold text-gray-900">Calibration Statistics</h2>
          <button
            onClick={handleLoadStats}
            disabled={loadingStats}
            className="px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loadingStats ? 'Loading...' : 'Load Statistics'}
          </button>
        </div>
        <p className="text-sm text-gray-600 mb-4">
          View how accurate predictions are compared to actual outcomes. Based on last 90 days of data.
        </p>

        {stats && (
          <div className="space-y-6">
            {(['safe', 'standard', 'long_shot'] as const).map((betType) => {
              const data = stats[betType];
              if (!data || data.total === 0) return null;

              const hitRate = data.hit_rate * 100;
              const avgProb = data.avg_prob * 100;
              const diff = (hitRate - avgProb);
              // If actual < predicted, we're OVER-confident (predicted too high)
              // If actual > predicted, we're UNDER-confident (predicted too low)
              const isOverConfident = diff < 0;

              return (
                <div key={betType} className="border border-gray-200 rounded-lg p-4">
                  <h3 className="text-lg font-semibold text-gray-900 mb-3 capitalize">
                    {betType} Bets
                  </h3>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div>
                      <p className="text-sm text-gray-600">Total Predictions</p>
                      <p className="text-2xl font-bold text-gray-900">{data.total}</p>
                    </div>
                    <div>
                      <p className="text-sm text-gray-600">Actual Hit Rate</p>
                      <p className="text-2xl font-bold text-blue-600">{hitRate.toFixed(1)}%</p>
                    </div>
                    <div>
                      <p className="text-sm text-gray-600">Avg Predicted</p>
                      <p className="text-2xl font-bold text-gray-700">{avgProb.toFixed(1)}%</p>
                    </div>
                    <div>
                      <p className="text-sm text-gray-600">Difference</p>
                      <p className={`text-2xl font-bold ${isOverConfident ? 'text-red-600' : 'text-green-600'}`}>
                        {diff > 0 ? '+' : ''}{diff.toFixed(1)}%
                      </p>
                      <p className="text-xs text-gray-500">
                        {isOverConfident ? 'Over-confident (predicted too high)' : 'Under-confident (predicted too low)'}
                      </p>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {showCurves && curves && Object.keys(curves).some(key => Object.keys(curves[key]).length > 0) && (
          <div className="mt-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Calibration Curves</h3>
            <div className="space-y-6">
              {(['safe', 'standard', 'long_shot'] as const).map((betType) => {
                if (!curves[betType] || Object.keys(curves[betType]).length === 0) return null;

                return (
                  <div key={betType} className="border border-gray-200 rounded-lg p-4">
                    <h4 className="font-semibold text-gray-900 mb-3 capitalize">{betType} Bets</h4>
                    <div className="overflow-x-auto">
                      <table className="min-w-full divide-y divide-gray-200">
                        <thead className="bg-gray-50">
                          <tr>
                            <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Range</th>
                            <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Sample</th>
                            <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Predicted</th>
                            <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Actual</th>
                            <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Adjustment</th>
                          </tr>
                        </thead>
                        <tbody className="bg-white divide-y divide-gray-200">
                          {Object.entries(curves[betType])
                            .sort(([a], [b]) => a.localeCompare(b))
                            .map(([rangeLabel, calData]: [string, any]) => (
                              <tr key={rangeLabel}>
                                <td className="px-4 py-2 text-sm text-gray-900">{rangeLabel}</td>
                                <td className="px-4 py-2 text-sm text-gray-600">{calData.sample_size}</td>
                                <td className="px-4 py-2 text-sm text-gray-600">{(calData.predicted_probability * 100).toFixed(1)}%</td>
                                <td className="px-4 py-2 text-sm text-gray-600">{(calData.actual_hit_rate * 100).toFixed(1)}%</td>
                                <td className={`px-4 py-2 text-sm font-medium ${
                                  calData.calibration_adjustment >= 0 ? 'text-green-600' : 'text-red-600'
                                }`}>
                                  {calData.calibration_adjustment > 0 ? '+' : ''}{(calData.calibration_adjustment * 100).toFixed(1)}%
                                </td>
                              </tr>
                            ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {showCurves && curves && Object.keys(curves).every(key => Object.keys(curves[key]).length === 0) && (
          <div className="mt-4 p-4 bg-yellow-50 border border-yellow-200 rounded-md">
            <p className="text-yellow-800">
              No calibration data available yet. Update prediction results first to build calibration curves.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

