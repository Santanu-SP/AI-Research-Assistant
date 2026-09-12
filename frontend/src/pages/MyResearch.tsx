import React, { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { TopBar } from '../components/layout/TopBar';
import { StatusBadge } from '../components/common/StatusBadge';
import { EmptyState } from '../components/common/EmptyState';
import { PrimaryButton } from '../components/common/PrimaryButton';
import { researchService } from '../services/research.service';
import { Research } from '../types/research';
import { Search, Clock, ChevronRight } from 'lucide-react';

export const MyResearchPage: React.FC = () => {
  const navigate = useNavigate();
  const [researchList, setResearchList] = useState<Research[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedDomain, setSelectedDomain] = useState<string>('all');
  const [selectedStatus, setSelectedStatus] = useState<string>('all');

  useEffect(() => {
    researchService.getResearchList().then((data) => {
      setResearchList(data);
    });
  }, []);

  const domains = Array.from(new Set(researchList.map((r) => r.domain)));

  const filtered = researchList.filter((item) => {
    const matchesSearch =
      item.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      item.question.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (item.description &&
        item.description.toLowerCase().includes(searchQuery.toLowerCase()));

    const matchesDomain =
      selectedDomain === 'all' || item.domain === selectedDomain;

    const matchesStatus =
      selectedStatus === 'all' || item.status === selectedStatus;

    return matchesSearch && matchesDomain && matchesStatus;
  });

  return (
    <div className="min-h-screen bg-[#fafaf8] flex flex-col">
      {/* TopBar */}
      <TopBar
        breadcrumbs={
          <div className="flex items-center gap-2">
            <span className="text-[#6b706c]">Archive</span>
            <span className="text-[#929792]">/</span>
            <span className="text-[#181a18] font-medium">My Research</span>
          </div>
        }
      />

      {/* Main Content */}
      <main className="flex-1 pt-14 pb-16 px-4 sm:px-6">
        <div className="max-w-5xl mx-auto py-8">
          {/* Header Row */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
            <div>
              <h1 className="font-serif text-2xl sm:text-3xl text-[#181a18] font-normal tracking-tight">
                My Research
              </h1>
              <p className="text-xs sm:text-sm text-[#6b706c] mt-1">
                Archived syntheses, active investigations, and structured evidence memos across all domains.
              </p>
            </div>

            <PrimaryButton
              showArrow
              onClick={() => navigate('/research/new')}
            >
              New Research
            </PrimaryButton>
          </div>

          {/* Filter / Search Bar */}
          <div className="p-3 bg-white border border-[#e5e7e4] rounded-xl mb-6 flex flex-wrap items-center justify-between gap-3 shadow-xs">
            {/* Search input */}
            <div className="relative flex-1 min-w-[240px]">
              <Search className="w-4 h-4 text-[#929792] absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                aria-label="Search research"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search investigations by title, domain, or keyword…"
                className="w-full bg-[#fafaf8] border border-[#e5e7e4] rounded-md pl-9 pr-3 py-1.5 text-xs text-[#181a18] placeholder:text-[#929792] focus:outline-none focus:ring-1 focus:ring-[#163328] focus:border-[#163328] transition-colors"
              />
            </div>

            {/* Domain filter */}
            <div className="flex items-center gap-2">
              <select
                aria-label="Filter research by domain"
                value={selectedDomain}
                onChange={(e) => setSelectedDomain(e.target.value)}
                className="bg-[#fafaf8] border border-[#e5e7e4] text-[#6b706c] hover:text-[#181a18] text-xs rounded-md px-2.5 py-1.5 focus:outline-none focus:ring-1 focus:ring-[#163328]"
              >
                <option value="all">All domains</option>
                {domains.map((dom) => (
                  <option key={dom} value={dom}>
                    {dom}
                  </option>
                ))}
              </select>

              {/* Status filter */}
              <select
                aria-label="Filter research by status"
                value={selectedStatus}
                onChange={(e) => setSelectedStatus(e.target.value)}
                className="bg-[#fafaf8] border border-[#e5e7e4] text-[#6b706c] hover:text-[#181a18] text-xs rounded-md px-2.5 py-1.5 focus:outline-none focus:ring-1 focus:ring-[#163328]"
              >
                <option value="all">All statuses</option>
                <option value="completed">Completed</option>
                <option value="researching">Researching</option>
                <option value="draft">Draft</option>
                <option value="failed">Failed</option>
              </select>
            </div>
          </div>

          {/* Research List / Table */}
          {researchList.length === 0 ? (
            <EmptyState
              title="No research yet"
              description="Start your first investigation to build an evidence-backed research report."
              primaryActionLabel="New research"
              onPrimaryAction={() => navigate('/research/new')}
            />
          ) : filtered.length === 0 ? (
            <EmptyState
              title="No research investigations found"
              description="No investigations match your active filters. Try clearing your search parameters or start a new synthesis."
              primaryActionLabel="Start new research"
              onPrimaryAction={() => navigate('/research/new')}
            />
          ) : (
            <div className="bg-white border border-[#e5e7e4] rounded-xl overflow-hidden shadow-xs divide-y divide-[#e5e7e4]">
              {filtered.map((item) => {
                const targetUrl =
                  item.status === 'researching'
                    ? `/research/${item.id}/progress`
                    : `/research/${item.id}`;

                return (
                  <Link
                    key={item.id}
                    to={targetUrl}
                    className="p-4 sm:p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4 hover:bg-[#fafaf8] transition-colors group cursor-pointer"
                  >
                    {/* Left details */}
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2 mb-1.5">
                        <span className="text-[11px] font-medium text-[#163328] bg-[#f1f6f3] border border-[#d8e5df] px-2 py-0.5 rounded">
                          {item.domain}
                        </span>
                        <StatusBadge status={item.status} size="sm" />
                      </div>

                      <h3 className="text-sm sm:text-[15px] font-semibold text-[#181a18] group-hover:text-[#163328] transition-colors leading-snug">
                        {item.title}
                      </h3>

                      {item.description && (
                        <p className="text-xs text-[#6b706c] line-clamp-1 mt-1 leading-relaxed">
                          {item.description}
                        </p>
                      )}
                    </div>

                    {/* Right metadata and arrow */}
                    <div className="flex items-center justify-between sm:justify-end gap-5 shrink-0 text-xs text-[#6b706c] pt-2 sm:pt-0 border-t sm:border-t-0 border-[#f5f5f2]">
                      <div className="text-right">
                        <span className="font-medium text-[#181a18] block">
                          {item.sourceCount} sources
                        </span>
                        <span className="text-[11px] text-[#929792] flex items-center justify-end gap-1 mt-0.5">
                          <Clock className="w-3 h-3" />
                          <span>{item.updatedAt}</span>
                        </span>
                      </div>

                      <div className="w-8 h-8 rounded-full flex items-center justify-center text-[#929792] group-hover:text-[#163328] group-hover:bg-[#f1f6f3] transition-all">
                        <ChevronRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
                      </div>
                    </div>
                  </Link>
                );
              })}
            </div>
          )}

          {/* Bottom Counter */}
          <div className="mt-3 text-right text-xs text-[#929792]">
            Showing {filtered.length} of {researchList.length} investigations
          </div>
        </div>
      </main>
    </div>
  );
};
