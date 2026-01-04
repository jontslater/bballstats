import { useState, useEffect } from 'react';
import { Prediction } from '../services/api';
import apiService from '../services/api';

interface ParlayBuilderProps {
  isOpen: boolean;
  onClose: () => void;
}

interface ParlayItem extends Prediction {
  betLine: string;
  betLineValue: number; // The actual number value
  betType: 'Over' | 'Under'; // Over or Under
  probability: number;
}

interface EditBetLineModalProps {
  prediction: Prediction | null;
  currentBetLine?: string;
  onSave: (betLine: string, betLineValue: number, betType: 'Over' | 'Under') => void;
  onCancel: () => void;
}

function EditBetLineModal({ prediction, currentBetLine, onSave, onCancel }: EditBetLineModalProps) {
  const [betType, setBetType] = useState<'Over' | 'Under'>('Over');
  const [betValue, setBetValue] = useState<string>('');

  useEffect(() => {
    if (prediction) {
      // Parse current bet line if provided
      if (currentBetLine) {
        const isOver = currentBetLine.startsWith('Over');
        const value = parseFloat(currentBetLine.replace(/Over|Under/g, '').trim());
        setBetType(isOver ? 'Over' : 'Under');
        setBetValue(value.toString());
      } else {
        // Set default based on bet_type
        let defaultValue = 0;
        if (prediction.bet_type === 'safe' && prediction.safe_line) {
          defaultValue = prediction.safe_line;
        } else if (prediction.bet_type === 'standard' && prediction.standard_line) {
          defaultValue = prediction.standard_line;
        } else if (prediction.bet_type === 'long_shot' && prediction.long_shot_line) {
          defaultValue = prediction.long_shot_line;
        } else {
          defaultValue = prediction.distribution_mean;
        }
        setBetValue(defaultValue.toFixed(1));
      }
    }
  }, [prediction, currentBetLine]);

  if (!prediction) return null;

  const handleSave = () => {
    const numValue = parseFloat(betValue);
    if (isNaN(numValue)) {
      alert('Please enter a valid number');
      return;
    }
    onSave(`${betType} ${numValue.toFixed(1)}`, numValue, betType);
  };

  return (
    <div 
      className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-[100] pointer-events-auto"
      onClick={(e) => {
        // Close if clicking the backdrop
        if (e.target === e.currentTarget) {
          onCancel();
        }
      }}
    >
      <div 
        className="bg-white rounded-lg shadow-xl max-w-md w-full mx-4 p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-xl font-bold text-gray-900 mb-4">Set Bet Line</h3>
        
        <div className="mb-4">
          <div className="text-sm text-gray-500 mb-1">Player</div>
          <div className="font-semibold text-gray-900">{prediction.player_name}</div>
        </div>

        <div className="mb-4">
          <div className="text-sm text-gray-500 mb-1">Stat Type</div>
          <div className="font-semibold text-gray-900 capitalize">
            {prediction.stat_type === 'points' ? 'Points' : 
             prediction.stat_type === 'rebounds' ? 'Rebounds' : 
             'Assists'}
          </div>
        </div>

        <div className="mb-4">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Bet Type
          </label>
          <div className="flex gap-2">
            <button
              onClick={() => setBetType('Over')}
              className={`flex-1 px-4 py-2 rounded-md ${
                betType === 'Over'
                  ? 'bg-green-600 text-white'
                  : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
              }`}
            >
              Over
            </button>
            <button
              onClick={() => setBetType('Under')}
              className={`flex-1 px-4 py-2 rounded-md ${
                betType === 'Under'
                  ? 'bg-red-600 text-white'
                  : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
              }`}
            >
              Under
            </button>
          </div>
        </div>

        <div className="mb-4">
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Line Value
          </label>
          <input
            type="number"
            step="0.5"
            value={betValue}
            onChange={(e) => setBetValue(e.target.value)}
            placeholder="e.g., 6.0"
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
            autoFocus
          />
          <div className="text-xs text-gray-500 mt-1">
            Suggested: {prediction.bet_type === 'safe' && prediction.safe_line ? prediction.safe_line.toFixed(1) :
                        prediction.bet_type === 'standard' && prediction.standard_line ? prediction.standard_line.toFixed(1) :
                        prediction.bet_type === 'long_shot' && prediction.long_shot_line ? prediction.long_shot_line.toFixed(1) :
                        prediction.distribution_mean.toFixed(1)}
          </div>
        </div>

        <div className="flex gap-2">
          <button
            onClick={onCancel}
            className="flex-1 px-4 py-2 bg-gray-200 text-gray-700 rounded-md hover:bg-gray-300"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            className="flex-1 px-4 py-2 bg-primary-600 text-white rounded-md hover:bg-primary-700"
          >
            Save
          </button>
        </div>
      </div>
    </div>
  );
}

