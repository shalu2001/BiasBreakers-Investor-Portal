import { Routes, Route } from 'react-router-dom';
import { Suspense, lazy } from 'react';
import { AppLayout } from './components/AppLayout';
import { RequireAuth } from './components/RequireAuth';
// Login / Register stay eager so the first screen paints instantly.
import { LoginPage } from './pages/Login/LoginPage';
import { RegisterPage } from './pages/Login/RegisterPage';

// Everything behind auth is code-split: the heavy bits (behavioural game,
// candlestick charts, etc.) load on demand instead of blocking the first paint.
const OnboardingPage = lazy(() =>
  import('./pages/Onboarding/OnboardingPage').then((m) => ({ default: m.OnboardingPage })),
);
const DashboardPage = lazy(() =>
  import('./pages/Dashboard/DashboardPage').then((m) => ({ default: m.DashboardPage })),
);
const PortfolioPage = lazy(() =>
  import('./pages/Portfolio/PortfolioPage').then((m) => ({ default: m.PortfolioPage })),
);
const RecommendPage = lazy(() =>
  import('./pages/Recommend/RecommendPage').then((m) => ({ default: m.RecommendPage })),
);
const NewsPage = lazy(() => import('./pages/News/NewsPage').then((m) => ({ default: m.NewsPage })));
const NewsArticlePage = lazy(() =>
  import('./pages/News/NewsArticlePage').then((m) => ({ default: m.NewsArticlePage })),
);
const AccountPage = lazy(() =>
  import('./pages/Account/AccountPage').then((m) => ({ default: m.AccountPage })),
);
const BehaviouralProfilePage = lazy(() =>
  import('./pages/BehaviouralProfile/BehaviouralProfilePage').then((m) => ({
    default: m.BehaviouralProfilePage,
  })),
);
const BehaviouralGamePage = lazy(() =>
  import('./pages/BehaviouralGame/BehaviouralGamePage').then((m) => ({ default: m.BehaviouralGamePage })),
);

function PageFallback() {
  return (
    <div style={{ padding: 40, color: 'var(--color-text-muted)', fontSize: 14 }}>Loading…</div>
  );
}

function App() {
  return (
    <Suspense fallback={<PageFallback />}>
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
          <Route path="/behavioural-profile" element={<BehaviouralProfilePage />} />
          <Route path="/portfolio" element={<PortfolioPage />} />
          <Route path="/recommend" element={<RecommendPage />} />
          <Route path="/news" element={<NewsPage />} />
          <Route path="/news/article" element={<NewsArticlePage />} />
          <Route path="/account" element={<AccountPage />} />
        </Route>
      </Routes>
    </Suspense>
  );
}

export default App;
