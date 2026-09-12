import React from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import {
  Compass,
  FolderOpen,
  FileText,
  Settings,
} from 'lucide-react';

interface AppSidebarProps {
  className?: string;
}

export const AppSidebar: React.FC<AppSidebarProps> = ({ className = '' }) => {
  const location = useLocation();

  const recentItems = [
    {
      title: 'How is generative AI changing software development?',
      path: '/research/res-genai-2025',
      type: 'report',
      tooltip: 'View Completed Report',
    },
    {
      title: 'Small Modular Reactor (SMR) Levelized Cost of Energy',
      path: '/research/res-smr-lcoe',
      type: 'report',
      tooltip: 'View Report',
    },
    {
      title: 'CRISPR-Cas9 Field Trials',
      path: '/research/res-crispr-sorghum/progress',
      type: 'progress',
      tooltip: 'Active Researching',
    },
    {
      title: 'Lithium-Sulfur Battery Longevity',
      path: '/research/res-lis-cathodes',
      type: 'report',
      tooltip: 'View Report',
    },
  ];

  return (
    <aside
      className={`fixed left-0 top-0 h-full w-[232px] bg-[#fafaf8] z-50 flex flex-col justify-between border-r border-[#e5e7e4] select-none ${className}`}
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
        <div className="px-2 mt-3">
          <div className="uppercase tracking-wider text-[10.5px] text-[#929792] font-semibold px-3 mb-1.5">
            Recent Research
          </div>
          <nav className="flex flex-col gap-0.5">
            {recentItems.map((item, idx) => {
              const isActive = location.pathname === item.path;
              return (
                <div key={idx} className="relative group/tooltip">
                  <NavLink
                    to={item.path}
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
                    {item.tooltip}
                  </div>
                </div>
              );
            })}
          </nav>
        </div>
      </div>

      {/* Bottom Profile & Settings */}
      <div className="border-t border-[#e5e7e4] p-2 bg-[#fafaf8]">
        <button
          type="button"
          onClick={() => {}}
          className="w-full text-[#6b706c] hover:text-[#181a18] hover:bg-[#f5f5f2] px-3 py-1.5 rounded-md flex items-center gap-2.5 text-[13px] mb-1.5 transition-colors duration-150"
        >
          <Settings className="w-[18px] h-[18px] shrink-0 text-[#929792]" />
          <span>Settings</span>
        </button>

        <div className="flex items-center justify-between p-2 rounded-md hover:bg-[#f5f5f2] transition-colors duration-150 cursor-pointer">
          <div className="flex items-center gap-2.5 overflow-hidden">
            <div className="w-8 h-8 rounded-full bg-[#e2e8e4] text-[#163328] font-semibold text-xs flex items-center justify-center border border-[#d0d7d2] shrink-0">
              EV
            </div>
            <div className="flex flex-col min-w-0 text-left">
              <span className="text-[13px] font-semibold text-[#181a18] truncate leading-tight">
                Dr. Elena Vance
              </span>
              <span className="text-[11px] text-[#929792] truncate leading-tight">
                Senior Research Fellow
              </span>
            </div>
          </div>
        </div>
      </div>
    </aside>
  );
};
