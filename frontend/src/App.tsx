import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import { SportProvider } from './contexts/SportContext';
import Dashboard from './pages/Dashboard';
import GamesList from './pages/GamesList';
import GameDetail from './pages/GameDetail';
import HistoricalResults from './pages/HistoricalResults';
import AllPredictions from './pages/AllPredictions';
import Analyze from './pages/Analyze';
import PoorMansBet from './pages/PoorMansBet';
import BankrollRecommendations from './pages/BankrollRecommendations';
import PredictionManagement from './pages/PredictionManagement';
import ValueLadders from './pages/ValueLadders';

// Force reload - navigation updated
function App() {
  return (
    <SportProvider>
      <Router>
        <Layout>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/games" element={<GamesList />} />
          <Route path="/games/:gameId" element={<GameDetail />} />
          <Route path="/historical" element={<HistoricalResults />} />
          <Route path="/predictions" element={<AllPredictions />} />
          <Route path="/analyze" element={<Analyze />} />
          <Route path="/poor-mans-bet" element={<PoorMansBet />} />
          <Route path="/bankroll-recommendations" element={<BankrollRecommendations />} />
          <Route path="/prediction-management" element={<PredictionManagement />} />
          <Route path="/value-ladders" element={<ValueLadders />} />
        </Routes>
      </Layout>
    </Router>
    </SportProvider>
  );
}

export default App;

