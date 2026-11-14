import React, { useState, useEffect, useRef } from 'react';
import { ArrowRight } from 'lucide-react';
import { ResearchDepth } from '../../types/research';
import { LoadingOrb } from '../common/LoadingOrb';
import { ModelControlBar } from './ModelControlBar';
import { shortcutLabel } from '../../lib/shortcuts';

interface ResearchComposerProps {
  initialPrompt?: string;
  onStartResearch: (payload: {
    question: string;
    depth: ResearchDepth;
    preferredProvider?: string | null;
    modelOverride?: string | null;
    localFallbackEnabled?: boolean;
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
  const [preferredProvider, setPreferredProvider] = useState<string | null>(null);
  const [modelOverride, setModelOverride] = useState<string | null>(null);
  const [localFallbackEnabled, setLocalFallbackEnabled] = useState<boolean | undefined>(undefined);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [loadingMessageIndex, setLoadingMessageIndex] = useState(0);
  const lastSubmitAt = useRef(0);

  useEffect(() => {
    setPrompt(initialPrompt);
  }, [initialPrompt]);

  useEffect(() => {
    if (!isLoading) {
      setLoadingMessageIndex(0);
      return;
    }
    const timer = window.setInterval(() => {
      setLoadingMessageIndex((index) =>
        Math.min(index + 1, LOADING_MESSAGES.length - 1)
      );
    }, 1100);
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
    // isLoading only updates on the next render; block a second press now.
    const now = Date.now();
    if (now - lastSubmitAt.current < 1500) return;
    lastSubmitAt.current = now;
    onStartResearch({
      question: prompt.trim(),
      depth,
      preferredProvider,
      modelOverride,
      localFallbackEnabled,
    });
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
          <ModelControlBar
            depth={depth}
            onDepthChange={setDepth}
            preferredProvider={preferredProvider}
            onPreferredProviderChange={setPreferredProvider}
            modelOverride={modelOverride}
            onModelOverrideChange={setModelOverride}
            localFallbackEnabled={localFallbackEnabled}
            onLocalFallbackChange={setLocalFallbackEnabled}
            disabled={isLoading}
            menuPlacement="up"
          />
        </div>

        <div className="ml-auto flex items-center gap-3">
          {isLoading ? (
            <span className="hidden text-xs text-ink-muted md:inline" aria-live="polite">
              {LOADING_MESSAGES[loadingMessageIndex]}
            </span>
          ) : (
            <kbd className="hidden select-none rounded border border-line bg-panel px-1.5 py-0.5 font-sans text-[10.5px] text-ink-muted xl:inline">
              {shortcutLabel('Enter')}
            </kbd>
          )}
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
