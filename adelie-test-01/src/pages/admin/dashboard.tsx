import React, { useEffect, useState } from 'react';

interface Metric {
  name: string;
  value: number;
  pathname: string;
  timestamp: number;
}

/**
 * Simple admin dashboard that displays performance metrics collected by the
 * `usePerformanceMetrics` hook. It fetches data from the internal monitoring
 * endpoint (`/api/performance`) and renders it in a table.
 */
const Dashboard: React.FC = () => {
  const [metrics, setMetrics] = useState<Metric[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchMetrics = async () => {
      try {
        const response = await fetch('/api/performance');
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const data: Metric[] = await response.json();
        setMetrics(data);
      } catch (err) {
        setError((err as Error).message);
      } finally {
        setLoading(false);
      }
    };
    fetchMetrics();
  }, []);

  if (loading) {
    return <div className="p-4">Loading performance data…</div>;
  }

  if (error) {
    return <div className="p-4 text-red-600">Error loading data: {error}</div>;
  }

  return (
    <div className="p-4">
      <h1 className="text-2xl font-bold mb-4">Performance Dashboard</h1>
      {metrics.length === 0 ? (
        <p>No performance metrics recorded yet.</p>
      ) : (
        <table className="min-w-full border-collapse border border-gray-300">
          <thead>
            <tr className="bg-gray-100">
              <th className="border px-3 py-2 text-left">Metric</th>
              <th className="border px-3 py-2 text-left">Value</th>
              <th className="border px-3 py-2 text-left">Path</th>
              <th className="border px-3 py-2 text-left">Timestamp</th>
            </tr>
          </thead>
          <tbody>
            {metrics.map((m, idx) => (
              <tr key={idx} className={idx % 2 === 0 ? 'bg-white' : 'bg-gray-50'}>
                <td className="border px-3 py-2">{m.name}</td>
                <td className="border px-3 py-2">{m.value}</td>
                <td className="border px-3 py-2">{m.pathname}</td>
                <td className="border px-3 py-2">
                  {new Date(m.timestamp).toLocaleString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
};

export default Dashboard;
