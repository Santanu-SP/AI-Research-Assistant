import React from 'react';
import { Link } from 'react-router-dom';

export const AuthShell: React.FC<React.PropsWithChildren<{ title: string; description: string }>> = ({ title, description, children }) => (
  <main className="min-h-screen bg-[#fafaf8] text-[#181a18] flex flex-col">
    <header className="h-14 border-b border-[#e5e7e4] px-5 sm:px-8 flex items-center">
      <Link to="/" className="text-sm font-semibold tracking-tight text-[#163328]">Research Assistant</Link>
    </header>
    <div className="flex-1 flex items-center justify-center px-4 py-12">
      <div className="w-full max-w-md">
        <div className="mb-7">
          <p className="text-[11px] uppercase tracking-[0.16em] font-semibold text-[#6b706c] mb-3">Your research workspace</p>
          <h1 className="font-serif text-4xl text-[#181a18] mb-2">{title}</h1>
          <p className="text-sm text-[#6b706c]">{description}</p>
        </div>
        <div className="bg-white border border-[#e5e7e4] rounded-xl p-6 sm:p-8 shadow-xs">{children}</div>
      </div>
    </div>
  </main>
);

export const authInputClass = 'w-full rounded-md border border-[#d0d7d2] bg-white px-3 py-2.5 text-sm text-[#181a18] focus:outline-none focus:ring-1 focus:ring-[#163328] focus:border-[#163328]';
export const authLabelClass = 'block text-xs font-medium text-[#181a18] mb-1.5';
