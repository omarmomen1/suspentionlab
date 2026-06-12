import { useEffect, useState, useRef } from "react";

const WS_BASE = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace("http", "ws");

export function useCollaboration(
  sessionId: string | null,
  params: any,
  setParams: (p: any) => void
) {
  const [isConnected, setIsConnected] = useState(false);
  const [activeUsers, setActiveUsers] = useState(0);
  const ws = useRef<WebSocket | null>(null);
  
  // Track if a parameter update came from the network so we don't echo it back
  const isNetworkUpdate = useRef(false);

  useEffect(() => {
    if (!sessionId) return;

    // Connect to WebSocket
    const socket = new WebSocket(`${WS_BASE}/sessions/${sessionId}/ws`);
    ws.current = socket;

    socket.onopen = () => {
      setIsConnected(true);
    };

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "state_update") {
          isNetworkUpdate.current = true;
          setParams((prev: any) => ({ ...prev, ...data.state }));
        } else if (data.type === "user_joined" || data.type === "user_left") {
          setActiveUsers(data.active_users || 1);
        }
      } catch (e) {
        console.error("Failed to parse WS message", e);
      }
    };

    socket.onclose = () => {
      setIsConnected(false);
    };

    return () => {
      socket.close();
    };
  }, [sessionId, setParams]);

  // Broadcast local changes
  useEffect(() => {
    if (!sessionId || !isConnected || !ws.current) return;
    
    if (isNetworkUpdate.current) {
      isNetworkUpdate.current = false;
      return; // Skip echoing
    }

    const payload = JSON.stringify({
      type: "state_update",
      state: params
    });
    
    // Debounce the WebSocket send to prevent flooding the server
    const timeoutId = setTimeout(() => {
      if (ws.current?.readyState === WebSocket.OPEN) {
        ws.current.send(payload);
      }
    }, 300);
    
    return () => clearTimeout(timeoutId);
  }, [params, sessionId, isConnected]);

  return { isConnected, activeUsers };
}
