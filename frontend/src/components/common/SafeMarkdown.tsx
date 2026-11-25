/**
 * Renders the small Markdown subset the model is asked to produce.
 * HTML from the answer is never inserted as markup.
 */
import React from 'react';
import { AlertTriangle, Info } from 'lucide-react';

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

interface NestedListGroup {
  kind: ListKind;
  start: number;
  items: { key: number; content: React.ReactNode[] }[];
}

interface ListEntry {
  key: number;
  content: React.ReactNode[];
  children: NestedListGroup[];
}

const INLINE_PATTERN = /(\*\*[^*\n]+\*\*|`[^`\n]+`|\[S\d+\]|\*[^\s*\n](?:[^*\n]*[^\s*\n])?\*)/g;

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
    if (token.startsWith('**') && token.endsWith('**') && token.length > 4) {
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
    } else if (token.startsWith('*') && token.endsWith('*') && token.length > 2) {
      segments.push(
        <em key={key} className="italic text-ink">
          {token.slice(1, -1)}
        </em>
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

const splitTableRow = (line: string): string[] | null => {
  const trimmed = line.trim();
  if (!trimmed.startsWith('|') || !trimmed.slice(1).includes('|')) {
    return null;
  }
  const inner = trimmed.endsWith('|') ? trimmed.slice(1, -1) : trimmed.slice(1);
  return inner.split('|').map((cell) => cell.trim());
};

const isTableSeparatorRow = (line: string): boolean => {
  const cells = splitTableRow(line);
  if (!cells || cells.length === 0) return false;
  return cells.every((cell) => /^:?-{2,}:?$/.test(cell));
};

const indentWidth = (line: string): number => {
  let width = 0;
  for (const ch of line) {
    if (ch === ' ') width += 1;
    else if (ch === '\t') width += 2;
    else break;
  }
  return width;
};

export const SafeMarkdown: React.FC<SafeMarkdownProps> = ({
  content,
  className = 'text-sm',
  renderCitation,
}) => {
  const lines = content.split('\n');
  const elements: React.ReactNode[] = [];
  let listEntries: ListEntry[] = [];
  let listKind: ListKind = 'ul';
  let listStart = 1;
  let key = 0;

  const inline = (text: string) => parseInline(text, renderCitation, `i${key}`);

  const renderListEntries = (entries: ListEntry[]) =>
    entries.map((entry) => (
      <li key={entry.key} className="leading-relaxed text-ink">
        {entry.content}
        {entry.children.map((group, gIdx) =>
          group.kind === 'ol' ? (
            <ol
              key={`sub-ol-${entry.key}-${gIdx}`}
              start={group.start}
              className="list-decimal pl-5 space-y-1 mt-1.5"
            >
              {group.items.map((sub) => (
                <li key={sub.key} className="leading-relaxed text-ink-soft">
                  {sub.content}
                </li>
              ))}
            </ol>
          ) : (
            <ul
              key={`sub-ul-${entry.key}-${gIdx}`}
              className="list-[circle] pl-5 space-y-1 mt-1.5"
            >
              {group.items.map((sub) => (
                <li key={sub.key} className="leading-relaxed text-ink-soft">
                  {sub.content}
                </li>
              ))}
            </ul>
          )
        )}
      </li>
    ));

  const flushList = () => {
    if (listEntries.length === 0) return;
    if (listKind === 'ol') {
      elements.push(
        <ol
          key={`ol-${key++}`}
          start={listStart}
          className="list-decimal pl-5 space-y-1.5 my-3"
        >
          {renderListEntries(listEntries)}
        </ol>
      );
    } else {
      elements.push(
        <ul key={`ul-${key++}`} className="list-disc pl-5 space-y-1.5 my-3">
          {renderListEntries(listEntries)}
        </ul>
      );
    }
    listEntries = [];
  };

  const pushItem = (kind: ListKind, text: string, nested: boolean, start = 1) => {
    if (nested && listEntries.length > 0) {
      const parent = listEntries[listEntries.length - 1];
      const itemKey = key++;
      const contentNodes = parseInline(text, renderCitation, `i${itemKey}`);
      const lastGroup = parent.children[parent.children.length - 1];
      if (lastGroup && lastGroup.kind === kind) {
        lastGroup.items.push({ key: itemKey, content: contentNodes });
      } else {
        parent.children.push({
          kind,
          start,
          items: [{ key: itemKey, content: contentNodes }],
        });
      }
      return;
    }
    if (listEntries.length > 0 && listKind !== kind) flushList();
    if (listEntries.length === 0) {
      listKind = kind;
      listStart = start;
    }
    const itemKey = key++;
    listEntries.push({
      key: itemKey,
      content: parseInline(text, renderCitation, `i${itemKey}`),
      children: [],
    });
  };

  for (let idx = 0; idx < lines.length; idx++) {
    const rawLine = lines[idx];
    const leadIndent = indentWidth(rawLine);
    const trimmedLine = rawLine.trim();

    // Markdown table (header + separator + data rows)
    if (idx + 1 < lines.length && isTableSeparatorRow(lines[idx + 1])) {
      const headers = splitTableRow(rawLine);
      if (headers && headers.length > 0) {
        flushList();
        const rows: string[][] = [];
        let rowIdx = idx + 2;
        while (rowIdx < lines.length) {
          const cells = splitTableRow(lines[rowIdx]);
          if (!cells || isTableSeparatorRow(lines[rowIdx])) break;
          rows.push(cells);
          rowIdx += 1;
        }
        const tableKey = key++;
        elements.push(
          <div
            key={`table-${tableKey}`}
            className="my-3.5 overflow-x-auto rounded-lg border border-line"
          >
            <table className="w-full border-collapse text-left text-[13.5px] leading-snug">
              <thead className="bg-subtle border-b border-line">
                <tr>
                  {headers.map((header, colIdx) => (
                    <th
                      key={`th-${tableKey}-${colIdx}`}
                      className="px-3 py-2 font-sans text-xs font-semibold tracking-wide text-ink"
                    >
                      {parseInline(header, renderCitation, `th-${tableKey}-${colIdx}`)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {rows.map((cells, rowNumber) => (
                  <tr
                    key={`tr-${tableKey}-${rowNumber}`}
                    className="bg-panel hover:bg-subtle transition-colors"
                  >
                    {headers.map((_, colIdx) => (
                      <td
                        key={`td-${tableKey}-${rowNumber}-${colIdx}`}
                        className="px-3 py-2 align-top text-ink"
                      >
                        {parseInline(
                          cells[colIdx] ?? '',
                          renderCitation,
                          `td-${tableKey}-${rowNumber}-${colIdx}`,
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
        idx = rowIdx - 1;
        continue;
      }
    }

    // H1
    if (trimmedLine.startsWith('# ')) {
      flushList();
      elements.push(
        <h2
          key={key++}
          className="font-serif text-xl text-ink font-normal mt-5 mb-2 first:mt-0"
        >
          {inline(trimmedLine.slice(2))}
        </h2>
      );
      continue;
    }

    // H2/H3/H4
    const headingMatch = /^(#{2,4})\s+(.*)$/.exec(trimmedLine);
    if (headingMatch) {
      flushList();
      const level = headingMatch[1].length;
      const text = headingMatch[2];
      elements.push(
        <h3
          key={key++}
          className={`font-sans font-semibold text-ink mt-5 mb-1.5 first:mt-0 ${
            level === 2 ? 'text-base' : 'text-sm'
          }`}
        >
          {inline(text)}
        </h3>
      );
      continue;
    }

    // Structured callouts for source gaps and conflicting viewpoints
    if (leadIndent < 2) {
      const conflictMatch =
        /^(?:[-*+]\s+)?(?:\*\*)?(Competing accounts|Conflicting (?:accounts|claims|views|evidence))(?:\s*:\s*\*\*|\*\*\s*:|:)\s*(.+)$/i.exec(
          trimmedLine
        );
      const gapMatch = !conflictMatch
        ? /^(?:[-*+]\s+)?(?:\*\*)?Not covered in the sources(?:\s*:\s*\*\*|\*\*\s*:|:)\s*(.+)$/i.exec(
            trimmedLine
          )
        : null;
      if (conflictMatch || gapMatch) {
        flushList();
        const isConflict = Boolean(conflictMatch);
        const calloutTitle = conflictMatch ? conflictMatch[1] : 'Not covered in the sources';
        const calloutBody = conflictMatch ? conflictMatch[2] : gapMatch![1];
        const subItems: { key: number; content: React.ReactNode[] }[] = [];
        let subIdx = idx + 1;
        while (subIdx < lines.length) {
          const nextRaw = lines[subIdx];
          const nextTrimmed = nextRaw.trim();
          const subMatch =
            /^[-*+]\s+(.*)$/.exec(nextTrimmed) ?? /^\d+[.)]\s+(.*)$/.exec(nextTrimmed);
          if (indentWidth(nextRaw) >= 2 && subMatch) {
            const subKey = key++;
            subItems.push({
              key: subKey,
              content: parseInline(subMatch[1], renderCitation, `csub-${subKey}`),
            });
            subIdx += 1;
          } else {
            break;
          }
        }
        idx = subIdx - 1;
        const calloutKey = key++;
        elements.push(
          <div
            key={`callout-${calloutKey}`}
            role="note"
            className={`my-3.5 flex items-start gap-2.5 rounded-lg border px-3.5 py-2.5 font-sans text-[13.5px] leading-relaxed text-ink ${
              isConflict
                ? 'border-warning-line bg-warning-soft'
                : 'border-info-line bg-info-soft'
            }`}
          >
            {isConflict ? (
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" aria-hidden="true" />
            ) : (
              <Info className="mt-0.5 h-4 w-4 shrink-0 text-info" aria-hidden="true" />
            )}
            <div className="min-w-0 flex-1">
              <p className="m-0">
                <span className={`font-semibold ${isConflict ? 'text-warning' : 'text-info'}`}>
                  {calloutTitle}:
                </span>{' '}
                {parseInline(calloutBody, renderCitation, `callout-${calloutKey}`)}
              </p>
              {subItems.length > 0 && (
                <ul className="mt-1.5 list-disc space-y-1 pl-5 text-ink">
                  {subItems.map((sub) => (
                    <li key={sub.key}>{sub.content}</li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        );
        continue;
      }
    }

    // Bullet list items (support 2-level nesting when indented by >= 2 spaces)
    const bullet = /^[-*+]\s+(.*)$/.exec(trimmedLine);
    if (bullet) {
      pushItem('ul', bullet[1], leadIndent >= 2);
      continue;
    }

    // Numbered list (keeps its numbers, so steps read in order)
    const numbered = /^(\d+)[.)]\s+(.*)$/.exec(trimmedLine);
    if (numbered) {
      pushItem('ol', numbered[2], leadIndent >= 2, Number(numbered[1]));
      continue;
    }

    // Empty line – flush list
    if (!trimmedLine) {
      flushList();
      continue;
    }

    // Blockquote
    if (trimmedLine.startsWith('> ')) {
      flushList();
      elements.push(
        <blockquote
          key={key++}
          className="border-l-2 border-accent pl-4 my-3 italic text-ink-soft"
        >
          {inline(trimmedLine.slice(2))}
        </blockquote>
      );
      continue;
    }

    // Horizontal rule
    if (/^---+$/.test(trimmedLine)) {
      flushList();
      elements.push(<hr key={key++} className="border-line my-4" />);
      continue;
    }

    // Regular paragraph
    flushList();
    elements.push(
      <p key={key++} className="leading-relaxed text-ink my-2">
        {inline(trimmedLine)}
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
