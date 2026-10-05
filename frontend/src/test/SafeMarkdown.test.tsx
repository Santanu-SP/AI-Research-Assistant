/**
 * Tests for SafeMarkdown component – no XSS, correct structure, correct rendering.
 */
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import { SafeMarkdown } from '../components/common/SafeMarkdown';

describe('SafeMarkdown', () => {
  it('renders plain text paragraph', () => {
    render(<SafeMarkdown content="Hello world" />);
    expect(screen.getByText('Hello world')).toBeInTheDocument();
  });

  it('renders bold text with strong element', () => {
    const { container } = render(
      <SafeMarkdown content="This is **bold** text" />
    );
    const strong = container.querySelector('strong');
    expect(strong).toBeTruthy();
    expect(strong!.textContent).toBe('bold');
  });

  it('renders inline code with code element', () => {
    const { container } = render(
      <SafeMarkdown content="Use `useEffect` hook" />
    );
    const code = container.querySelector('code');
    expect(code).toBeTruthy();
    expect(code!.textContent).toBe('useEffect');
  });

  it('renders h1 markdown as h2 element', () => {
    const { container } = render(<SafeMarkdown content="# Main Heading" />);
    const heading = container.querySelector('h2');
    expect(heading).toBeTruthy();
    expect(heading!.textContent).toBe('Main Heading');
  });

  it('renders h2 markdown as h3 element', () => {
    const { container } = render(
      <SafeMarkdown content="## Section Heading" />
    );
    const heading = container.querySelector('h3');
    expect(heading).toBeTruthy();
  });

  it('renders bullet list items as ul/li', () => {
    const { container } = render(
      <SafeMarkdown content={'- Item one\n- Item two\n- Item three'} />
    );
    const list = container.querySelector('ul');
    expect(list).toBeTruthy();
    expect(list!.querySelectorAll('li')).toHaveLength(3);
  });

  it('renders blockquotes', () => {
    const { container } = render(
      <SafeMarkdown content="> This is a quote" />
    );
    const blockquote = container.querySelector('blockquote');
    expect(blockquote).toBeTruthy();
    expect(blockquote!.textContent).toBe('This is a quote');
  });

  it('does not render raw HTML from content', () => {
    const { container } = render(
      <SafeMarkdown content="<script>alert('xss')</script>" />
    );
    // The angle brackets should appear as text, not as DOM elements
    const scripts = container.querySelectorAll('script');
    expect(scripts).toHaveLength(0);
  });

  it('handles empty string without crashing', () => {
    const { container } = render(<SafeMarkdown content="" />);
    expect(container).toBeTruthy();
  });

  it('renders multiline content with mixed elements', () => {
    const content = `# Title\n\nSome paragraph.\n\n- Bullet 1\n- Bullet 2`;
    const { container } = render(<SafeMarkdown content={content} />);
    expect(container.querySelector('h2')).toBeTruthy();
    expect(container.querySelector('ul')).toBeTruthy();
    expect(container.querySelectorAll('li')).toHaveLength(2);
  });
});
