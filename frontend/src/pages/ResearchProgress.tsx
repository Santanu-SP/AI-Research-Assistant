import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { TopBar } from '../components/layout/TopBar';
import { ProgressStepper } from '../components/research/ProgressStepper';
import { researchService } from '../services/research.service';
import { ResearchProgress as IResearchProgress } from '../types/research';
import { Radio, Ban } from 'lucide-react';

export const ResearchProgressPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [progress, setProgress] = useState<IResearchProgress | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(48);

  useEffect(() => {
    researchService.getResearchProgress(id || 'tdp43-phase-separation').then((res) => {
      setProgress(res);
    });

    const timer = setInterval(() => {
      setElapsedSeconds((prev) => prev + 1);
    }, 1000);

    return () => clearInterval(timer);
  }, [id]);

  const formatElapsed = (sec: number) => {
    const mins = Math.floor(sec / 60);
    const remainingSec = sec % 60;
    return `${mins.toString().padStart(2, '0')}:${remainingSec.toString().padStart(2, '0')}`;
  };

  if (!progress) {
    return (
      <div className="min-h-screen bg-[#fafaf8] flex items-center justify-center">
        <div className="text-xs text-[#6b706c]">Loading investigation state…</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#fafaf8] flex flex-col">
      {/* TopBar */}
      <TopBar
        breadcrumbs={
          <div className="flex items-center gap-2">
            <Link to="/research" className="text-[#6b706c] hover:text-[#181a18]">
              Research
            </Link>
            <span className="text-[#929792]">/</span>
            <div className="flex items-center gap-1.5 text-[#163328] font-medium">
              <span className="w-2 h-2 rounded-full bg-emerald-600 animate-pulse" />
              <span>Active Investigation</span>
            </div>
          </div>
        }
        rightActions={
          <div className="flex items-center gap-3">
            <span className="text-xs text-[#6b706c] font-mono">
              {formatElapsed(elapsedSeconds)} elapsed
            </span>

            <button
              type="button"
              onClick={() => navigate('/research')}
              className="text-xs text-[#6b706c] hover:text-[#b91c1c] border border-[#e5e7e4] hover:border-[#fecaca] hover:bg-[#fee2e2]/30 px-2.5 py-1 rounded-md transition-colors flex items-center gap-1 cursor-pointer"
            >
              <Ban className="w-3 h-3" />
              <span>Cancel research</span>
            </button>
          </div>
        }
      />

      {/* Main Container */}
      <main className="flex-1 pt-14 pb-16 px-4 sm:px-6">
        <div className="max-w-5xl mx-auto py-8">
          {/* Header Metadata */}
          <div className="mb-6">
            <div className="flex flex-wrap items-center gap-2 text-xs text-[#6b706c] mb-2 font-mono">
              <span className="text-[#163328] font-semibold">{progress.dossierRef}</span>
              <span className="text-[#929792]">·</span>
              <span>Depth: Standard</span>
              <span className="text-[#929792]">·</span>
              <span>Started {progress.startedAt}</span>
            </div>

            <h1 className="font-serif text-2xl sm:text-3xl text-[#181a18] font-normal leading-snug">
              {progress.question}
            </h1>
          </div>

          {/* Stepper Component */}
          <ProgressStepper progress={progress} />

          {/* Dual Ingestion Panels: Live Evidence & Discovered Sources */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start mb-8">
            {/* Left 7 cols: Live Evidence Ingestion */}
            <div className="lg:col-span-7 flex flex-col gap-4">
              <div className="flex items-center justify-between pb-2 border-b border-[#e5e7e4]">
                <div className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-emerald-600 animate-ping" />
                  <span className="uppercase tracking-wider text-[11px] font-semibold text-[#163328]">
                    Live Evidence Ingestion
                  </span>
                </div>
                <span className="text-[11px] text-[#929792]">
                  Real-time pipeline
                </span>
              </div>

              {/* Live Evidence Cards */}
              <div className="flex flex-col gap-3">
                {progress.liveEvidence.map((item) => (
                  <div
                    key={item.id}
                    className="p-4 bg-white border border-[#e5e7e4] rounded-lg shadow-xs"
                  >
                    <div className="flex items-center justify-between gap-2 text-xs mb-1.5">
                      <div className="font-semibold text-[#163328] text-[11.5px]">
                        {item.publisher} · {item.year}
                      </div>
                      <span className="text-[10px] font-medium bg-[#f1f6f3] text-[#173d31] border border-[#d8e5df] px-2 py-0.5 rounded-full">
                        {item.statusTag}
                      </span>
                    </div>

                    <h4 className="text-[13.5px] font-medium text-[#181a18] leading-snug mb-2">
                      {item.title}
                    </h4>

                    <div className="bg-[#fafaf8] border-l-2 border-[#163328] pl-3 py-2 text-xs text-[#424744] italic rounded-r mb-2.5">
                      &ldquo;{item.excerpt}&rdquo;
                    </div>

                    <div className="flex items-center justify-between text-[11px] text-[#6b706c]">
                      <span>{item.authors}</span>
                      {item.identifierValue && (
                        <span className="font-mono text-[10.5px] text-[#929792]">
                          {item.identifierLabel}: {item.identifierValue}
                        </span>
                      )}
                    </div>
                  </div>
                ))}

                {/* Pulsing Active Analysis Log */}
                <div className="p-3 bg-[#f1f6f3]/80 border border-[#cbe0d5] rounded-lg flex items-center justify-between gap-2 text-xs">
                  <div className="flex items-center gap-2 text-[#163328] font-medium min-w-0">
                    <Radio className="w-4 h-4 text-emerald-600 animate-pulse shrink-0" />
                    <span className="truncate">
                      Synthesizing cross-correlation: Phosphorylation kinetics vs. amyloid formation
                    </span>
                  </div>
                  <span className="font-mono text-[10.5px] text-[#6b706c] shrink-0">
                    14:02:49
                  </span>
                </div>
              </div>
            </div>

            {/* Right 5 cols: Discovered Sources */}
            <div className="lg:col-span-5 flex flex-col gap-4">
              <div className="flex items-center justify-between pb-2 border-b border-[#e5e7e4]">
                <span className="uppercase tracking-wider text-[11px] font-semibold text-[#929792]">
                  Discovered Sources
                </span>
                <span className="text-[11px] text-[#6b706c]">
                  {progress.discoveredSources.length} matched
                </span>
              </div>

              <div className="flex flex-col gap-2">
                {progress.discoveredSources.map((source) => (
                  <div
                    key={source.id}
                    className="p-3 bg-white border border-[#e5e7e4] rounded-lg hover:border-[#cbd0ca] transition-colors"
                  >
                    <div className="flex items-center justify-between text-[10.5px] text-[#929792] mb-1">
                      <span>{source.publisher} · {source.year}</span>
                      <span>{source.sourceType}</span>
                    </div>

                    <h5 className="text-xs font-medium text-[#181a18] leading-snug line-clamp-2 mb-1">
                      {source.title}
                    </h5>

                    <div className="flex items-center justify-between text-[11px] text-[#6b706c]">
                      <span className="truncate">{source.authors}</span>
                    </div>
                  </div>
                ))}

                {/* Queue status */}
                <div className="p-3 bg-white border border-dashed border-[#d0d7d2] rounded-lg text-center text-xs text-[#6b706c]">
                  Ingesting {progress.ingestingQueueCount} pending citations… Queue: {progress.ingestingQueueCount}
                </div>
              </div>
            </div>
          </div>

        </div>
      </main>
    </div>
  );
};
