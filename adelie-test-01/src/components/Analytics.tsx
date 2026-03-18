import { useEffect } from 'react';

/**
 * Component that injects Vercel Analytics script into the page.
 * The script is loaded asynchronously and removed when the component
 * unmounts (e.g., during hot‑module replacement in development).
 */
const VercelAnalytics: React.FC = () => {
  useEffect(() => {
    const script = document.createElement('script');
    script.src = 'https://vercel.com/_vercel/insights/script.js';
    script.async = true;
    document.body.appendChild(script);

    return () => {
      document.body.removeChild(script);
    };
  }, []);

  // This component does not render any visible UI.
  return null;
};

export default VercelAnalytics;
