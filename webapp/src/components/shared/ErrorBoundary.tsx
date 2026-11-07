import { Component, type ErrorInfo, type ReactNode } from "react";
import { Button } from "../ui/button";

type Props = { children: ReactNode };
type State = { error: Error | null };

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("[ErrorBoundary]", error, info.componentStack);
  }

  render(): ReactNode {
    if (this.state.error) {
      return (
        <div role="alert" className="flex flex-col items-start gap-3 p-6">
          <h2 className="text-lg font-semibold">Something went wrong</h2>
          <pre className="max-w-full overflow-auto rounded-md bg-muted p-3 font-mono text-sm text-muted-foreground">{this.state.error.message}</pre>
          <Button
            type="button"
            onClick={() => this.setState({ error: null })}
          >
            Try again
          </Button>
        </div>
      );
    }
    return this.props.children;
  }
}
