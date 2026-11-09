import { Component, type ReactNode } from 'react';

/** Shows the error instead of a white page when something throws while rendering. */
export default class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    return (
      <div style={{ padding: 32, fontFamily: 'Inter, system-ui, sans-serif' }}>
        <h1 style={{ fontSize: 20 }}>Something broke</h1>
        <pre style={{ whiteSpace: 'pre-wrap', background: '#14161b', color: '#ffb4aa', padding: 16, borderRadius: 8 }}>
          {error.message}
          {'\n\n'}
          {error.stack}
        </pre>
        <a href="/">Back to start</a>
      </div>
    );
  }
}
