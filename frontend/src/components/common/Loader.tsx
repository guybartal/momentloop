interface LoaderProps {
  size?: "sm" | "md" | "lg";
  className?: string;
}

export default function Loader({ size = "md", className = "" }: LoaderProps) {
  const sizeClasses = {
    sm: "h-4 w-4 border-2",
    md: "h-8 w-8 border-2",
    lg: "h-12 w-12 border-b-2",
  };

  return (
    <div
      className={`animate-spin rounded-full border-primary-600 ${sizeClasses[size]} ${className}`}
      style={{ borderTopColor: "transparent" }}
    />
  );
}
