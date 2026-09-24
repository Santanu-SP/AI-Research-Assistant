import React from 'react';
import { LandingNav } from '../components/landing/LandingNav';
import { HeroSection } from '../components/landing/HeroSection';
import { PrinciplePanel, ProductShowcase } from '../components/landing/ProductShowcase';
import { BenefitsSection, PrivacySection, WorkflowSection } from '../components/landing/WorkflowSections';
import { UseCasesCarousel } from '../components/landing/UseCasesCarousel';
import { FAQSection } from '../components/landing/FAQSection';
import { FinalCTA, LandingFooter } from '../components/landing/FinalSections';
import '../components/landing/landing.css';

export const LandingPage: React.FC = () => (
  <div className="landing-page">
    <div className="landing-announcement" role="status">
      <span>Research with evidence, not guesswork.</span>
      <small>Upload papers. Ask questions. Trace every answer.</small>
    </div>
    <LandingNav />
    <main>
      <HeroSection />
      <ProductShowcase />
      <PrinciplePanel />
      <WorkflowSection />
      <BenefitsSection />
      <PrivacySection />
      <UseCasesCarousel />
      <FAQSection />
      <FinalCTA />
    </main>
    <LandingFooter />
  </div>
);
