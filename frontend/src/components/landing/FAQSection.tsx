import React, { useState } from 'react';
import { ArrowLink, Eyebrow, Reveal } from './LandingPrimitives';

const faqs = [
  ['What makes an answer “grounded”?', 'Grounded answers are generated from evidence retrieved from your indexed document collection rather than being presented without source context.'],
  ['Can I upload my own research papers?', 'Yes. The document workflow accepts research PDFs and prepares extractable text for indexing and retrieval.'],
  ['How does the assistant find relevant evidence?', 'The system combines semantic vector search with keyword and full-text retrieval before later evidence-selection stages.'],
  ['Can I inspect the source behind an answer?', 'The research experience is designed to preserve source metadata such as document, page, section, and supporting excerpt when available.'],
  ['Does it search across another user’s documents?', 'No. Retrieval is scoped to the authenticated user’s documents.'],
  ['Which AI models power the research pipeline?', 'The current retrieval foundation uses Qwen embeddings with PostgreSQL and pgvector. Reranking and local generation are the planned next stages of the Qwen-based pipeline.'],
] as const;

export const FAQSection: React.FC = () => {
  const [open, setOpen] = useState(0);
  return (
    <section id="faq" className="landing-faq" aria-labelledby="faq-heading">
      <div className="landing-container faq-grid">
        <div className="faq-intro">
          <Reveal><Eyebrow>FAQ</Eyebrow></Reveal>
          <Reveal variant="clip" delay={60}><h2 id="faq-heading" className="landing-section-title">Questions<br />& answers</h2></Reveal>
          <Reveal delay={120}><ArrowLink to="/register" tone="outline">Start researching</ArrowLink></Reveal>
        </div>
        <Reveal className="faq-list">
          {faqs.map(([question, answer], index) => {
            const expanded = open === index;
            return <div key={question} className={`faq-item ${expanded ? 'is-open' : ''}`}>
              <h3><button type="button" aria-expanded={expanded} aria-controls={`faq-answer-${index}`} onClick={() => setOpen(expanded ? -1 : index)}><span>{question}</span><span className="faq-toggle-icon" aria-hidden="true"><i /><i /></span></button></h3>
              <div id={`faq-answer-${index}`} className="faq-answer" aria-hidden={!expanded}><div><p>{answer}</p></div></div>
            </div>;
          })}
        </Reveal>
      </div>
    </section>
  );
};
