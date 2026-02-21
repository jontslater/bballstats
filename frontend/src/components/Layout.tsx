import { Link, useLocation } from 'react-router-dom';
import { ReactNode } from 'react';
import { useSport } from '../contexts/SportContext';

interface LayoutProps {
  children: ReactNode;
}

export default function Layout({ children }: LayoutProps) {
  const location = useLocation();
  const { sport, setSport } = useSport();

  const isActive = (path: string) => {
    return location.pathname === path ? 'bg-primary-600 text-white' : 'text-gray-700 hover:bg-gray-100';
  };

  const sportEmoji = sport === 'NBA' ? '🏀' : sport === 'NFL' ? '🏈' : '⚾';
  const sportTitle = sport === 'NBA' ? 'NBA' : sport === 'NFL' ? 'NFL' : 'MLB';

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Navigation */}
      <nav className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16">
            <div className="flex">
              <div className="flex-shrink-0 flex items-center gap-4">
                <h1 className="text-2xl font-bold text-primary-600">{sportEmoji} {sportTitle} Betting Analytics v2.1</h1>
                {/* Sport Selector */}
                <div className="flex gap-2 ml-4">
                  <button
                    onClick={() => setSport('NBA')}
                    className={`px-3 py-1 rounded-md text-sm font-medium ${
                      sport === 'NBA'
                        ? 'bg-primary-600 text-white'
                        : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                    }`}
                  >
                    🏀 NBA
                  </button>
                  <button
                    onClick={() => setSport('NFL')}
                    className={`px-3 py-1 rounded-md text-sm font-medium ${
                      sport === 'NFL'
                        ? 'bg-primary-600 text-white'
                        : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                    }`}
                  >
                    🏈 NFL
                  </button>
                  <button
                    onClick={() => setSport('MLB')}
                    className={`px-3 py-1 rounded-md text-sm font-medium ${
                      sport === 'MLB'
                        ? 'bg-primary-600 text-white'
                        : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                    }`}
                  >
                    ⚾ MLB
                  </button>
                </div>
              </div>
              <div className="ml-6 flex space-x-4 overflow-x-auto scrollbar-hide">
                <Link
                  to="/"
                  className={`inline-flex items-center px-1 pt-1 border-b-2 border-transparent text-xs sm:text-sm font-medium ${isActive('/')}`}
                >
                  Dashboard
                </Link>
                <Link
                  to="/games"
                  className={`inline-flex items-center px-1 pt-1 border-b-2 border-transparent text-xs sm:text-sm font-medium ${isActive('/games')}`}
                >
                  Games
                </Link>
                <Link
                  to="/value-ladders"
                  className={`inline-flex items-center px-1 pt-1 border-b-2 border-transparent text-xs sm:text-sm font-medium ${isActive('/value-ladders')}`}
                >
                  🎯 Value Ladders
                </Link>
                <Link
                  to="/predictions"
                  className={`inline-flex items-center px-1 pt-1 border-b-2 border-transparent text-xs sm:text-sm font-medium ${isActive('/predictions')}`}
                >
                  All Predictions
                </Link>
                <Link
                  to="/analyze"
                  className={`inline-flex items-center px-1 pt-1 border-b-2 border-transparent text-xs sm:text-sm font-medium ${isActive('/analyze')}`}
                >
                  Analyze
                </Link>
                <Link
                  to="/historical"
                  className={`inline-flex items-center px-1 pt-1 border-b-2 border-transparent text-xs sm:text-sm font-medium ${isActive('/historical')}`}
                >
                  Historical Results
                </Link>
                {/* Temporarily hidden - Lineups & Injuries
                <Link
                  to="/lineups-injuries"
                  className={`inline-flex items-center px-1 pt-1 border-b-2 border-transparent text-xs sm:text-sm font-medium ${isActive('/lineups-injuries')}`}
                >
                  Lineups & Injuries
                </Link>
                */}
                <Link
                  to="/poor-mans-bet"
                  className={`inline-flex items-center px-1 pt-1 border-b-2 border-transparent text-xs sm:text-sm font-medium ${isActive('/poor-mans-bet')}`}
                >
                  Sure Bets
                </Link>
                <Link
                  to="/bankroll-recommendations"
                  className={`inline-flex items-center px-1 pt-1 border-b-2 border-transparent text-xs sm:text-sm font-medium ${isActive('/bankroll-recommendations')}`}
                >
                  Bankroll Recommendations
                </Link>
                <Link
                  to="/prediction-management"
                  className={`inline-flex items-center px-1 pt-1 border-b-2 border-transparent text-xs sm:text-sm font-medium ${isActive('/prediction-management')}`}
                >
                  Prediction Management
                </Link>
              </div>
            </div>
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
        {children}
      </main>
    </div>
  );
}

