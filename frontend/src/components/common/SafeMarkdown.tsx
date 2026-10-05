/**
 * SafeMarkdown: Renders model-generated Markdown safely without dangerouslySetInnerHTML.
 *
 * Uses a simple parse-and-render approach. The backend answer is plain text or
 * light Markdown (headers, bold, bullets, code spans). We render structure without
 * executing any HTML from the model output.
 *
 * This implementation handles the subset of Markdown that the research backend
 * actually produces. If a full Markdown library is needed in the future, install
 * a sanitizing renderer (e.g., react-markdown with rehype-sanitize).
 */
import React from 'react';

interface SafeMarkdownProps {
  content: string;
  className?: string;
}

/** Split text into inline segments: bold, code, and plain text. */
const parseInline = (text: string): React.ReactNode[] => {
  const segments: React.ReactNode[] = [];
  // Match **bold**, `code`, and plain text
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      segments.push(text.slice(lastIndex, match.index));
    }
    const token = match[1];
    if (token.startsWith('**')) {
      segments.push(
        <strong key={match.index} className="font-semibold text-[#181a18]">
          {token.slice(2, -2)}
        </strong>
      );
    } else if (token.startsWith('`')) {
      segments.push(
        <code
          key={match.index}
          className="font-mono text-[13px] bg-[#f5f5f2] px-1 py-0.5 rounded text-[#181a18]"
        >
          {token.slice(1, -1)}
        </code>
      );
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
  className = '',
}) => {
  const lines = content.split('\n');
  const elements: React.ReactNode[] = [];
  let listItems: React.ReactNode[] = [];
  let key = 0;

  const flushList = () => {
    if (listItems.length > 0) {
      elements.push(
        <ul key={`ul-${key++}`} className="list-disc pl-5 space-y-1 my-3">
          {listItems}
        </ul>
      );
      listItems = [];
    }
  };

  for (const rawLine of lines) {
    const line = rawLine;

    // H1
    if (line.startsWith('# ')) {
      flushList();
      elements.push(
        <h2
          key={key++}
          className="font-serif text-xl text-[#181a18] font-normal mt-5 mb-2 first:mt-0"
        >
          {parseInline(line.slice(2))}
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
          className={`font-semibold text-[#181a18] mt-4 mb-1.5 ${
            level === 2 ? 'text-base' : 'text-sm'
          }`}
        >
          {parseInline(text)}
        </h3>
      );
      continue;
    }

    // Bullet list items
    if (line.startsWith('- ') || line.startsWith('* ')) {
      listItems.push(
        <li key={key++} className="text-sm leading-relaxed text-[#2c302d]">
          {parseInline(line.slice(2))}
        </li>
      );
      continue;
    }

    // Numbered list
    const numMatch = /^(\d+)\.\s+(.*)$/.exec(line);
    if (numMatch) {
      listItems.push(
        <li key={key++} className="text-sm leading-relaxed text-[#2c302d]">
          {parseInline(numMatch[2])}
        </li>
      );
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
          className="border-l-2 border-[#163328] pl-4 my-3 italic text-[#424744] text-sm"
        >
          {parseInline(line.slice(2))}
        </blockquote>
      );
      continue;
    }

    // Horizontal rule
    if (/^---+$/.test(line.trim())) {
      flushList();
      elements.push(<hr key={key++} className="border-[#e5e7e4] my-4" />);
      continue;
    }

    // Regular paragraph
    flushList();
    elements.push(
      <p key={key++} className="text-sm leading-relaxed text-[#2c302d] my-1.5">
        {parseInline(line)}
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
