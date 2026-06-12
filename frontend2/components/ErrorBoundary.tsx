"use client";

import React, { Component, ErrorInfo, ReactNode } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";

interface Props {
  children?: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("Uncaught error:", error, errorInfo);
  }

  public render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }
      
      return (
        <div className="flex flex-col items-center justify-center p-8 bg-zinc-900 border border-red-900/30 rounded-xl shadow-2xl backdrop-blur-md">
          <div className="w-16 h-16 bg-red-500/10 rounded-full flex items-center justify-center mb-4 border border-red-500/20">
            <AlertTriangle className="w-8 h-8 text-red-500" />
          </div>
          <h2 className="text-xl font-semibold text-white mb-2 tracking-tight">Simulation Engine Fault</h2>
          <p className="text-zinc-400 text-center mb-6 max-w-md">
            An unexpected error occurred during rendering. This has been logged for our engineers.
          </p>
          <button
            className="flex items-center gap-2 px-6 py-3 bg-white text-black font-medium rounded-lg hover:bg-zinc-200 transition-colors"
            onClick={() => this.setState({ hasError: false, error: null })}
          >
            <RefreshCw className="w-4 h-4" />
            Reload Component
          </button>
          
          {process.env.NODE_ENV === 'development' && this.state.error && (
            <div className="mt-8 w-full">
              <div className="p-4 bg-black/50 rounded text-red-400 font-mono text-xs overflow-auto max-h-48 border border-red-900/50">
                {this.state.error.toString()}
              </div>
            </div>
          )}
        </div>
      );
    }

    return this.props.children;
  }
}
