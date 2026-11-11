import React from 'react';
import { LandingNav } from '../components/landing/LandingNav';
import {
  FAQ,
  Features,
  FinalCta,
  Hero,
  HowItWorks,
  LandingFooter,
  Pipeline,
} from '../components/landing/LandingSections';

export const LandingPage: React.FC = () => (
  <div className="min-h-screen bg-canvas text-ink">
    <a
      href="#main"
      className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-[100] focus:rounded-md focus:bg-panel focus:px-3 focus:py-2 focus:text-sm focus:shadow-md"
    >
      Skip to content
    </a>
    <LandingNav />
    <main id="main">
      <Hero />
      <HowItWorks />
      <Features />
      <Pipeline />
      <FAQ />
      <FinalCta />
    </main>
    <LandingFooter />
  </div>
);
