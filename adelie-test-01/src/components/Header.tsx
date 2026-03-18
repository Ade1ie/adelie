import React from 'react';

interface HeaderProps {
  // Props can be extended as needed
}

export default function Header({}: HeaderProps) {
  return (
    <header className="bg-white shadow-sm border-b border-gray-200 sticky top-0 z-10">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between items-center py-4">
          {/* Logo */}
          <div className="flex items-center space-x-3">
            <div className="w-8 h-8 bg-primary-600 rounded-lg flex items-center justify-center">
              <span className="text-white font-bold text-lg">W</span>
            </div>
            <h1 className="text-2xl font-bold text-gray-900">Workspace</h1>
          </div>
          
          {/* Navigation */}
          <nav className="hidden md:flex space-x-8">
            <a 
              href="#" 
              className="text-gray-600 hover:text-primary-600 transition-colors duration-200 font-medium"
            >
              Dashboard
            </a>
            <a 
              href="#" 
              className="text-gray-600 hover:text-primary-600 transition-colors duration-200 font-medium"
            >
              Notes
            </a>
            <a 
              href="#" 
              className="text-gray-600 hover:text-primary-600 transition-colors duration-200 font-medium"
            >
              Files
            </a>
            <a 
              href="#" 
              className="text-gray-600 hover:text-primary-600 transition-colors duration-200 font-medium"
            >
              Settings
            </a>
          </nav>
          
          {/* Mobile menu button */}
          <button 
            className="md:hidden p-2 rounded-md text-gray-600 hover:text-primary-600 hover:bg-gray-100 transition-colors duration-200"
            aria-label="Toggle menu"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
        </div>
      </div>
    </header>
  );
}