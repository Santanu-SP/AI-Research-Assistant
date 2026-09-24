import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate, Link, useLocation } from 'react-router-dom';
import { TopBar } from '../components/layout/TopBar';
import { ResearchComposer } from '../components/research/ResearchComposer';
import { StatusBadge } from '../components/common/StatusBadge';
import { EmptyState } from '../components/common/EmptyState';
import { ErrorState } from '../components/common/ErrorState';
import { LoadingState } from '../components/common/LoadingState';
import { mockSuggestedQuestions } from '../data/mockResearch';
import {
  getResearchErrorMessage,
  researchService,
} from '../services/research.service';
import { ArrowUpRight, Clock } from 'lucide-react';
import { ResearchDepth, ResearchResponse } from '../types/research';

const formatUpdatedAt = (value: string): string =>
  new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    year: new Date(value).getFullYear() === new Date().getFullYear() ? undefined : 'numeric',
  }).format(new Date(value));

export const NewResearch: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [selectedPrompt, setSelectedPrompt] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [recentResearch, setRecentResearch] = useState<ResearchResponse[]>([]);
  const [recentTotal, setRecentTotal] = useState(0);
  const [isRecentLoading, setIsRecentLoading] = useState(true);
  const [recentError, setRecentError] = useState<string | null>(null);

  useEffect(() => {
    setSelectedPrompt('');
    setCreateError(null);
  }, [location.key]);

  const loadRecentResearch = useCallback(async () => {
    setIsRecentLoading(true);
    setRecentError(null);
    try {
      const response = await researchService.listResearch({ limit: 4, offset: 0 });
      setRecentResearch(response.items);
      setRecentTotal(response.total);
    } catch (error) {
      setRecentError(
        getResearchErrorMessage(error, 'We could not load your recent research.')
      );
    } finally {
      setIsRecentLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadRecentResearch();
  }, [loadRecentResearch]);

  const handleStartResearch = async (payload: {
    question: string;
    depth: ResearchDepth;
  }) => {
    setIsSubmitting(true);
    setCreateError(null);
    try {
      const result = await researchService.queryResearch({
        query: payload.question,
        researchDepth: payload.depth,
      });
      navigate(`/research/${result.researchId}`);
    } catch (error) {
      setCreateError(
        getResearchErrorMessage(error, 'Research could not be completed. Please try again.')
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSelectSuggestion = (question: string) => {
    setSelectedPrompt(question);
  };

  return (
    <div className="min-h-screen bg-[#fafaf8] flex flex-col">
      {/* TopBar with breadcrumb */}
      <TopBar
        breadcrumbs={
          <div className="flex items-center gap-2">
            <span className="text-[#6b706c]">Research</span>
            <span className="text-[#929792]">/</span>
            <span className="text-[#181a18] font-medium">New Research</span>
          </div>
        }
      />

      {/* Main Content Area */}
      <main className="flex-1 pt-14 pb-16 px-4 sm:px-6">
        <div className="max-w-3xl mx-auto py-10">
          {/* Header Section */}
          <div className="mb-8 text-center sm:text-left">
            <h1 className="font-serif text-3xl sm:text-4xl text-[#181a18] tracking-tight font-normal mb-2.5">
              What would you like to investigate?
            </h1>
            <p className="text-sm sm:text-[15px] text-[#6b706c] max-w-2xl leading-relaxed">
              Search your indexed papers and generate a locally grounded answer with validated citations.
            </p>
          </div>

          {/* Research Composer */}
          <div className="mb-10">
            <ResearchComposer
              key={location.key}
              initialPrompt={selectedPrompt}
              onStartResearch={handleStartResearch}
              isLoading={isSubmitting}
            />
            {createError ? (
              <div className="mt-3">
                <ErrorState
                  title="Research could not be completed"
                  message={createError}
                />
              </div>
            ) : null}
          </div>

          {/* Suggested Research Questions */}
          <div className="mb-10">
            <div className="uppercase tracking-wider text-[11px] font-semibold text-[#929792] mb-3">
              Suggested Research Questions
            </div>

            <div className="grid grid-cols-1 gap-2">
              {mockSuggestedQuestions.map((sug) => (
                <button
                  key={sug.id}
                  type="button"
                  onClick={() => handleSelectSuggestion(sug.question)}
                  className="w-full text-left p-3.5 bg-white border border-[#e5e7e4] hover:border-[#cbd0ca] hover:bg-[#fcfdfc] rounded-lg transition-all duration-150 flex items-center justify-between group cursor-pointer"
                >
                  <div className="min-w-0 pr-4">
                    <p className="text-[13.5px] font-medium text-[#181a18] group-hover:text-[#163328] transition-colors leading-snug">
                      {sug.question}
                    </p>
                    <span className="text-[11.5px] text-[#929792] mt-0.5 inline-block">
                      {sug.domain}
                    </span>
                  </div>
                  <ArrowUpRight className="w-4 h-4 text-[#929792] group-hover:text-[#163328] group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-all shrink-0" />
                </button>
              ))}
            </div>
          </div>

          {/* Recent Research Section */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <span className="uppercase tracking-wider text-[11px] font-semibold text-[#929792]">
                Recent Research
              </span>
              <Link
                to="/research"
                className="text-xs font-medium text-[#163328] hover:underline"
              >
                View all ({recentTotal})
              </Link>
            </div>

            {isRecentLoading ? (
              <LoadingState rows={2} />
            ) : recentError ? (
              <ErrorState
                title="Recent research unavailable"
                message={recentError}
                onRetry={() => void loadRecentResearch()}
              />
            ) : recentResearch.length === 0 ? (
              <EmptyState
                title="No research yet"
                description="Create your first research record using the question above."
              />
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {recentResearch.map((item) => {
                const targetPath =
                  item.status === 'researching'
                    ? `/research/${item.id}/progress`
                    : item.status === 'completed'
                      ? `/research/${item.id}`
                      : `/research/${item.id}/progress`;

                return (
                  <Link
                    key={item.id}
                    to={targetPath}
                    className="p-4 bg-white border border-[#e5e7e4] hover:border-[#cbd0ca] hover:shadow-xs rounded-lg transition-all duration-150 flex flex-col justify-between group"
                  >
                    <div>
                      <div className="flex items-center justify-between gap-2 mb-2">
                        <span className="text-[11px] font-medium text-[#6b706c] truncate">
                          {item.domain || 'General research'}
                        </span>
                        <StatusBadge status={item.status} size="sm" />
                      </div>

                      <h4 className="text-[13.5px] font-medium text-[#181a18] group-hover:text-[#163328] transition-colors line-clamp-2 leading-snug mb-3">
                        {item.title}
                      </h4>
                    </div>

                    <div className="flex items-center justify-between text-[11px] text-[#929792] pt-2 border-t border-[#f5f5f2]">
                      <span>{item.sourceCount} sources</span>
                      <span className="flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        <span>{formatUpdatedAt(item.updatedAt)}</span>
                      </span>
                    </div>
                  </Link>
                );
              })}
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
};
