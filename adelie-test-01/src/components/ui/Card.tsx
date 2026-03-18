import React from 'react';

interface CardProps {
  /**
   * The card title
   */
  title?: string;
  /**
   * Optional subtitle
   */
  subtitle?: string;
  /**
   * Optional header action (e.g., button, dropdown)
   */
  headerAction?: React.ReactNode;
  /**
   * Optional footer content
   */
  footer?: React.ReactNode;
  /**
   * Whether the card has a hover effect
   */
  hoverable?: boolean;
  /**
   * Whether the card has a border
   */
  bordered?: boolean;
  /**
   * Whether the card has padding
   */
  padded?: boolean;
  /**
   * The main card content
   */
  children: React.ReactNode;
  /**
   * Additional CSS classes
   */
  className?: string;
}

const Card: React.FC<CardProps> = ({
  title,
  subtitle,
  headerAction,
  footer,
  hoverable = false,
  bordered = true,
  padded = true,
  children,
  className = '',
}) => {
  const baseStyles = 'rounded-lg bg-white';
  const borderStyle = bordered ? 'border border-gray-200' : '';
  const hoverStyle = hoverable ? 'transition-shadow duration-200 hover:shadow-md' : '';
  const paddingStyle = padded ? 'p-6' : '';
  
  return (
    <div 
      className={`${baseStyles} ${borderStyle} ${hoverStyle} ${className}`}
      role="article"
      aria-labelledby={title ? `card-title-${title.replace(/\s+/g, '-').toLowerCase()}` : undefined}
    >
      {(title || subtitle || headerAction) && (
        <div className="border-b border-gray-100 px-6 py-4">
          <div className="flex items-center justify-between">
            <div>
              {title && (
                <h3 
                  id={`card-title-${title.replace(/\s+/g, '-').toLowerCase()}`}
                  className="text-lg font-semibold text-gray-900"
                >
                  {title}
                </h3>
              )}
              {subtitle && (
                <p className="mt-1 text-sm text-gray-500">
                  {subtitle}
                </p>
              )}
            </div>
            {headerAction && (
              <div>
                {headerAction}
              </div>
            )}
          </div>
        </div>
      )}
      
      <div className={padded ? 'p-6' : ''}>
        {children}
      </div>
      
      {footer && (
        <div className="border-t border-gray-100 px-6 py-4 bg-gray-50 rounded-b-lg">
          {footer}
        </div>
      )}
    </div>
  );
};

export default Card;
