/**
 * Renders the small Markdown subset the model is asked to produce.
 * HTML from the answer is never inserted as markup.
 */
import React from 'react';

interface SafeMarkdownProps {
  content: string;
  className?: string;
  /**
   * Draws an inline source marker such as [S2]. Without it, markers stay as
   * plain text.
   */
  renderCitation?: (sourceNumber: number, key: string) => React.ReactNode;
}

type ListKind = 'ul' | 'ol';

const INLINE_PATTERN = /(\*\*[^*]+\*\*|`[^`]+`|\[S\d+\])/g;

const parseInline = (
  text: string,
  renderCitation?: SafeMarkdownProps['renderCitation'],
  keyPrefix = '',
): React.ReactNode[] => {
  const segments: React.ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  const pattern = new RegExp(INLINE_PATTERN.source, 'g');

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      segments.push(text.slice(lastIndex, match.index));
    }
    const token = match[1];
    const key = `${keyPrefix}-${match.index}`;
    if (token.startsWith('**')) {
      segments.push(
        <strong key={key} className="font-semibold text-ink">
          {token.slice(2, -2)}
        </strong>
      );
    } else if (token.startsWith('`')) {
      segments.push(
        <code
          key={key}
          className="font-mono text-[13px] bg-subtle px-1 py-0.5 rounded text-ink"
        >
          {token.slice(1, -1)}
        </code>
      );
    } else if (renderCitation) {
      segments.push(renderCitation(Number(token.slice(2, -1)), key));
    } else {
      segments.push(token);
    }
    lastIndex = match.index + token.length;
  }
  if (lastIndex < text.length) {
    segments.push(text.slice(lastIndex));
  }
  return segments;
};

export const SafeMarkdown: React.FC<SafeMarkdownProps> = ({
  content,
  className = 'text-sm',
  renderCitation,
}) => {
  const lines = content.split('\n');
  const elements: React.ReactNode[] = [];
  let listItems: React.ReactNode[] = [];
  let listKind: ListKind = 'ul';
  let listStart = 1;
  let key = 0;

  const inline = (text: string) => parseInline(text, renderCitation, `i${key}`);

  const flushList = () => {
    if (listItems.length === 0) return;
    if (listKind === 'ol') {
      elements.push(
        <ol
          key={`ol-${key++}`}
          start={listStart}
          className="list-decimal pl-5 space-y-1.5 my-3"
        >
          {listItems}
        </ol>
      );
    } else {
      elements.push(
        <ul key={`ul-${key++}`} className="list-disc pl-5 space-y-1.5 my-3">
          {listItems}
        </ul>
      );
    }
    listItems = [];
  };

  const pushItem = (kind: ListKind, text: string, start = 1) => {
    if (listItems.length > 0 && listKind !== kind) flushList();
    if (listItems.length === 0) {
      listKind = kind;
      listStart = start;
    }
    listItems.push(
      <li key={key++} className="leading-relaxed text-ink">
        {inline(text)}
      </li>
    );
  };

  for (const rawLine of lines) {
    // Models indent sub-points; treat them as items of the same list.
    const line = rawLine.replace(/^\s+(?=([-*+]|\d+[.)])\s)/, '');

    // H1
    if (line.startsWith('# ')) {
      flushList();
      elements.push(
        <h2
          key={key++}
          className="font-serif text-xl text-ink font-normal mt-5 mb-2 first:mt-0"
        >
          {inline(line.slice(2))}
        </h2>
      );
      continue;
    }

    // H2/H3
    if (line.startsWith('## ') || line.startsWith('### ')) {
      flushList();
      const level = line.startsWith('### ') ? 3 : 2;
      const text = line.slice(level + 1);
      elements.push(
        <h3
          key={key++}
          className={`font-semibold text-ink mt-4 mb-1.5 ${
            level === 2 ? 'text-base' : 'text-sm'
          }`}
        >
          {inline(text)}
        </h3>
      );
      continue;
    }

    // Bullet list items
    const bullet = /^[-*+]\s+(.*)$/.exec(line);
    if (bullet) {
      pushItem('ul', bullet[1]);
      continue;
    }

    // Numbered list (keeps its numbers, so steps read in order)
    const numbered = /^(\d+)[.)]\s+(.*)$/.exec(line);
    if (numbered) {
      pushItem('ol', numbered[2], Number(numbered[1]));
      continue;
    }

    // Empty line – flush list
    if (!line.trim()) {
      flushList();
      continue;
    }

    // Blockquote
    if (line.startsWith('> ')) {
      flushList();
      elements.push(
        <blockquote
          key={key++}
          className="border-l-2 border-accent pl-4 my-3 italic text-ink-soft"
        >
          {inline(line.slice(2))}
        </blockquote>
      );
      continue;
    }

    // Horizontal rule
    if (/^---+$/.test(line.trim())) {
      flushList();
      elements.push(<hr key={key++} className="border-line my-4" />);
      continue;
    }

    // Regular paragraph
    flushList();
    elements.push(
      <p key={key++} className="leading-relaxed text-ink my-1.5">
        {inline(line)}
      </p>
    );
  }

  flushList();

  return (
    <div
      className={`prose-like ${className}`}
      aria-label="Research answer"
    >
      {elements}
    </div>
  );
};
