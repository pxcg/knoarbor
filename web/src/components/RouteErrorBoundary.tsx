import { Component, type ErrorInfo, type ReactNode } from "react";

type Props = {
  children: ReactNode;
  fallbackTitle: string;
  fallbackCopy: string;
  reloadLabel: string;
};

type State = {
  error: Error | null;
};

export class RouteErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Route render failed", error, info);
  }

  componentDidUpdate(previousProps: Props) {
    if (previousProps.children !== this.props.children && this.state.error) {
      this.setState({ error: null });
    }
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <section className="panel route-error-panel">
        <h2>{this.props.fallbackTitle}</h2>
        <p className="panel-copy">{this.props.fallbackCopy}</p>
        <button className="button primary" type="button" onClick={() => window.location.reload()}>
          {this.props.reloadLabel}
        </button>
      </section>
    );
  }
}
