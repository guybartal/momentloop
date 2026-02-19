import { useState, useEffect } from "react";

interface GeneratingTimerProps {
  label?: string;
  className?: string;
  startTime?: number;
}

export default function GeneratingTimer({
  label = "Generating",
  className = "",
  startTime,
}: GeneratingTimerProps) {
  const [baseTime] = useState(() => startTime ?? Date.now());
  const [elapsed, setElapsed] = useState(() =>
    startTime ? (Date.now() - startTime) / 1000 : 0
  );

  useEffect(() => {
    const interval = setInterval(() => {
      setElapsed((Date.now() - baseTime) / 1000);
    }, 100);

    return () => clearInterval(interval);
  }, [baseTime]);

  return (
    <span className={className}>
      {label}... ({elapsed.toFixed(1)}s)
    </span>
  );
}