export default function ParlayBuilder({ isOpen, onClose }: ParlayBuilderProps) {
  const [parlayItems, setParlayItems] = useState<ParlayItem[]>([]);
  const [parlayName, setParlayName] = useState('');
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);
  const [editingItem, setEditingItem] = useState<Prediction | null>(null);
  const [editingItemIndex, setEditingItemIndex] = useState<number | null>(null);
  const [pendingPrediction, setPendingPrediction] = useState<Prediction | null>(null);

  // Load parlay from localStorage on mount
  useEffect(() => {
    const saved = localStorage.getItem('parlayBuilder');
    if (saved) {
      try {
        setParlayItems(JSON.parse(saved));
      } catch (e) {
        console.error('Error loading parlay from localStorage:', e);
      }
    }
  }, []);

  // Save parlay to localStorage whenever it changes
  useEffect(() => {
    if (parlayItems.length > 0) {
      localStorage.setItem('parlayBuilder', JSON.stringify(parlayItems));
    } else {
      localStorage.removeItem('parlayBuilder');
    }
  }, [parlayItems]);

  // Listen for add-to-parlay events
  useEffect(() => {
    const handleAddToParlay = (event: CustomEvent<Prediction>) => {
      const prediction = event.detail;
      
      // Check if already in parlay
      // Allow same player with different stat types (e.g., LeBron points, LeBron rebounds)
      // Check by player_id, game_id, stat_type, and bet_line to allow duplicates with different stats
      const isDuplicate = parlayItems.some(item => {
        // Same player, game, stat type, and bet line = duplicate
        return item.player_id === prediction.player_id &&
               item.game_id === prediction.game_id &&
               item.stat_type === prediction.stat_type &&
               item.betLine === (prediction.bet_line || prediction.betLine);
      });
      
      if (isDuplicate) {
        return; // Already added
      }
      
      // Also check by prediction_id for regular predictions (but allow different stat types)
      if (prediction.prediction_id && prediction.prediction_id > 0 && !prediction.advanced_bet_type) {
        // Only skip if it's the exact same prediction (same prediction_id AND same stat_type)
        if (parlayItems.some(item => 
          item.prediction_id === prediction.prediction_id &&
          item.stat_type === prediction.stat_type
        )) {
          return; // Already added
        }
      }

      // For advanced bets that already have a bet_line, add directly without showing modal
      if (prediction.advanced_bet_type && (prediction.bet_line || prediction.betLine)) {
        const betLine = prediction.bet_line || prediction.betLine || '';
        const betLineValue = parseFloat(betLine.replace(/Over|Under/g, '').trim()) || 0;
        const betType = betLine.startsWith('Over') ? 'Over' : 'Under';
        const probability = prediction.safe_probability || prediction.probability || 0.5;
        
        const newItem: ParlayItem = {
          ...prediction,
          betLine,
          betLineValue,
          betType,
          probability,
        };
        
        setParlayItems(prev => [...prev, newItem]);
        return;
      }

      // Show modal to set bet line for regular predictions
      setPendingPrediction(prediction);
    };

    window.addEventListener('addToParlay' as any, handleAddToParlay as EventListener);
    return () => {
      window.removeEventListener('addToParlay' as any, handleAddToParlay as EventListener);
    };
  }, [parlayItems]);

  const handleSaveBetLine = (betLine: string, betLineValue: number, betType: 'Over' | 'Under') => {
    if (pendingPrediction) {
      // Calculate probability based on the bet line
      // For advanced bets, use the probability from the bet data
      let probability = 0;
      if (pendingPrediction.advanced_bet_type) {
        // Use probability from advanced bet
        probability = pendingPrediction.safe_probability || pendingPrediction.probability || 0.5;
      } else if (pendingPrediction.bet_type === 'safe' && pendingPrediction.safe_probability) {
        probability = pendingPrediction.safe_probability;
      } else if (pendingPrediction.bet_type === 'standard' && pendingPrediction.standard_probability) {
        probability = pendingPrediction.standard_probability;
      } else if (pendingPrediction.bet_type === 'long_shot' && pendingPrediction.long_shot_probability) {
        probability = pendingPrediction.long_shot_probability;
      } else {
        probability = pendingPrediction.safe_probability || 0.5;
      }

      const newItem: ParlayItem = {
        ...pendingPrediction,
        betLine,
        betLineValue,
        betType,
        probability,
      };

      setParlayItems(prev => [...prev, newItem]);
      setPendingPrediction(null);
    } else if (editingItemIndex !== null && editingItem) {
      // Update existing item
      setParlayItems(prev => prev.map((item, idx) => 
        idx === editingItemIndex 
          ? { ...item, betLine, betLineValue, betType }
          : item
      ));
      setEditingItem(null);
      setEditingItemIndex(null);
    }
  };

  const handleCancelEdit = () => {
    setPendingPrediction(null);
    setEditingItem(null);
    setEditingItemIndex(null);
  };

  const handleEditItem = (item: ParlayItem, index: number) => {
    setEditingItem(item);
    setEditingItemIndex(index);
  };

  const removeItem = (predictionId: number) => {
    setParlayItems(prev => prev.filter(item => item.prediction_id !== predictionId));
  };

  const handleTextToParlay = async () => {
    const textInput = document.getElementById('text-parlay-input') as HTMLTextAreaElement;
    const text = textInput?.value.trim();
    
    if (!text) {
      alert('Please enter parlay text');
      return;
    }

    try {
      // First, try to parse and match the text
      const parseResult = await apiService.parseTextToBets({ text });
      
      if (parseResult.matched_bets.length === 0) {
        alert(`Could not match any bets. Make sure players have predictions for today's games.`);
        return;
      }

      // If 1 or more bets, add them all to the parlay builder
      // (We'll create a parlay if there are 2+ bets, but first add them to builder)
      if (parseResult.matched_bets.length >= 1) {
        let addedCount = 0;
        let skippedCount = 0;
        
        for (const bet of parseResult.matched_bets) {
          // Create a prediction-like object and add it to the builder
          const predictionLike = {
            player_id: bet.player_id,
            game_id: bet.game_id,
            stat_type: bet.stat_type,
            bet_line: bet.bet_line,
            player_name: bet.player_name,
            distribution_mean: bet.matched_line || 0,
            safe_probability: bet.confidence || 0.75,
            bet_type: 'standard',
            prediction_id: bet.prediction_id || -1,
            game_date: bet.game_date
          };
          
          // Check if this bet is already in the parlay builder
          const isDuplicate = parlayItems.some(item => 
            item.player_id === bet.player_id &&
            item.game_id === bet.game_id &&
            item.stat_type === bet.stat_type &&
            item.betLine === bet.bet_line
          );
          
          if (!isDuplicate) {
            // Add directly to parlay builder (text-to-parlay bets already have bet_line set)
            const betLine = bet.bet_line;
            const betLineValue = parseFloat(betLine.replace(/Over|Under/g, '').trim()) || 0;
            const betType = betLine.startsWith('Over') ? 'Over' : 'Under';
            const probability = bet.confidence || 0.75;
            
            const newItem: ParlayItem = {
              ...predictionLike,
              betLine,
              betLineValue,
              betType,
              probability,
            };
            
            setParlayItems(prev => [...prev, newItem]);
            addedCount++;
          } else {
            skippedCount++;
          }
        }
        
        // Clear text input
        if (textInput) {
          textInput.value = '';
        }
        
        const unmatchedCount = parseResult.parsed_count - parseResult.matched_count;
        if (parseResult.matched_bets.length === 1) {
          alert(`Added "${parseResult.matched_bets[0].player_name} ${parseResult.matched_bets[0].bet_line}" to parlay builder. Add more bets to create a parlay.`);
        } else {
          let message = `Added ${addedCount} bet${addedCount !== 1 ? 's' : ''} to parlay builder.`;
          if (skippedCount > 0) {
            message += ` Skipped ${skippedCount} duplicate${skippedCount !== 1 ? 's' : ''}.`;
          }
          if (unmatchedCount > 0) {
            message += ` Could not match ${unmatchedCount} bet${unmatchedCount !== 1 ? 's' : ''}.`;
            // Show detailed info if available
            if (parseResult.unmatched_info && parseResult.unmatched_info.length > 0) {
              const details = parseResult.unmatched_info.map((info: any) => {
                if (!info.matched_player) {
                  return `${info.player_name} (${info.stat_type}) - Player not found`;
                } else if (!info.has_predictions) {
                  return `${info.player_name} (${info.stat_type}) - No predictions (found: ${info.matched_player})`;
                } else {
                  return `${info.player_name} (${info.stat_type}) - Issue matching`;
                }
              }).join('; ');
              message += ` Details: ${details}`;
            } else {
              message += ` (check player names and ensure predictions exist)`;
            }
          }
          if (addedCount >= 2) {
            message += ` You can now save this as a parlay.`;
          } else {
            message += ` Add more bets to create a parlay.`;
          }
          alert(message);
        }
        
        // If we have 2+ bets, don't try to create a parlay automatically
        // Let the user review and save manually
        return;
      }

      // If 2+ bets, create a parlay
      const result = await apiService.createParlayFromText({
        text,
        name: parlayName || undefined,
        notes: notes || undefined,
      });

      alert(`Parlay created successfully! Matched ${result.matched_count} out of ${result.parsed_count} bets.`);
      
      // Clear text input
      if (textInput) {
        textInput.value = '';
      }
      
      // Close builder and refresh
      onClose();
      // Trigger a page refresh or reload parlays
      window.location.reload();
    } catch (error: any) {
      console.error('Error creating parlay from text:', error);
      const errorMsg = error.response?.data?.detail || error.message;
      
      // If it's the "need 2 bets" error, offer to add to builder instead
      if (errorMsg.includes('at least 2 bets')) {
        // Try to parse and add to builder
        try {
          const parseResult = await apiService.parseTextToBets({ text });
          if (parseResult.matched_bets.length === 1) {
            const bet = parseResult.matched_bets[0];
            const predictionLike = {
              player_id: bet.player_id,
              game_id: bet.game_id,
              stat_type: bet.stat_type,
              bet_line: bet.bet_line,
              player_name: bet.player_name,
              distribution_mean: bet.matched_line || 0,
              safe_probability: bet.confidence || 0.75,
              bet_type: 'standard',
              prediction_id: bet.prediction_id || -1,
              game_date: bet.game_date
            };
            
            const event = new CustomEvent('addToParlay', { detail: predictionLike });
            window.dispatchEvent(event);
            
            if (textInput) {
              textInput.value = '';
            }
            
            alert(`Added "${bet.player_name} ${bet.bet_line}" to parlay builder. Add more bets to create a parlay.`);
            return;
          }
        } catch (parseError) {
          // Fall through to show original error
        }
      }
      
      alert(errorMsg || 'Failed to create parlay from text. Make sure format is correct: "Player Name Over X.X points, Player Name Over X.X rebounds"');
    }
  };

  const clearParlay = () => {
    if (confirm('Clear all items from parlay?')) {
      setParlayItems([]);
      setParlayName('');
      setNotes('');
    }
  };

  const calculateCombinedProbability = () => {
    if (parlayItems.length === 0) return 0;
    return parlayItems.reduce((acc, item) => acc * item.probability, 1);
  };

  const calculateOdds = (probability: number) => {
    if (probability <= 0 || probability >= 1) return 'N/A';
    const decimalOdds = 1 / probability;
    const americanOdds = (decimalOdds - 1) * 100;
    if (americanOdds >= 0) {
      return `+${Math.round(americanOdds)}`;
    } else {
      return `${Math.round(americanOdds)}`;
    }
  };

  const handleSaveParlay = async () => {
    if (parlayItems.length < 2) {
      alert('Parlay must have at least 2 legs');
      return;
    }

    setSaving(true);
    try {
      // Create plays for each item
      // Items with prediction_id > 0 and no advanced_bet_type are regular predictions (need to create play)
      // Items with advanced_bet_type and prediction_id > 0 might already be saved as plays
      const playPromises = parlayItems.map(async (item) => {
        // Skip team totals (player_id = 0) - they can't be saved as plays
        if (item.player_id === 0) {
          throw new Error('Team totals cannot be saved as individual plays. Please remove team total bets from the parlay.');
        }
        
        // If this is an advanced bet with a prediction_id that's actually a play_id, check if it exists
        if (item.advanced_bet_type && item.prediction_id && item.prediction_id > 0) {
          try {
            const play = await apiService.getPlay(item.prediction_id);
            if (play && play.play_id) {
              return { play_id: play.play_id };
            }
          } catch {
            // Not a play or doesn't exist, continue to create one
          }
        }
        
        // Create a new play for this prediction/advanced bet
        return apiService.createPlay({
          player_id: item.player_id,
          game_id: item.game_id,
          stat_type: item.stat_type,
          bet_line: item.betLine,
          notes: item.advanced_bet_type 
            ? `Advanced bet: ${item.advanced_bet_type}` 
            : `From prediction ${item.prediction_id || 'unknown'}`,
        });
      });

      const plays = await Promise.all(playPromises);
      const playIds = plays.map(p => p.play_id).filter(id => id > 0);

      if (playIds.length < 2) {
        alert('Parlay must have at least 2 valid plays. Some bets could not be saved.');
        setSaving(false);
        return;
      }

      // Then create the parlay
      await apiService.createParlay({
        play_ids: playIds,
        name: parlayName || undefined,
        notes: notes || undefined,
      });

      // Clear the parlay builder
      setParlayItems([]);
      setParlayName('');
      setNotes('');
      localStorage.removeItem('parlayBuilder');

      alert('Parlay saved successfully!');
      onClose();
    } catch (error: any) {
      console.error('Error saving parlay:', error);
      alert(error.message || error.response?.data?.detail || 'Failed to save parlay');
    } finally {
      setSaving(false);
    }
  };

  const combinedProbability = calculateCombinedProbability();
  const odds = calculateOdds(combinedProbability);

  if (!isOpen) return (
    <>
      {/* Edit Bet Line Modal - render even when parlay builder is closed */}
      {(pendingPrediction || editingItem) && (
        <EditBetLineModal
          prediction={pendingPrediction || editingItem}
          currentBetLine={editingItem ? editingItem.betLine : undefined}
          onSave={handleSaveBetLine}
          onCancel={handleCancelEdit}
        />
      )}
    </>
  );

  return (
    <>
      <div 
        className="fixed inset-0 bg-black bg-opacity-50 z-50 flex pointer-events-none"
        onClick={(e) => {
          // Close if clicking the backdrop (not the modal itself)
          if (e.target === e.currentTarget) {
            onClose();
          }
        }}
      >
        <div 
          className="bg-white w-full max-w-md ml-auto shadow-2xl flex flex-col h-full pointer-events-auto"
          onClick={(e) => e.stopPropagation()}
        >
        {/* Header */}
        <div className="p-6 border-b border-gray-200">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-2xl font-bold text-gray-900">Parlay Builder</h2>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-600 text-2xl"
            >
              ×
            </button>
          </div>
          <div className="text-sm text-gray-500">
            {parlayItems.length} {parlayItems.length === 1 ? 'leg' : 'legs'}
          </div>
        </div>

        {/* Text to Parlay Input */}
        <div className="p-6 border-b border-gray-200 bg-blue-50">
          <h3 className="text-sm font-semibold text-gray-700 mb-2">Quick Add from Text</h3>
          <p className="text-xs text-gray-600 mb-3">
            Example: "LeBron Over 25 points, AD Over 10 rebounds, Curry Over 30 points"
          </p>
          <textarea
            id="text-parlay-input"
            placeholder="Type your parlay here..."
            className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
            rows={3}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && e.ctrlKey) {
                handleTextToParlay();
              }
            }}
          />
          <button
            onClick={handleTextToParlay}
            className="mt-2 w-full px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 text-sm"
          >
            Create from Text (Ctrl+Enter)
          </button>
        </div>

        {/* Parlay Items */}
        <div className="flex-1 overflow-y-auto p-6">
          {parlayItems.length === 0 ? (
            <div className="text-center text-gray-500 py-12">
              <div className="text-4xl mb-4">🎯</div>
              <p className="text-lg font-medium mb-2">No bets added yet</p>
              <p className="text-sm">Click the + button on any prediction card to add it to your parlay</p>
            </div>
          ) : (
            <div className="space-y-4">
              {parlayItems.map((item, idx) => (
                <div
                  key={`${item.player_id}-${item.game_id}-${item.stat_type}-${item.betLine}-${idx}`}
                  className="bg-gray-50 rounded-lg p-4 border border-gray-200"
                >
                  <div className="flex justify-between items-start mb-2">
                    <div className="flex-1">
                      <div className="font-semibold text-gray-900">
                        {item.player_name}
                      </div>
                      <div className="text-sm text-gray-600">
                        {item.stat_type === 'points' ? 'PTS' : item.stat_type === 'rebounds' ? 'REB' : 'AST'} • {item.betLine}
                      </div>
                      <div className="text-xs text-gray-500 mt-1">
                        {(item.probability * 100).toFixed(0)}% likely
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <button
                        onClick={() => handleEditItem(item, idx)}
                        className="text-blue-500 hover:text-blue-700 text-sm font-medium"
                        title="Edit bet line"
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => removeItem(item.prediction_id)}
                        className="text-red-500 hover:text-red-700 text-xl font-bold"
                        title="Remove"
                      >
                        ×
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Summary & Actions */}
        {parlayItems.length > 0 && (
          <div className="border-t border-gray-200 p-6 space-y-4">
            {/* Combined Stats */}
            <div className="bg-primary-50 rounded-lg p-4">
              <div className="flex justify-between items-center mb-2">
                <span className="text-sm font-medium text-gray-700">Combined Probability:</span>
                <span className="text-lg font-bold text-primary-600">
                  {(combinedProbability * 100).toFixed(2)}%
                </span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-sm font-medium text-gray-700">Odds:</span>
                <span className="text-lg font-bold text-primary-600">{odds}</span>
              </div>
            </div>

            {/* Name Input */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Parlay Name (optional)
              </label>
              <input
                type="text"
                value={parlayName}
                onChange={(e) => setParlayName(e.target.value)}
                placeholder="e.g., Monday Night Parlay"
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
              />
            </div>

            {/* Notes Input */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Notes (optional)
              </label>
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Add any notes about this parlay..."
                rows={2}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
              />
            </div>

            {/* Action Buttons */}
            <div className="flex gap-2">
              <button
                onClick={clearParlay}
                className="flex-1 px-4 py-2 bg-gray-200 text-gray-700 rounded-md hover:bg-gray-300"
              >
                Clear
              </button>
              <button
                onClick={handleSaveParlay}
                disabled={saving || parlayItems.length < 2}
                className="flex-1 px-4 py-2 bg-primary-600 text-white rounded-md hover:bg-primary-700 disabled:bg-gray-300 disabled:cursor-not-allowed"
              >
                {saving ? 'Saving...' : 'Save Parlay'}
              </button>
            </div>
          </div>
        )}
        </div>
      </div>

      {/* Edit Bet Line Modal - render outside parlay builder */}
      {(pendingPrediction || editingItem) && (
        <EditBetLineModal
          prediction={pendingPrediction || editingItem}
          currentBetLine={editingItem ? editingItem.betLine : undefined}
          onSave={handleSaveBetLine}
          onCancel={handleCancelEdit}
        />
      )}
    </>
  );
}

