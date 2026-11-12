import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Link } from 'react-router-dom';
import { MoreHorizontal, Pencil, Trash2 } from 'lucide-react';
import { ResearchResponse } from '../../types/research';
import { useToast } from '../../app/ToastContext';
import { getResearchErrorMessage } from '../../services/research.service';

interface ResearchHistoryItemProps {
  item: ResearchResponse;
  to: string;
  active: boolean;
  highlight?: string;
  onNavigate?: () => void;
  onRename: (title: string) => Promise<void>;
  onDelete: () => void;
}

const STATUS_LABEL: Record<string, string> = {
  researching: 'In progress',
  failed: 'Failed',
  draft: 'Draft',
};

/** Bolds the part of the title that matches the search. */
const Highlighted: React.FC<{ text: string; query?: string }> = ({ text, query }) => {
  if (!query) return <>{text}</>;
  const index = text.toLowerCase().indexOf(query);
  if (index < 0) return <>{text}</>;
  return (
    <>
      {text.slice(0, index)}
      <mark className="rounded-[2px] bg-accent-soft px-px text-ink">{text.slice(index, index + query.length)}</mark>
      {text.slice(index + query.length)}
    </>
  );
};

export const ResearchHistoryItem: React.FC<ResearchHistoryItemProps> = ({
  item,
  to,
  active,
  highlight,
  onNavigate,
  onRename,
  onDelete,
}) => {
  const { addToast } = useToast();
  const [menuOpen, setMenuOpen] = useState(false);
  const [menuPosition, setMenuPosition] = useState<{ top: number; left: number } | null>(null);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(item.title);
  const [saving, setSaving] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useLayoutEffect(() => {
    if (!menuOpen || !triggerRef.current) return;
    const rect = triggerRef.current.getBoundingClientRect();
    const width = 168;
    const height = 84;
    const top = rect.bottom + 4 + height > window.innerHeight ? rect.top - height - 4 : rect.bottom + 4;
    setMenuPosition({ top, left: Math.max(8, rect.right - width) });
  }, [menuOpen]);

  useEffect(() => {
    if (!menuOpen) return;
    const close = (event: Event) => {
      const target = event.target as Node;
      if (menuRef.current?.contains(target) || triggerRef.current?.contains(target)) return;
      setMenuOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopPropagation();
        setMenuOpen(false);
        triggerRef.current?.focus();
      }
    };
    const onScroll = () => setMenuOpen(false);
    document.addEventListener('mousedown', close);
    document.addEventListener('keydown', onKey, true);
    window.addEventListener('resize', onScroll);
    document.addEventListener('scroll', onScroll, true);
    window.requestAnimationFrame(() => menuRef.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus());
    return () => {
      document.removeEventListener('mousedown', close);
      document.removeEventListener('keydown', onKey, true);
      window.removeEventListener('resize', onScroll);
      document.removeEventListener('scroll', onScroll, true);
    };
  }, [menuOpen]);

  useEffect(() => {
    if (editing) {
      setDraft(item.title);
      window.requestAnimationFrame(() => {
        inputRef.current?.focus();
        inputRef.current?.select();
      });
    }
  }, [editing, item.title]);

  const commit = async () => {
    const title = draft.trim();
    if (!title || title === item.title) {
      setEditing(false);
      return;
    }
    setSaving(true);
    try {
      await onRename(title);
      setEditing(false);
    } catch (error) {
      addToast({
        type: 'error',
        title: 'Could not rename',
        description: getResearchErrorMessage(error, 'Please try again.'),
      });
    } finally {
      setSaving(false);
    }
  };

  if (editing) {
    return (
      <li>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void commit();
          }}
          className="flex h-8 items-center rounded-md bg-subtle px-1"
        >
          <input
            ref={inputRef}
            value={draft}
            disabled={saving}
            maxLength={200}
            aria-label="Research title"
            onChange={(event) => setDraft(event.target.value)}
            onBlur={() => void commit()}
            onKeyDown={(event) => {
              if (event.key === 'Escape') {
                event.stopPropagation();
                setEditing(false);
              }
            }}
            className="h-6 w-full rounded border border-accent-line bg-panel px-1.5 text-[13px] text-ink focus:outline-none"
          />
        </form>
      </li>
    );
  }

  const statusLabel = STATUS_LABEL[item.status];

  return (
    <li className="group/item relative">
      <Link
        to={to}
        onClick={onNavigate}
        title={item.title}
        aria-current={active ? 'page' : undefined}
        className={`flex h-8 items-center gap-2 rounded-md pl-2.5 text-[13px] transition-colors ${
          active || menuOpen
            ? 'bg-subtle pr-2.5 font-medium text-ink [@media(hover:none)]:pr-9'
            : 'pr-2.5 text-ink-soft hover:bg-subtle hover:text-ink [@media(hover:none)]:pr-9'
        }`}
      >
        <span className="min-w-0 flex-1 truncate">
          <Highlighted text={item.title} query={highlight} />
        </span>
        {statusLabel && (
          <span
            title={statusLabel}
            className={`h-1.5 w-1.5 shrink-0 rounded-full ${
              item.status === 'researching'
                ? 'animate-pulse bg-warning'
                : item.status === 'failed'
                  ? 'bg-danger'
                  : 'border border-ink-muted'
            }`}
          >
            <span className="sr-only">{statusLabel}</span>
          </span>
        )}
      </Link>
      <button
        ref={triggerRef}
        type="button"
        aria-label={`Options for ${item.title}`}
        aria-haspopup="menu"
        aria-expanded={menuOpen}
        onClick={() => setMenuOpen((open) => !open)}
        className={`absolute right-1 top-1/2 inline-flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded bg-subtle text-ink-muted transition-opacity before:pointer-events-none before:absolute before:right-full before:top-0 before:h-full before:w-6 before:bg-gradient-to-l before:from-subtle before:to-transparent hover:bg-line hover:text-ink focus-visible:opacity-100 [@media(hover:none)]:bg-transparent [@media(hover:none)]:before:hidden ${
          menuOpen || active ? 'opacity-100' : 'opacity-0 group-hover/item:opacity-100 group-focus-within/item:opacity-100 [@media(hover:none)]:opacity-70'
        }`}
      >
        <MoreHorizontal className="h-4 w-4" />
      </button>

      {menuOpen &&
        menuPosition &&
        createPortal(
          <div
            ref={menuRef}
            role="menu"
            aria-label={`Options for ${item.title}`}
            style={{ top: menuPosition.top, left: menuPosition.left, width: 168 }}
            className="menu-enter fixed z-[70] overflow-hidden rounded-lg border border-line bg-panel py-1 shadow-lg"
          >
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                setMenuOpen(false);
                setEditing(true);
              }}
              className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-[13px] text-ink-soft outline-none hover:bg-subtle hover:text-ink focus:bg-subtle focus:text-ink"
            >
              <Pencil className="h-3.5 w-3.5" /> Rename
            </button>
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                setMenuOpen(false);
                onDelete();
              }}
              className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-[13px] text-danger outline-none hover:bg-danger-soft focus:bg-danger-soft"
            >
              <Trash2 className="h-3.5 w-3.5" /> Delete
            </button>
          </div>,
          document.body,
        )}
    </li>
  );
};
