import React, { useEffect, useState } from 'react';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import {
  Compass,
  FolderOpen,
  FileText,
  LogOut,
} from 'lucide-react';
import { researchService } from '../../services/research.service';
import { ResearchResponse } from '../../types/research';
import { useAuth } from '../../app/AuthContext';

interface AppSidebarProps {
  className?: string;
}

export const AppSidebar: React.FC<AppSidebarProps> = ({ className = '' }) => {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const [recentItems, setRecentItems] = useState<ResearchResponse[]>([]);
  const [profileOpen, setProfileOpen] = useState(false);
  const [logoutError, setLogoutError] = useState<string | null>(null);

  useEffect(() => {
    researchService
      .listResearch({ limit: 4, offset: 0 })
      .then((res) => {
        setRecentItems(res.items);
      })
      .catch((err) => {
        console.error('Failed to load recent research for sidebar:', err);
      });
  }, [location.pathname]); // Refresh when navigation changes

  return (
    <aside
      className={`app-chrome-surface fixed left-0 top-0 h-full w-[232px] z-50 flex flex-col justify-between border-r border-[#e5e7e4] select-none ${className}`}
    >
      <div className="flex flex-col">
        {/* Brand / Logo Header */}
        <div className="h-14 px-4 flex items-center gap-2.5 border-b border-[#e5e7e4]">
          <div className="w-6 h-6 flex items-center justify-center shrink-0 text-[#163328]">
            <svg
              className="w-5 h-5"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              viewBox="0 0 24 24"
            >
              <path
                d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </div>
          <span className="font-semibold text-[14.5px] tracking-tight text-[#181a18]">
            Research Assistant
          </span>
        </div>

        {/* Primary Navigation */}
        <div className="p-2 pt-3">
          <nav className="flex flex-col gap-0.5">
            {/* New Research */}
            <NavLink
              to="/research/new"
              className={({ isActive }) =>
                isActive
                  ? 'bg-[#f1f6f3] text-[#163328] font-medium rounded-md px-3 py-2 flex items-center gap-2.5 relative text-[13.5px] transition-colors duration-150'
                  : 'text-[#6b706c] hover:text-[#181a18] hover:bg-[#f5f5f2] px-3 py-2 rounded-md flex items-center gap-2.5 text-[13.5px] font-normal transition-colors duration-150'
              }
            >
              {({ isActive }) => (
                <>
                  {isActive && (
                    <div className="absolute left-0 top-1.5 bottom-1.5 w-[2px] bg-[#163328] rounded-r-full" />
                  )}
                  <Compass className="w-[18px] h-[18px] shrink-0" />
                  <span>New Research</span>
                </>
              )}
            </NavLink>

            {/* My Research */}
            <NavLink
              to="/research"
              end
              className={({ isActive }) =>
                isActive
                  ? 'bg-[#f1f6f3] text-[#163328] font-medium rounded-md px-3 py-2 flex items-center gap-2.5 relative text-[13.5px] transition-colors duration-150'
                  : 'text-[#6b706c] hover:text-[#181a18] hover:bg-[#f5f5f2] px-3 py-2 rounded-md flex items-center gap-2.5 text-[13.5px] font-normal transition-colors duration-150'
              }
            >
              {({ isActive }) => (
                <>
                  {isActive && (
                    <div className="absolute left-0 top-1.5 bottom-1.5 w-[2px] bg-[#163328] rounded-r-full" />
                  )}
                  <FolderOpen className="w-[18px] h-[18px] shrink-0" />
                  <span>My Research</span>
                </>
              )}
            </NavLink>

            {/* Documents */}
            <NavLink
              to="/documents"
              className={({ isActive }) =>
                isActive
                  ? 'bg-[#f1f6f3] text-[#163328] font-medium rounded-md px-3 py-2 flex items-center gap-2.5 relative text-[13.5px] transition-colors duration-150'
                  : 'text-[#6b706c] hover:text-[#181a18] hover:bg-[#f5f5f2] px-3 py-2 rounded-md flex items-center gap-2.5 text-[13.5px] font-normal transition-colors duration-150'
              }
            >
              {({ isActive }) => (
                <>
                  {isActive && (
                    <div className="absolute left-0 top-1.5 bottom-1.5 w-[2px] bg-[#163328] rounded-r-full" />
                  )}
                  <FileText className="w-[18px] h-[18px] shrink-0" />
                  <span>Documents</span>
                </>
              )}
            </NavLink>
          </nav>
        </div>

        {/* Recent Research Section */}
        {recentItems.length > 0 && (
          <div className="px-2 mt-3">
            <div className="uppercase tracking-wider text-[10.5px] text-[#929792] font-semibold px-3 mb-1.5">
              Recent Research
            </div>
            <nav className="flex flex-col gap-0.5">
              {recentItems.map((item) => {
                const targetPath =
                  item.status === 'researching'
                    ? `/research/${item.id}/progress`
                    : item.status === 'completed'
                    ? `/research/${item.id}`
                    : `/research/${item.id}/progress`;

                const tooltipText =
                  item.status === 'completed'
                    ? 'View Report'
                    : item.status === 'researching'
                    ? 'Active Researching'
                    : 'View Research';

                const isActive = location.pathname === targetPath;
                return (
                  <div key={item.id} className="relative group/tooltip">
                    <NavLink
                      to={targetPath}
                      className={`text-[13px] truncate px-3 py-1.5 rounded-md transition-colors duration-150 block ${
                        isActive
                          ? 'bg-[#f1f6f3] text-[#163328] font-medium'
                          : 'text-[#6b706c] hover:text-[#181a18] hover:bg-[#f5f5f2]'
                      }`}
                    >
                      {item.title}
                    </NavLink>
                    {/* Tooltip */}
                    <div className="pointer-events-none absolute left-[98%] top-1/2 -translate-y-1/2 ml-2 z-50 bg-[#181a18] text-white text-[11px] font-normal px-2.5 py-1 rounded shadow-md whitespace-nowrap opacity-0 group-hover/tooltip:opacity-100 transition-opacity duration-150">
                      {tooltipText}
                    </div>
                  </div>
                );
              })}
            </nav>
          </div>
        )}
      </div>

      {/* Bottom Profile & Settings */}
      <div className="border-t border-[#e5e7e4] p-2">
        {profileOpen && <div className="mb-2 rounded-md border border-[#e5e7e4] bg-white p-2">
          <p className="px-2 py-1 text-[11px] text-[#6b706c] truncate">{user?.email}</p>
          <button type="button" onClick={() => {
            setLogoutError(null);
            void logout().then(() => navigate('/login', { replace: true })).catch(() => {
              setLogoutError('Could not reach the server. Please try again.');
            });
          }} className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs text-[#181a18] hover:bg-[#f5f5f2]">
            <LogOut className="w-4 h-4" /> Logout
          </button>
          {logoutError && <p role="alert" className="text-xs text-[#b91c1c] px-2">{logoutError}</p>}
        </div>}

        <button type="button" aria-expanded={profileOpen} onClick={() => setProfileOpen((open) => !open)} className="w-full flex items-center justify-between p-2 rounded-md hover:bg-[#f5f5f2] transition-colors duration-150">
          <div className="flex items-center gap-2.5 overflow-hidden">
            <div className="w-8 h-8 rounded-full bg-[#e2e8e4] text-[#163328] font-semibold text-xs flex items-center justify-center border border-[#d0d7d2] shrink-0">
              {user?.name.slice(0, 1).toUpperCase() || 'R'}
            </div>
            <div className="flex flex-col min-w-0 text-left">
              <span className="text-[13px] font-semibold text-[#181a18] truncate leading-tight">
                {user?.name || 'Researcher'}
              </span>
              <span className="text-[11px] text-[#929792] truncate leading-tight">
                Account
              </span>
            </div>
          </div>
        </button>
      </div>
    </aside>
  );
};
