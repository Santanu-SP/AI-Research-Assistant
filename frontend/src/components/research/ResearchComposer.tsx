import React, { useState, useEffect, useRef } from 'react';
import { Check, ChevronDown, ArrowRight } from 'lucide-react';
import { ResearchDepth } from '../../types/research';
import { LoadingOrb } from '../common/LoadingOrb';

interface ResearchComposerProps {
  initialPrompt?: string;
  onStartResearch: (payload: {
    question: string;
    depth: ResearchDepth;
  }) => void;
  isLoading?: boolean;
}

const LOADING_MESSAGES = [
  'Searching your papers',
  'Ranking relevant evidence',
  'Preparing grounded answer',
];

export const ResearchComposer: React.FC<ResearchComposerProps> = ({
  initialPrompt = '',
  onStartResearch,
  isLoading = false,
}) => {
  const [prompt, setPrompt] = useState(initialPrompt);
  const [depth, setDepth] = useState<ResearchDepth>('standard');
  const [isDepthOpen, setIsDepthOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [loadingMessageIndex, setLoadingMessageIndex] = useState(0);

  useEffect(() => {
    setPrompt(initialPrompt);
  }, [initialPrompt]);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setIsDepthOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  useEffect(() => {
    if (!isLoading) {
      setLoadingMessageIndex(0);
      return;
    }
    const timer = window.setInterval(() => {
      setLoadingMessageIndex((index) =>
        Math.min(index + 1, LOADING_MESSAGES.length - 1)
      );
    }, 2500);
    return () => window.clearInterval(timer);
  }, [isLoading]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleSubmit = () => {
    if (!prompt.trim() || isLoading) return;
    onStartResearch({
      question: prompt.trim(),
      depth,
    });
  };

  const depthLabels: Record<ResearchDepth, string> = {
    quick: 'Quick',
    standard: 'Standard',
    deep: 'Deep',
  };

  return (
    <div className="w-full bg-panel border border-line rounded-xl shadow-xs transition-all duration-150 focus-within:border-accent focus-within:ring-1 focus-within:ring-accent">
      <div className="p-4 sm:p-5">
        <label htmlFor="research-prompt" className="sr-only">
          Research inquiry query or prompt
        </label>
        <textarea
          ref={textareaRef}
          id="research-prompt"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={handleKeyDown}
          rows={4}
          disabled={isLoading}
          className="w-full min-h-[148px] bg-transparent resize-none text-[15px] text-ink placeholder:text-ink-muted focus:outline-none leading-relaxed border-0 p-0 focus:ring-0"
          placeholder="Ask a research question or describe what you want to investigate…"
        />
      </div>

      <div className="px-4 py-2.5 bg-canvas rounded-b-[11px] border-t border-line flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2 relative">
          <div className="relative" ref={dropdownRef}>
            <button
              type="button"
              onClick={() => setIsDepthOpen(!isDepthOpen)}
              aria-expanded={isDepthOpen}
              aria-haspopup="menu"
              className="bg-panel text-ink-soft hover:text-ink border border-line text-xs font-medium px-2.5 py-1.5 rounded-md flex items-center gap-1 transition-colors duration-150 cursor-pointer"
            >
              <span>Research depth: {depthLabels[depth]}</span>
              <ChevronDown
                className={`w-3.5 h-3.5 text-ink-muted transition-transform duration-150 ${
                  isDepthOpen ? 'rotate-180' : ''
                }`}
              />
            </button>

            {isDepthOpen && (
              <div className="absolute left-0 bottom-full mb-1.5 w-52 bg-panel border border-line rounded-md shadow-md py-1 z-30 transition-all duration-150 text-xs">
                <button
                  type="button"
                  onClick={() => {
                    setDepth('quick');
                    setIsDepthOpen(false);
                  }}
                  className={`w-full text-left px-3 py-2 text-ink-soft hover:text-ink hover:bg-canvas flex items-center justify-between ${
                    depth === 'quick' ? 'bg-accent-soft/50' : ''
                  }`}
                >
                  <div>
                    <span className="font-medium text-ink block">Quick</span>
                    <span className="text-[10.5px] text-ink-muted">Fast overview &amp; summary</span>
                  </div>
                  {depth === 'quick' && <Check className="w-3.5 h-3.5 text-accent" />}
                </button>

                <button
                  type="button"
                  onClick={() => {
                    setDepth('standard');
                    setIsDepthOpen(false);
                  }}
                  className={`w-full text-left px-3 py-2 text-ink-soft hover:text-ink hover:bg-canvas flex items-center justify-between ${
                    depth === 'standard' ? 'bg-accent-soft/60' : ''
                  }`}
                >
                  <div>
                    <span className="font-medium text-accent block">Standard (Default)</span>
                    <span className="text-[10.5px] text-ink-muted">Multi-source verification</span>
                  </div>
                  {depth === 'standard' && <Check className="w-3.5 h-3.5 text-accent" />}
                </button>

                <button
                  type="button"
                  onClick={() => {
                    setDepth('deep');
                    setIsDepthOpen(false);
                  }}
                  className={`w-full text-left px-3 py-2 text-ink-soft hover:text-ink hover:bg-canvas flex items-center justify-between ${
                    depth === 'deep' ? 'bg-accent-soft/50' : ''
                  }`}
                >
                  <div>
                    <span className="font-medium text-ink block">Deep</span>
                    <span className="text-[10.5px] text-ink-muted">Comprehensive cross-synthesis</span>
                  </div>
                  {depth === 'deep' && <Check className="w-3.5 h-3.5 text-accent" />}
                </button>
              </div>
            )}
          </div>
        </div>

        <div className="flex items-center gap-3 ml-auto">
          <span className="text-[11px] text-ink-muted hidden md:inline">
            {isLoading ? LOADING_MESSAGES[loadingMessageIndex] : 'Uses your indexed papers only'}
          </span>
          <span className="text-[11.5px] text-ink-muted hidden sm:inline select-none">
            ⌘ + Enter
          </span>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={!prompt.trim() || isLoading}
            className="bg-solid hover:bg-solid-hover active:scale-[0.98] text-on-solid text-xs font-medium px-4 py-2 rounded-md flex items-center gap-1.5 transition-all duration-150 shadow-none cursor-pointer group disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {isLoading ? <LoadingOrb size={16} className="loading-orb--on-solid" /> : null}
            <span>{isLoading ? 'Researching...' : 'Start research'}</span>
            {!isLoading ? (
              <ArrowRight className="w-3.5 h-3.5 transition-transform duration-150 group-hover:translate-x-0.5" />
            ) : null}
          </button>
        </div>
      </div>
    </div>
  );
};
