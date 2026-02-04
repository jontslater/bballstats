import React from 'react';
import { Last3Game } from '../services/api';

interface Last3GamesProps {
  last3Games?: Last3Game[];
  statType: string;
  isCombo?: boolean; // For combo stats like "points+assists"
  isMilestone?: boolean; // For milestone props (20+ Points, Double-Double, etc.)
  isTeamTotal?: boolean; // For team totals
  threshold?: number; // For milestone props: threshold value (e.g., 20 for "20+ Points")
}

export default function Last3Games({ 
  last3Games, 
  statType, 
  isCombo = false, 
  isMilestone = false,
  isTeamTotal = false,
  threshold 
}: Last3GamesProps) {
  if (!last3Games || last3Games.length === 0) {
    return (
      <div className="text-xs text-gray-400 italic mt-1">
        No recent games
      </div>
    );
  }

  // Get stat label
  const statLabels: { [key: string]: string } = {
    'points': 'PTS',
    'rebounds': 'REB',
    'assists': 'AST',
    'minutes': 'MIN',
    'passing_yards': 'PY',
    'rushing_yards': 'RY',
    'receptions': 'REC',
    'receiving_yards': 'REY',
    'passing_tds': 'PTD',
    'rushing_tds': 'RTD',
    'receiving_tds': 'RETD',
    'points+rebounds': 'P+R',
    'points+assists': 'P+A',
    'rebounds+assists': 'R+A',
  };
  
  // Handle combo stats (e.g., "points+assists")
  let statLabel: string;
  if (isCombo || statType.includes('+')) {
    const normalizedStat = statType.toLowerCase().replace(/\s+/g, '');
    statLabel = statLabels[normalizedStat] || normalizedStat.toUpperCase().replace('+', '+');
  } else {
    statLabel = statLabels[statType] || statType.toUpperCase().substring(0, 3);
  }

  // Format value display based on type
  const formatValue = (game: Last3Game, idx: number) => {
    if (isMilestone && 'achieved' in game) {
      // For milestones, show checkmark if achieved
      const achieved = (game as any).achieved;
      const value = (game as any).value;
      
      if (statType === 'DD' || statType === 'TD') {
        // For double/triple doubles, show value (e.g., "PTS/REB" or "15P/12R/10A")
        return (
          <div key={idx} className="flex items-center gap-1">
            <span className={`font-semibold ${achieved ? 'text-green-600' : 'text-gray-500'}`}>
              {value}
            </span>
            {achieved && <span className="text-green-600">✓</span>}
            <span className="text-gray-400">@</span>
            <span className="text-gray-600">{game.opponent}</span>
            {idx < last3Games.length - 1 && (
              <span className="text-gray-300 mx-0.5">•</span>
            )}
          </div>
        );
      } else {
        // For single stat milestones (e.g., "20+ Points")
        return (
          <div key={idx} className="flex items-center gap-1">
            <span className={`font-semibold ${achieved ? 'text-green-600' : 'text-gray-500'}`}>
              {value}
            </span>
            {achieved && <span className="text-green-600">✓</span>}
            <span className="text-gray-400">@</span>
            <span className="text-gray-600">{game.opponent}</span>
            {idx < last3Games.length - 1 && (
              <span className="text-gray-300 mx-0.5">•</span>
            )}
          </div>
        );
      }
    } else {
      // Regular stat display
      return (
        <div key={idx} className="flex items-center gap-1">
          <span className="font-semibold">{game.value}</span>
          <span className="text-gray-400">@</span>
          <span className="text-gray-600">{game.opponent}</span>
          {idx < last3Games.length - 1 && (
            <span className="text-gray-300 mx-0.5">•</span>
          )}
        </div>
      );
    }
  };

  return (
    <div className="flex items-center gap-2 mt-1 text-xs text-gray-500">
      <span className="font-medium">Last 3:</span>
      <div className="flex gap-1.5 items-center flex-wrap">
        {last3Games.map((game, idx) => formatValue(game, idx))}
        {last3Games.length < 3 && (
          <span className="text-gray-400 italic">
            ({3 - last3Games.length} fewer)
          </span>
        )}
      </div>
    </div>
  );
}

