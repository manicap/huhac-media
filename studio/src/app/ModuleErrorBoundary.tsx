import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  readonly moduleTitle: string;
  readonly children: ReactNode;
}

interface State {
  readonly error: Error | null;
}

export class ModuleErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(`Studio module ${this.props.moduleTitle} failed`, error, info);
  }

  private retry = () => this.setState({ error: null });

  render() {
    if (!this.state.error) {
      return this.props.children;
    }
    return (
      <section className="module-state module-state--error" role="alert">
        <p className="eyebrow">Izolovaná chyba modulu</p>
        <h2>Modul {this.props.moduleTitle} selhal</h2>
        <p>Shell a ostatní moduly zůstávají dostupné.</p>
        <button className="button button--primary" type="button" onClick={this.retry}>
          Zkusit znovu
        </button>
      </section>
    );
  }
}
