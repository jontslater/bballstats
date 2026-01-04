import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import Dashboard from './pages/Dashboard';
import GamesList from './pages/GamesList';
import GameDetail from './pages/GameDetail';
import MyPlays from './pages/MyPlays';
import HistoricalResults from './pages/HistoricalResults';
import AllPredictions from './pages/AllPredictions';
import Analyze from './pages/Analyze';
import LineupsAndInjuries from './pages/LineupsAndInjuries';
import PoorMansBet from './pages/PoorMansBet';
import BankrollRecommendations from './pages/BankrollRecommendations';

function App() {
  return (
    <Router>
      <Layout>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/games" element={<GamesList />} />
          <Route path="/games/:gameId" element={<GameDetail />} />
          <Route path="/plays" element={<MyPlays />} />
          <Route path="/historical" element={<HistoricalResults />} />
          <Route path="/predictions" element={<AllPredictions />} />
          <Route path="/analyze" element={<Analyze />} />
          <Route path="/lineups-injuries" element={<LineupsAndInjuries />} />
          <Route path="/poor-mans-bet" element={<PoorMansBet />} />
          <Route path="/bankroll-recommendations" element={<BankrollRecommendations />} />
        </Routes>
      </Layout>
    </Router>
  );
}

export default App;

