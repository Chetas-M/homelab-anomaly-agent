import { BrowserRouter as Router, Routes, Route, Link } from 'react-router-dom';
import { Activity } from 'lucide-react';
import FleetOverview from './pages/FleetOverview';
import NodeDetail from './pages/NodeDetail';
import DataQuality from './pages/DataQuality';

function App() {
  return (
    <Router>
      <div className="container">
        <header className="header">
          <div className="header-title">
            <Activity className="text-accent" />
            <Link style={{ color: 'inherit', textDecoration: 'none' }} to="/">
              <strong>Home Lab Anomaly Agent</strong>
            </Link>
          </div>
          <div className="text-xs text-muted mono">
            v1.75
          </div>
        </header>
        
        <main>
          <Routes>
            <Route path="/" element={<FleetOverview />} />
            <Route path="/node/:nodeId" element={<NodeDetail />} />
            <Route path="/node/:nodeId/quality" element={<DataQuality />} />
          </Routes>
        </main>
      </div>
    </Router>
  );
}

export default App;
