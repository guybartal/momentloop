import { useEffect, useRef, useCallback } from "react";

const WS_URL = import.meta.env.VITE_WS_URL || "ws://localhost:8000";

interface WebSocketMessage {
  event: string;
  data: Record<string, unknown>;
}

interface UseProjectWebSocketOptions {
  onPhotoStyled?: (photoId: string, styledUrl: string) => void;
  onVideoReady?: (videoId: string, videoUrl: string) => void;
  onExportComplete?: (exportId: string, fileUrl: string) => void;
}

export function useProjectWebSocket(
  projectId: string | undefined,
  options: UseProjectWebSocketOptions = {}
) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const { onPhotoStyled, onVideoReady, onExportComplete } = options;

  const connect = useCallback(() => {
    if (!projectId) return;

    const ws = new WebSocket(`${WS_URL}/ws/${projectId}`);

    ws.onopen = () => {
      console.log("WebSocket connected for project", projectId);
    };

    ws.onmessage = (event) => {
      try {
        const message: WebSocketMessage = JSON.parse(event.data);

        switch (message.event) {
          case "photo_styled":
            onPhotoStyled?.(
              message.data.photo_id as string,
              message.data.styled_url as string
            );
            break;
          case "video_ready":
            onVideoReady?.(
              message.data.video_id as string,
              message.data.video_url as string
            );
            break;
          case "export_complete":
            onExportComplete?.(
              message.data.export_id as string,
              message.data.file_url as string
            );
            break;
        }
      } catch (e) {
        console.error("Failed to parse WebSocket message:", e);
      }
    };

    ws.onclose = () => {
      console.log("WebSocket disconnected, attempting reconnect...");
      // Attempt to reconnect after 3 seconds
      reconnectTimeoutRef.current = window.setTimeout(() => {
        connect();
      }, 3000);
    };

    ws.onerror = (error) => {
      console.error("WebSocket error:", error);
    };

    wsRef.current = ws;
  }, [projectId, onPhotoStyled, onVideoReady, onExportComplete]);

  useEffect(() => {
    connect();

    // Ping every 30 seconds to keep connection alive
    const pingInterval = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send("ping");
      }
    }, 30000);

    return () => {
      clearInterval(pingInterval);
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [connect]);

  return {
    isConnected: wsRef.current?.readyState === WebSocket.OPEN,
  };
}
