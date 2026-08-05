import { Routes, Route } from 'react-router-dom';
import { AppLayout } from './components/AppLayout';
import { RequireAuth } from './components/RequireAuth';
import { LoginPage } from './pages/Login/LoginPage';
import { RegisterPage } from './pages/Login/RegisterPage';
import { OnboardingPage } from './pages/Onboarding/OnboardingPage';
import { DashboardPage } from './pages/Dashboard/DashboardPage';
import { PortfolioPage } from './pages/Portfolio/PortfolioPage';
import { RecommendPage } from './pages/Recommend/RecommendPage';
import { NewsPage } from './pages/News/NewsPage';
import { AccountPage } from './pages/Account/AccountPage';
import { BehaviouralGamePage } from './pages/BehaviouralGame/BehaviouralGamePage';

function App() {
  return (
    <Routes>
      {/* public */}
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />

      {/* signed-in, full-screen flow */}
      <Route path="/onboarding" element={<RequireAuth><OnboardingPage /></RequireAuth>} />
      <Route path="/behavioural-game" element={<RequireAuth><BehaviouralGamePage /></RequireAuth>} />

      {/* signed-in app shell */}
      <Route
        element={
          <RequireAuth>
            <AppLayout />
          </RequireAuth>
        }
      >
        <Route path="/" element={<DashboardPage />} />
        <Route path="/portfolio" element={<PortfolioPage />} />
        <Route path="/recommend" element={<RecommendPage />} />
        <Route path="/news" element={<NewsPage />} />
        <Route path="/account" element={<AccountPage />} />
      </Route>
    </Routes>
  );
}

export default App;
