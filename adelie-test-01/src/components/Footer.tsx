import React from 'react';

interface FooterProps {
  // Props can be extended as needed
}

export default function Footer({}: FooterProps) {
  const currentYear = new Date().getFullYear();
  
  return (
    <footer className="bg-gray-100 border-t border-gray-200 py-8">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {/* Brand section */}
          <div className="space-y-4">
            <div className="flex items-center space-x-3">
              <div className="w-8 h-8 bg-primary-600 rounded-lg flex items-center justify-center">
                <span className="text-white font-bold text-lg">W</span>
              </div>
              <span className="text-xl font-bold text-gray-900">Workspace</span>
            </div>
            <p className="text-gray-600 text-sm max-w-md">
              Your private digital environment for productivity and organization.
            </p>
          </div>
          
          {/* Links section */}
          <div className="space-y-4">
            <h3 className="text-lg font-semibold text-gray-900">Quick Links</h3>
            <div className="flex flex-col space-y-2">
              <a href="#" className="text-gray-600 hover:text-primary-600 transition-colors duration-200 text-sm">
                Documentation
              </a>
              <a href="#" className="text-gray-600 hover:text-primary-600 transition-colors duration-200 text-sm">
                Support
              </a>
              <a href="#" className="text-gray-600 hover:text-primary-600 transition-colors duration-200 text-sm">
                Privacy Policy
              </a>
              <a href="#" className="text-gray-600 hover:text-primary-600 transition-colors duration-200 text-sm">
                Terms of Service
              </a>
            </div>
          </div>
          
          {/* Contact section */}
          <div className="space-y-4">
            <h3 className="text-lg font-semibold text-gray-900">Contact</h3>
            <div className="flex flex-col space-y-2">
              <span className="text-gray-600 text-sm">support@workspace.com</span>
              <span className="text-gray-600 text-sm">+1 (555) 123-4567</span>
            </div>
          </div>
        </div>
        
        {/* Copyright */}
        <div className="mt-8 pt-8 border-t border-gray-200 text-center">
          <p className="text-gray-600 text-sm">
            &copy; {currentYear} Personal Workspace. All rights reserved.
          </p>
        </div>
      </div>
    </footer>
  );
}