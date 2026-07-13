import type { ButtonHTMLAttributes } from "react";

export type ButtonVariant = "accent" | "ghost";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
}

const VARIANT_CLASS: Record<ButtonVariant, string> = {
  accent:
    "px-3 py-1.5 rounded bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-300 text-xs font-medium transition-colors border border-cyan-500/30 text-center",
  ghost:
    "px-3 py-1.5 rounded bg-white/5 hover:bg-white/10 text-white/70 text-xs font-medium transition-colors border border-white/10 text-center",
};

/**
 * Shared focusable action control (C10 L105). Native `<button>` keeps
 * keyboard focus + activation semantics for free (C09 focus contracts) —
 * only the visual variant is tokenized here.
 */
export function Button({ variant = "accent", className = "", type = "button", ...props }: ButtonProps) {
  return (
    <button
      type={type}
      className={`${VARIANT_CLASS[variant]}${className ? ` ${className}` : ""}`}
      {...props}
    />
  );
}
