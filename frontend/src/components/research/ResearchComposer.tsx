import React, { useState, useEffect, useRef } from 'react';
import { Check, FileText, ChevronDown, ArrowRight, Plus } from 'lucide-react';
import { ResearchDepth } from '../../types/research';
import { LoadingOrb } from '../common/LoadingOrb';

interface ResearchComposerProps {
  initialPrompt?: string;
  onStartResearch: (payload: {
    question: string;
    depth: ResearchDepth;
    includeWeb: boolean;
    includeDocs: boolean;
  }) => void;
  isLoading?: boolean;
}

export const ResearchComposer: React.FC<ResearchComposerProps> = ({
  initialPrompt = 'How do post-translational modifications regulate TDP-43 phase separation in neurodegenerative phenotypes?',
  onStartResearch,
  isLoading = false,
}) => {
  const [prompt, setPrompt] = useState(initialPrompt);
  const [includeWeb, setIncludeWeb] = useState(true);
  const [includeDocs, setIncludeDocs] = useState(true);
  const [depth, setDepth] = useState<ResearchDepth>('standard');
  const [isDepthOpen, setIsDepthOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

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
      includeWeb,
      includeDocs,
    });
  };

  const depthLabels: Record<ResearchDepth, string> = {
    quick: 'Quick',
    standard: 'Standard',
    deep: 'Deep',
  };

  return (
    <div className="w-full bg-white border border-[#e5e7e4] rounded-xl shadow-xs transition-all duration-150 focus-within:border-[#163328] focus-within:ring-1 focus-within:ring-[#163328]">
      {/* Textarea container */}
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
          className="w-full min-h-[148px] bg-transparent resize-none text-[15px] text-[#181a18] placeholder:text-[#929792] focus:outline-none leading-relaxed border-0 p-0 focus:ring-0"
          placeholder="Ask a research question or describe what you want to investigate…"
        />
      </div>

      {/* Composer Bottom Toolbar */}
      <div className="px-4 py-2.5 bg-[#fafaf8] rounded-b-[11px] border-t border-[#e5e7e4] flex flex-wrap items-center justify-between gap-3">
        {/* Left Controls: Chips & Depth Dropdown */}
        <div className="flex flex-wrap items-center gap-2 relative">
          {/* Selectable: Web & Academic */}
          <button
            type="button"
            onClick={() => setIncludeWeb(!includeWeb)}
            aria-pressed={includeWeb}
            className={`text-xs font-medium px-2.5 py-1.5 rounded-md flex items-center gap-1.5 transition-all duration-150 cursor-pointer active:scale-[0.98] ${
              includeWeb
                ? 'bg-[#f1f6f3] text-[#163328] border border-[#cbe0d5]'
                : 'bg-white text-[#6b706c] border border-[#e5e7e4] hover:text-[#181a18]'
            }`}
          >
            {includeWeb ? (
              <Check className="w-3.5 h-3.5 text-[#163328]" />
            ) : (
              <Plus className="w-3.5 h-3.5 text-[#929792]" />
            )}
            <span>Web &amp; academic</span>
          </button>

          {/* Selectable: Uploaded Documents */}
          <button
            type="button"
            onClick={() => setIncludeDocs(!includeDocs)}
            aria-pressed={includeDocs}
            className={`text-xs font-medium px-2.5 py-1.5 rounded-md flex items-center gap-1.5 transition-all duration-150 cursor-pointer active:scale-[0.98] ${
              includeDocs
                ? 'bg-[#f1f6f3] text-[#163328] border border-[#cbe0d5]'
                : 'bg-white text-[#6b706c] border border-[#e5e7e4] hover:text-[#181a18]'
            }`}
          >
            <FileText className={`w-3.5 h-3.5 ${includeDocs ? 'text-[#163328]' : 'text-[#929792]'}`} />
            <span>Documents</span>
          </button>

          {/* Research Depth Dropdown Trigger */}
          <div className="relative" ref={dropdownRef}>
            <button
              type="button"
              onClick={() => setIsDepthOpen(!isDepthOpen)}
              aria-expanded={isDepthOpen}
              aria-haspopup="menu"
              className="bg-white text-[#6b706c] hover:text-[#181a18] border border-[#e5e7e4] text-xs font-medium px-2.5 py-1.5 rounded-md flex items-center gap-1 transition-colors duration-150 cursor-pointer"
            >
              <span>Research depth: {depthLabels[depth]}</span>
              <ChevronDown
                className={`w-3.5 h-3.5 text-[#929792] transition-transform duration-150 ${
                  isDepthOpen ? 'rotate-180' : ''
                }`}
              />
            </button>

            {/* Dropdown Menu */}
            {isDepthOpen && (
              <div className="absolute left-0 bottom-full mb-1.5 w-52 bg-white border border-[#e5e7e4] rounded-md shadow-md py-1 z-30 transition-all duration-150 text-xs">
                <button
                  type="button"
                  onClick={() => {
                    setDepth('quick');
                    setIsDepthOpen(false);
                  }}
                  className={`w-full text-left px-3 py-2 text-[#6b706c] hover:text-[#181a18] hover:bg-[#fafaf8] flex items-center justify-between ${
                    depth === 'quick' ? 'bg-[#f1f6f3]/50' : ''
                  }`}
                >
                  <div>
                    <span className="font-medium text-[#181a18] block">Quick</span>
                    <span className="text-[10.5px] text-[#929792]">Fast overview &amp; summary</span>
                  </div>
                  {depth === 'quick' && <Check className="w-3.5 h-3.5 text-[#163328]" />}
                </button>

                <button
                  type="button"
                  onClick={() => {
                    setDepth('standard');
                    setIsDepthOpen(false);
                  }}
                  className={`w-full text-left px-3 py-2 text-[#6b706c] hover:text-[#181a18] hover:bg-[#fafaf8] flex items-center justify-between ${
                    depth === 'standard' ? 'bg-[#f1f6f3]/60' : ''
                  }`}
                >
                  <div>
                    <span className="font-medium text-[#163328] block">Standard (Default)</span>
                    <span className="text-[10.5px] text-[#929792]">Multi-source verification</span>
                  </div>
                  {depth === 'standard' && <Check className="w-3.5 h-3.5 text-[#163328]" />}
                </button>

                <button
                  type="button"
                  onClick={() => {
                    setDepth('deep');
                    setIsDepthOpen(false);
                  }}
                  className={`w-full text-left px-3 py-2 text-[#6b706c] hover:text-[#181a18] hover:bg-[#fafaf8] flex items-center justify-between ${
                    depth === 'deep' ? 'bg-[#f1f6f3]/50' : ''
                  }`}
                >
                  <div>
                    <span className="font-medium text-[#181a18] block">Deep</span>
                    <span className="text-[10.5px] text-[#929792]">Comprehensive cross-synthesis</span>
                  </div>
                  {depth === 'deep' && <Check className="w-3.5 h-3.5 text-[#163328]" />}
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Right CTA Button & Helper */}
        <div className="flex items-center gap-3 ml-auto">
          <span className="text-[11.5px] text-[#929792] hidden sm:inline select-none">
            ⌘ + Enter
          </span>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={!prompt.trim() || isLoading}
            className="bg-[#163328] hover:bg-[#214f40] active:scale-[0.98] text-white text-xs font-medium px-4 py-2 rounded-md flex items-center gap-1.5 transition-all duration-150 shadow-none cursor-pointer group disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {isLoading ? <LoadingOrb size={16} className="loading-orb--on-solid" /> : null}
            <span>{isLoading ? 'Creating research...' : 'Create research'}</span>
            {!isLoading ? (
              <ArrowRight className="w-3.5 h-3.5 transition-transform duration-150 group-hover:translate-x-0.5" />
            ) : null}
          </button>
        </div>
      </div>
    </div>
  );
};
