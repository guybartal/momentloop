import { useState, useEffect } from "react";

interface GeneratingTimerProps {
  label?: string;
  className?: string;
}

export default function GeneratingTimer({
  label = "Generating",
  className = "",
}: GeneratingTimerProps) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const startTime = Date.now();
    const interval = setInterval(() => {
      setElapsed((Date.now() - startTime) / 1000);
    }, 100);

    return () => clearInterval(interval);
  }, []);

  return (
    <span className={className}>
      {label}... ({elapsed.toFixed(1)}s)
    </span>
  );
}
