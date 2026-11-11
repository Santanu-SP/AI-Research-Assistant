import React from 'react';
import { Link } from 'react-router-dom';

export const AuthShell: React.FC<React.PropsWithChildren<{ title: string; description: string }>> = ({ title, description, children }) => (
  <main className="min-h-screen bg-canvas text-ink flex flex-col">
    <header className="h-14 border-b border-line px-5 sm:px-8 flex items-center">
      <Link to="/" className="text-sm font-semibold tracking-tight text-accent">Research Assistant</Link>
    </header>
    <div className="flex-1 flex items-center justify-center px-4 py-12">
      <div className="w-full max-w-md">
        <div className="mb-7">
          <p className="text-[11px] uppercase tracking-[0.16em] font-semibold text-ink-soft mb-3">Your research workspace</p>
          <h1 className="font-serif text-4xl text-ink mb-2">{title}</h1>
          <p className="text-sm text-ink-soft">{description}</p>
        </div>
        <div className="bg-panel border border-line rounded-xl p-6 sm:p-8 shadow-xs">{children}</div>
      </div>
    </div>
  </main>
);

export const authInputClass = 'w-full rounded-md border border-line-strong bg-panel px-3 py-2.5 text-sm text-ink focus:outline-none focus:ring-1 focus:ring-accent focus:border-accent';
export const authLabelClass = 'block text-xs font-medium text-ink mb-1.5';
