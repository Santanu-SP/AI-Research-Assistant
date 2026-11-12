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
  'Gathering the strongest evidence',
  'Writing your answer',
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
    <div className="w-full rounded-xl border border-line-strong bg-panel shadow-sm transition-shadow duration-150 focus-within:border-accent focus-within:shadow-[0_0_0_3px_color-mix(in_srgb,var(--app-accent)_16%,transparent)]">
      <div className="p-4 sm:p-5">
        <label htmlFor="research-prompt" className="sr-only">
          Research question
        </label>
        <textarea
          ref={textareaRef}
          id="research-prompt"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={handleKeyDown}
          rows={4}
          disabled={isLoading}
          className="w-full min-h-[120px] resize-none border-0 bg-transparent p-0 text-[15px] leading-relaxed text-ink placeholder:text-ink-muted focus:outline-none focus-visible:outline-none"
          placeholder="Ask a question about your papers, e.g. Does residence time predict in-vivo efficacy better than affinity?"
        />
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 rounded-b-[13px] border-t border-line bg-subtle/50 px-3 py-2.5 sm:px-4">
        <div className="flex flex-wrap items-center gap-2 relative">
          <div className="relative" ref={dropdownRef}>
            <button
              type="button"
              onClick={() => setIsDepthOpen(!isDepthOpen)}
              aria-expanded={isDepthOpen}
              aria-haspopup="menu"
              className="flex h-8 cursor-pointer items-center gap-1.5 rounded-md border border-line bg-panel px-2.5 text-xs font-medium text-ink-soft transition-colors duration-150 hover:border-line-strong hover:text-ink"
            >
              <span className="text-ink-muted">Depth</span>
              <span className="text-ink">{depthLabels[depth]}</span>
              <ChevronDown
                className={`w-3.5 h-3.5 text-ink-muted transition-transform duration-150 ${
                  isDepthOpen ? 'rotate-180' : ''
                }`}
              />
            </button>

            {isDepthOpen && (
              <div role="menu" className="absolute bottom-full left-0 z-30 mb-1.5 w-60 rounded-lg border border-line bg-panel py-1 text-xs shadow-lg">
                <button
                  type="button"
                  onClick={() => {
                    setDepth('quick');
                    setIsDepthOpen(false);
                  }}
                  className={`w-full text-left px-3 py-2 text-ink-soft hover:text-ink hover:bg-subtle flex items-center justify-between ${
                    depth === 'quick' ? 'bg-subtle' : ''
                  }`}
                >
                  <div>
                    <span className="font-medium text-ink block">Quick</span>
                    <span className="text-[11px] text-ink-muted">A short answer from the strongest passages</span>
                  </div>
                  {depth === 'quick' && <Check className="w-3.5 h-3.5 text-accent" />}
                </button>

                <button
                  type="button"
                  onClick={() => {
                    setDepth('standard');
                    setIsDepthOpen(false);
                  }}
                  className={`w-full text-left px-3 py-2 text-ink-soft hover:text-ink hover:bg-subtle flex items-center justify-between ${
                    depth === 'standard' ? 'bg-subtle' : ''
                  }`}
                >
                  <div>
                    <span className="font-medium text-ink block">Standard</span>
                    <span className="text-[11px] text-ink-muted">Balanced coverage across your papers</span>
                  </div>
                  {depth === 'standard' && <Check className="w-3.5 h-3.5 text-accent" />}
                </button>

                <button
                  type="button"
                  onClick={() => {
                    setDepth('deep');
                    setIsDepthOpen(false);
                  }}
                  className={`w-full text-left px-3 py-2 text-ink-soft hover:text-ink hover:bg-subtle flex items-center justify-between ${
                    depth === 'deep' ? 'bg-subtle' : ''
                  }`}
                >
                  <div>
                    <span className="font-medium text-ink block">Deep</span>
                    <span className="text-[11px] text-ink-muted">More passages, longer synthesis</span>
                  </div>
                  {depth === 'deep' && <Check className="w-3.5 h-3.5 text-accent" />}
                </button>
              </div>
            )}
          </div>
        </div>

        <div className="flex items-center gap-3 ml-auto">
          <span className="hidden text-xs text-ink-muted md:inline">
            {isLoading ? LOADING_MESSAGES[loadingMessageIndex] : 'Answers use your documents only'}
          </span>
          <kbd className="hidden select-none rounded border border-line bg-panel px-1.5 py-0.5 font-mono text-[10.5px] text-ink-muted sm:inline">
            ⌘ Enter
          </kbd>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={!prompt.trim() || isLoading}
            className="group flex h-8 cursor-pointer items-center gap-1.5 rounded-md bg-solid px-3.5 text-[13px] font-medium text-on-solid shadow-xs transition-colors duration-150 hover:bg-solid-hover disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isLoading ? <LoadingOrb size={16} className="loading-orb--on-solid" /> : null}
            <span>{isLoading ? 'Researching…' : 'Start research'}</span>
            {!isLoading ? (
              <ArrowRight className="w-3.5 h-3.5 transition-transform duration-150 group-hover:translate-x-0.5" />
            ) : null}
          </button>
        </div>
      </div>
    </div>
  );
};
