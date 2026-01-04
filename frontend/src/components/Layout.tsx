import { Link, useLocation } from 'react-router-dom';
import { ReactNode } from 'react';

interface LayoutProps {
  children: ReactNode;
}

export default function Layout({ children }: LayoutProps) {
  const location = useLocation();

  const isActive = (path: string) => {
    return location.pathname === path ? 'bg-primary-600 text-white' : 'text-gray-700 hover:bg-gray-100';
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Navigation */}
      <nav className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16">
            <div className="flex">
              <div className="flex-shrink-0 flex items-center">
                <h1 className="text-2xl font-bold text-primary-600">🏀 NBA Betting Analytics</h1>
              </div>
              <div className="hidden sm:ml-6 sm:flex sm:space-x-8">
                <Link
                  to="/"
                  className={`inline-flex items-center px-1 pt-1 border-b-2 border-transparent text-sm font-medium ${isActive('/')}`}
                >
                  Dashboard
                </Link>
                <Link
                  to="/games"
                  className={`inline-flex items-center px-1 pt-1 border-b-2 border-transparent text-sm font-medium ${isActive('/games')}`}
                >
                  Games
                </Link>
                <Link
                  to="/plays"
                  className={`inline-flex items-center px-1 pt-1 border-b-2 border-transparent text-sm font-medium ${isActive('/plays')}`}
                >
                  My Plays
                </Link>
                <Link
                  to="/predictions"
                  className={`inline-flex items-center px-1 pt-1 border-b-2 border-transparent text-sm font-medium ${isActive('/predictions')}`}
                >
                  All Predictions
                </Link>
                <Link
                  to="/analyze"
                  className={`inline-flex items-center px-1 pt-1 border-b-2 border-transparent text-sm font-medium ${isActive('/analyze')}`}
                >
                  Analyze
                </Link>
                <Link
                  to="/historical"
                  className={`inline-flex items-center px-1 pt-1 border-b-2 border-transparent text-sm font-medium ${isActive('/historical')}`}
                >
                  Historical Results
                </Link>
                <Link
                  to="/lineups-injuries"
                  className={`inline-flex items-center px-1 pt-1 border-b-2 border-transparent text-sm font-medium ${isActive('/lineups-injuries')}`}
                >
                  Lineups & Injuries
                </Link>
                <Link
                  to="/poor-mans-bet"
                  className={`inline-flex items-center px-1 pt-1 border-b-2 border-transparent text-sm font-medium ${isActive('/poor-mans-bet')}`}
                >
                  Poor Man's Bet
                </Link>
                <Link
                  to="/bankroll-recommendations"
                  className={`inline-flex items-center px-1 pt-1 border-b-2 border-transparent text-sm font-medium ${isActive('/bankroll-recommendations')}`}
                >
                  Bankroll Recommendations
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

