import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Layout from '@/components/Layout';
import Home from '@/pages/index';
import About from '@/pages/about';
import NotFound from '@/pages/404';
import Dashboard from '@/pages/admin/dashboard';
import { usePerformanceMetrics } from '@/hooks/usePerformanceMetrics';
import VercelAnalytics from '@/components/Analytics';

/**
 * Root application component.
 * Integrates Vercel Analytics, custom performance metrics collection,
 * and sets up the main routing structure.
 */
const App: React.FC = () => {
  // Initialise custom performance logger
  usePerformanceMetrics();

  return (
    <>
      {/* Vercel Analytics script injection */}
      <VercelAnalytics />
      <Router>
        <Layout>
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/about" element={<About />} />
            <Route path="/admin/dashboard" element={<Dashboard />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </Layout>
      </Router>
    </>
  );
};

export default App;
