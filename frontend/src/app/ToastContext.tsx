import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from 'react';
import { Check, AlertCircle, Info, AlertTriangle, X } from 'lucide-react';

export type ToastType = 'success' | 'error' | 'info' | 'warning';

export interface ToastMessage {
  id: string;
  type: ToastType;
  title: string;
  description?: string;
}

interface ToastContextValue {
  addToast: (toast: Omit<ToastMessage, 'id'>) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

let toastIdCounter = 0;

export const ToastProvider: React.FC<React.PropsWithChildren> = ({
  children,
}) => {
  const [toasts, setToasts] = useState<ToastMessage[]>([]);
  const timers = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  const remove = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
    const timer = timers.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timers.current.delete(id);
    }
  }, []);

  const addToast = useCallback(
    (toast: Omit<ToastMessage, 'id'>) => {
      const id = `toast-${++toastIdCounter}`;
      setToasts((prev) => [...prev.slice(-4), { ...toast, id }]);
      const duration = toast.type === 'error' ? 6000 : 4000;
      timers.current.set(id, setTimeout(() => remove(id), duration));
    },
    [remove]
  );

  // Clean up timers on unmount
  useEffect(() => {
    const activeTimers = timers.current;
    return () => {
      activeTimers.forEach(clearTimeout);
    };
  }, []);

  return (
    <ToastContext.Provider value={{ addToast }}>
      {children}
      <ToastContainer toasts={toasts} onDismiss={remove} />
    </ToastContext.Provider>
  );
};

export const useToast = (): ToastContextValue => {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('ToastProvider is missing from the tree');
  return ctx;
};


const ICONS: Record<ToastType, React.ReactNode> = {
  success: <Check className="w-4 h-4 text-accent" />,
  error: <AlertCircle className="w-4 h-4 text-danger" />,
  info: <Info className="w-4 h-4 text-info" />,
  warning: <AlertTriangle className="w-4 h-4 text-warning" />,
};

const BG: Record<ToastType, string> = {
  success: 'bg-panel border-accent-line',
  error: 'bg-panel border-danger-line',
  info: 'bg-panel border-info-line',
  warning: 'bg-panel border-warning-line',
};

const TITLE_COLOR: Record<ToastType, string> = {
  success: 'text-accent',
  error: 'text-danger',
  info: 'text-info',
  warning: 'text-warning',
};

interface ToastContainerProps {
  toasts: ToastMessage[];
  onDismiss: (id: string) => void;
}

const ToastContainer: React.FC<ToastContainerProps> = ({
  toasts,
  onDismiss,
}) => {
  if (toasts.length === 0) return null;
  return (
    <div
      role="region"
      aria-label="Notifications"
      aria-live="polite"
      className="fixed bottom-4 right-4 z-[9999] flex flex-col gap-2 max-w-sm w-full"
    >
      {toasts.map((toast) => (
        <div
          key={toast.id}
          role="alert"
          className={`flex items-start gap-3 px-4 py-3 rounded-xl border shadow-lg ${BG[toast.type]} animate-in slide-in-from-right-4 duration-200`}
        >
          <span className="mt-0.5 shrink-0">{ICONS[toast.type]}</span>
          <div className="flex-1 min-w-0">
            <p
              className={`text-sm font-semibold leading-snug ${TITLE_COLOR[toast.type]}`}
            >
              {toast.title}
            </p>
            {toast.description && (
              <p className="text-xs text-ink-soft mt-0.5 leading-relaxed">
                {toast.description}
              </p>
            )}
          </div>
          <button
            type="button"
            aria-label="Dismiss notification"
            onClick={() => onDismiss(toast.id)}
            className="shrink-0 mt-0.5 text-ink-muted hover:text-ink transition-colors"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      ))}
    </div>
  );
};
