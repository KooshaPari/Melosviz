import { Component, type ErrorInfo, type ReactNode } from "react";
import { t } from "../i18n";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/** Branded error boundary with retry — C10 L101. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("MelosViz UI error", error, info);
  }

  private retry = (): void => {
    this.setState({ error: null });
  };

  render(): ReactNode {
    if (!this.state.error) return this.props.children;
    return (
      <div
        role="alert"
        className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-4 p-8"
        style={{ background: "var(--mv-bg)", color: "var(--mv-primary)" }}
      >
        <h1 className="text-2xl font-bold">{t("app.name")}</h1>
        <p style={{ color: "rgba(255,255,255,0.7)" }}>{t("error.generic")}</p>
        <pre
          className="max-w-lg overflow-auto rounded p-3 text-xs"
          style={{ background: "var(--mv-surface)", color: "#f87171" }}
        >
          {this.state.error.message}
        </pre>
        <button
          type="button"
          onClick={this.retry}
          className="rounded px-4 py-2 font-semibold text-white"
          style={{ background: "var(--mv-primary)" }}
        >
          {t("error.retry")}
        </button>
      </div>
    );
  }
}
