import React from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";

export class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error("ErrorBoundary caught an error:", error, errorInfo);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
    if (this.props.onReset) {
      this.props.onReset();
    }
  };

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          padding: "40px",
          margin: "20px",
          background: "rgba(30, 20, 45, 0.4)",
          border: "1px solid var(--border-glass)",
          borderRadius: "var(--radius-lg)",
          backdropFilter: "blur(20px)",
          color: "white",
          textAlign: "center",
          boxShadow: "0 10px 30px rgba(0, 0, 0, 0.3)",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: "20px"
        }}>
          <div style={{
            width: "64px",
            height: "64px",
            background: "rgba(239, 68, 68, 0.15)",
            border: "1px solid rgba(239, 68, 68, 0.3)",
            borderRadius: "50%",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "#ef4444",
            boxShadow: "0 0 20px rgba(239, 68, 68, 0.2)"
          }}>
            <AlertTriangle size={32} />
          </div>
          <h2 style={{ margin: 0, fontSize: "22px", fontWeight: "700" }}>View Crashed</h2>
          <p style={{ color: "var(--text-secondary)", margin: 0, maxWidth: "500px", fontSize: "14px", lineHeight: "1.6" }}>
            An unexpected error occurred while rendering this view.
          </p>
          {this.state.error && (
            <pre style={{
              background: "rgba(0, 0, 0, 0.3)",
              border: "1px solid rgba(255, 255, 255, 0.05)",
              padding: "16px",
              borderRadius: "8px",
              fontSize: "12px",
              fontFamily: "monospace",
              color: "#f87171",
              maxWidth: "100%",
              overflowX: "auto",
              textAlign: "left"
            }}>
              {this.state.error.toString()}
            </pre>
          )}
          <button
            className="btn-primary"
            style={{ display: "flex", alignItems: "center", gap: "8px", width: "160px", justifyContent: "center" }}
            onClick={this.handleReset}
          >
            <RefreshCw size={16} /> Reset View
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
