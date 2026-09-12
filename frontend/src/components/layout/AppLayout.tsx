import React, { useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { AppSidebar } from './AppSidebar';
import { AnimatedResearchBackground } from './AnimatedResearchBackground';
import { Menu, X } from 'lucide-react';

export const AppLayout: React.FC = () => {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const location = useLocation();

  // Close mobile drawer on route transition
  React.useEffect(() => {
    setMobileMenuOpen(false);
  }, [location.pathname]);

  return (
    <div className="relative isolate min-h-screen overflow-x-clip bg-[#fafaf8] text-[#181a18]">
      <AnimatedResearchBackground />

      {/* Desktop Sidebar */}
      <div className="hidden lg:block">
        <AppSidebar />
      </div>

      {/* Mobile Header Bar with Hamburger */}
      <div className="lg:hidden fixed top-0 left-0 right-0 h-14 bg-[#fafaf8] border-b border-[#e5e7e4] z-50 flex items-center justify-between px-4">
        <button
          type="button"
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          className="p-1.5 rounded-md text-[#181a18] hover:bg-[#f1f6f3] transition-colors"
          aria-label="Toggle navigation menu"
        >
          {mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
        </button>

        <span className="font-semibold text-sm tracking-tight text-[#181a18]">
          Research Assistant
        </span>

        <div className="w-8 h-8 rounded-full bg-[#e2e8e4] text-[#163328] font-semibold text-xs flex items-center justify-center border border-[#d0d7d2]">
          EV
        </div>
      </div>

      {/* Mobile Drawer */}
      {mobileMenuOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div
            className="fixed inset-0 bg-black/40 backdrop-blur-xs transition-opacity"
            onClick={() => setMobileMenuOpen(false)}
          />
          <div className="relative w-[280px] h-full bg-[#fafaf8] shadow-2xl z-10 animate-in slide-in-from-left duration-200">
            <AppSidebar className="w-full relative shadow-none border-r border-[#e5e7e4]" />
          </div>
        </div>
      )}

      {/* Main content offset by desktop sidebar */}
      <div className="app-content-surface relative z-10 lg:pl-[232px] pt-14 lg:pt-0 min-h-screen flex flex-col">
        <Outlet />
      </div>
    </div>
  );
};
