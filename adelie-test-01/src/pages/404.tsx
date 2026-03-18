import React from 'react';
import { Link } from 'react-router-dom';
import Layout from '@/components/Layout';

const NotFound: React.FC = () => {
  return (
    <Layout>
      <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4 sm:px-6 lg:px-8">
        <div className="max-w-md w-full text-center">
          {/* 404 Illustration */}
          <div className="mb-8">
            <div className="mx-auto w-48 h-48 bg-gradient-to-br from-blue-100 to-purple-100 rounded-full flex items-center justify-center">
              <span className="text-6xl font-bold text-gray-600">404</span>
            </div>
          </div>
          
          {/* Error Message */}
          <h1 className="text-3xl font-bold text-gray-900 mb-4">Page Not Found</h1>
          <p className="text-lg text-gray-600 mb-8">
            Sorry, we couldn't find the page you're looking for. The page might have been moved, deleted, or you entered the wrong URL.
          </p>
          
          {/* Navigation Options */}
          <div className="space-y-4 sm:space-y-0 sm:space-x-4 sm:flex sm:justify-center">
            <Link
              to="/"
              className="w-full sm:w-auto inline-flex items-center justify-center px-6 py-3 border border-transparent text-base font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700 transition-colors duration-200"
            >
              Back to Homepage
            </Link>
            <button
              onClick={() => window.history.back()}
              className="w-full sm:w-auto inline-flex items-center justify-center px-6 py-3 border border-gray-300 text-base font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 transition-colors duration-200"
            >
              Go Back
            </button>
          </div>
          
          {/* Additional Help */}
          <div className="mt-8 text-sm text-gray-500">
            <p>If you believe this is an error, please contact support.</p>
          </div>
        </div>
      </div>
    </Layout>
  );
};

export default NotFound;