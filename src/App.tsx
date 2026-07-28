import { Routes, Route } from 'react-router-dom';
import { AppLayout } from './components/AppLayout';
import { LoginPage } from './pages/Login/LoginPage';
import { OnboardingPage } from './pages/Onboarding/OnboardingPage';
import { DashboardPage } from './pages/Dashboard/DashboardPage';
import { PortfolioPage } from './pages/Portfolio/PortfolioPage';
import { RecommendPage } from './pages/Recommend/RecommendPage';
import { NewsPage } from './pages/News/NewsPage';

function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/onboarding" element={<OnboardingPage />} />

      <Route element={<AppLayout />}>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/portfolio" element={<PortfolioPage />} />
        <Route path="/recommend" element={<RecommendPage />} />
        <Route path="/news" element={<NewsPage />} />
      </Route>
    </Routes>
  );
}

export default App;
