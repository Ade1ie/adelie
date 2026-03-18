import React from 'react';

type SpinnerSize = 'xs' | 'sm' | 'md' | 'lg' | 'xl';
type SpinnerVariant = 'primary' | 'secondary' | 'light';

interface LoadingSpinnerProps {
  /**
   * The size of the spinner
   */
  size?: SpinnerSize;
  /**
   * The visual variant of the spinner
   */
  variant?: SpinnerVariant;
  /**
   * Optional label text to display with the spinner
   */
  label?: string;
  /**
   * Whether the spinner should be centered in its container
   */
  centered?: boolean;
  /**
   * Additional CSS classes
   */
  className?: string;
  /**
   * Accessibility label for screen readers
   */
  ariaLabel?: string;
}

const LoadingSpinner: React.FC<LoadingSpinnerProps> = ({
  size = 'md',
  variant = 'primary',
  label,
  centered = false,
  className = '',
  ariaLabel = 'Loading',
}) => {
  const sizeClasses: Record<SpinnerSize, string> = {
    xs: 'h-4 w-4',
    sm: 'h-6 w-6',
    md: 'h-8 w-8',
    lg: 'h-12 w-12',
    xl: 'h-16 w-16',
  };
  
  const variantClasses: Record<SpinnerVariant, string> = {
    primary: 'text-blue-600',
    secondary: 'text-gray-600',
    light: 'text-gray-300',
  };
  
  const containerClasses = centered ? 'flex flex-col items-center justify-center' : 'inline-flex flex-col items-center';
  
  return (
    <div 
      className={`${containerClasses} ${className}`}
      role="status"
      aria-live="polite"
      aria-label={ariaLabel}
    >
      <svg 
        className={`animate-spin ${sizeClasses[size]} ${variantClasses[variant]}`}
        xmlns="http://www.w3.org/2000/svg"
        fill="none"
        viewBox="0 0 24 24"
        aria-hidden="true"
      >
        <circle 
          className="opacity-25" 
          cx="12" 
          cy="12" 
          r="10" 
          stroke="currentColor" 
          strokeWidth="4"
        />
        <path 
          className="opacity-75" 
          fill="currentColor" 
          d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
        />
      </svg>
      
      {label && (
        <span 
          className="mt-2 text-sm text-gray-600"
          aria-hidden="true"
        >
          {label}
        </span>
      )}
      
      <span className="sr-only">
        {ariaLabel}
      </span>
    </div>
  );
};

export default LoadingSpinner;
