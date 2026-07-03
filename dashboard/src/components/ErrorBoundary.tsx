import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";
import { AlertCircle, RefreshCw } from "lucide-react";

interface Props {
  children: ReactNode;
  /** Optional label shown in the error card header */
  label?: string;
}

interface State {
  error: Error | null;
}

/**
 * Catches any JS errors thrown inside child components and renders a
 * recovery card instead of letting the whole app go black.
 */
export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[ErrorBoundary]", error, info.componentStack);
  }

  reset = () => this.setState({ error: null });

  render() {
    if (this.state.error) {
      return (
        <div className="flex flex-col items-center justify-center h-full gap-4 p-8 text-center">
          <div className="w-12 h-12 rounded-full bg-red-950 flex items-center justify-center">
            <AlertCircle size={24} className="text-red-400" />
          </div>
          <div>
            <p className="text-sm font-medium text-white mb-1">
              {this.props.label ?? "Something went wrong"}
            </p>
            <p className="text-xs text-gray-500 font-mono max-w-sm break-all">
              {this.state.error.message}
            </p>
          </div>
          <button
            onClick={this.reset}
            className="flex items-center gap-1.5 text-xs bg-gray-800 hover:bg-gray-700 text-gray-300 px-3 py-1.5 rounded-md transition-colors"
          >
            <RefreshCw size={12} />
            Try again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
