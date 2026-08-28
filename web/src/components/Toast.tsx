interface ToastProps {
  message: string;
  visible: boolean;
}

/** Brief, polite status toast for copy/save confirmations (visible + screen-reader). */
export function Toast({ message, visible }: ToastProps) {
  if (!visible) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      aria-atomic="true"
      className="fixed bottom-24 left-1/2 z-50 -translate-x-1/2 rounded-lg border border-cyan-500/40 bg-black/85 px-4 py-2 text-sm font-medium text-cyan-200 shadow-lg"
      data-testid="toast"
    >
      {message}
    </div>
  );
}
