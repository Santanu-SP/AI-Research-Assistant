import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { LucideIcon, MoreHorizontal } from 'lucide-react';

export interface ActionMenuItem {
  label: string;
  icon: LucideIcon;
  onSelect: () => void;
  danger?: boolean;
  /** Draws a divider above this item. */
  separated?: boolean;
}

interface ActionMenuProps {
  /** Accessible name of the "..." button, e.g. "Actions for Plant biology". */
  label: string;
  items: ActionMenuItem[];
  width?: number;
  className?: string;
}

const ITEM_HEIGHT = 36;

/**
 * A "..." button with a small menu. The menu is drawn on top of the page (in a portal),
 * so a list with rounded, clipped corners can't cut it off, and it opens upwards when
 * there is no room below. It closes on an outside click, Escape, scroll or resize.
 */
export const ActionMenu: React.FC<ActionMenuProps> = ({ label, items, width = 196, className = '' }) => {
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState<{ top: number; left: number } | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    if (!open || !triggerRef.current) {
      setPosition(null);
      return;
    }
    const rect = triggerRef.current.getBoundingClientRect();
    const separators = items.filter((item) => item.separated).length;
    const height = items.length * ITEM_HEIGHT + separators * 9 + 8;
    const below = rect.bottom + 4;
    const top = below + height > window.innerHeight - 8 ? Math.max(8, rect.top - height - 4) : below;
    const left = Math.min(Math.max(8, rect.right - width), window.innerWidth - width - 8);
    setPosition({ top, left });
  }, [open, items, width]);

  useEffect(() => {
    if (!open) return;
    const close = (event: Event) => {
      const target = event.target as Node;
      if (menuRef.current?.contains(target) || triggerRef.current?.contains(target)) return;
      setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopPropagation();
        setOpen(false);
        triggerRef.current?.focus();
      }
    };
    const dismiss = () => setOpen(false);
    document.addEventListener('pointerdown', close);
    document.addEventListener('keydown', onKey, true);
    window.addEventListener('resize', dismiss);
    document.addEventListener('scroll', dismiss, true);
    return () => {
      document.removeEventListener('pointerdown', close);
      document.removeEventListener('keydown', onKey, true);
      window.removeEventListener('resize', dismiss);
      document.removeEventListener('scroll', dismiss, true);
    };
  }, [open]);

  useEffect(() => {
    if (open && position) menuRef.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus();
  }, [open, position]);

  const moveFocus = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (!['ArrowDown', 'ArrowUp', 'Home', 'End', 'Tab'].includes(event.key)) return;
    if (event.key === 'Tab') {
      setOpen(false);
      return;
    }
    event.preventDefault();
    const options = Array.from(menuRef.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? []);
    const index = options.indexOf(document.activeElement as HTMLElement);
    const next =
      event.key === 'Home'
        ? 0
        : event.key === 'End'
          ? options.length - 1
          : (index + (event.key === 'ArrowDown' ? 1 : -1) + options.length) % options.length;
    options[next]?.focus();
  };

  return (
    // Clicks inside the menu must not reach a clickable row behind it.
    <div className={`relative ${className}`} onClick={(event) => event.stopPropagation()} onKeyDown={(event) => event.stopPropagation()}>
      <button
        ref={triggerRef}
        type="button"
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className={`flex h-8 w-8 items-center justify-center rounded-md text-ink-muted transition-colors hover:bg-sunken hover:text-ink ${
          open ? 'bg-sunken text-ink' : ''
        }`}
      >
        <MoreHorizontal className="h-4 w-4" />
      </button>

      {open &&
        position &&
        createPortal(
          <div
            ref={menuRef}
            role="menu"
            aria-label={label}
            onKeyDown={moveFocus}
            onClick={(event) => event.stopPropagation()}
            style={{ top: position.top, left: position.left, width }}
            className="menu-enter fixed z-[70] overflow-hidden rounded-lg border border-line bg-panel py-1 shadow-lg"
          >
            {items.map(({ label: itemLabel, icon: Icon, onSelect, danger, separated }) => (
              <React.Fragment key={itemLabel}>
                {separated && <div className="my-1 h-px bg-line" role="separator" />}
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setOpen(false);
                    onSelect();
                  }}
                  className={`flex h-9 w-full items-center gap-2.5 px-3 text-left text-[13px] outline-none ${
                    danger
                      ? 'text-danger hover:bg-danger-soft focus:bg-danger-soft'
                      : 'text-ink hover:bg-subtle focus:bg-subtle'
                  }`}
                >
                  <Icon className={`h-4 w-4 shrink-0 ${danger ? '' : 'text-ink-muted'}`} />
                  {itemLabel}
                </button>
              </React.Fragment>
            ))}
          </div>,
          document.body,
        )}
    </div>
  );
};
