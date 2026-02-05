const EXPORT_STEPS = [
  { id: "collecting_videos", label: "Collecting Videos" },
  { id: "extracting_frames", label: "Extracting Frames" },
  { id: "generating_transitions", label: "Generating Transitions" },
  { id: "concatenating", label: "Joining Videos" },
  { id: "generating_thumbnail", label: "Creating Preview" },
];

interface ExportProgressStepperProps {
  currentStep: string | null;
  detail: string | null;
  percent: number;
}

// Inline SVG icons
function CheckCircleIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  );
}

function CircleIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <circle cx="12" cy="12" r="9" strokeWidth={2} />
    </svg>
  );
}

function LoaderIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
    </svg>
  );
}

export default function ExportProgressStepper({
  currentStep,
  detail,
  percent,
}: ExportProgressStepperProps) {
  const getStepStatus = (stepId: string) => {
    if (!currentStep) return "pending";
    const currentIndex = EXPORT_STEPS.findIndex((s) => s.id === currentStep);
    const stepIndex = EXPORT_STEPS.findIndex((s) => s.id === stepId);

    if (stepIndex < currentIndex) return "completed";
    if (stepIndex === currentIndex) return "in_progress";
    return "pending";
  };

  return (
    <div className="space-y-4">
      {/* Progress bar */}
      <div className="w-full bg-gray-200 dark:bg-gray-600 rounded-full h-2.5">
        <div
          className="bg-primary-600 h-2.5 rounded-full transition-all duration-500"
          style={{ width: `${percent}%` }}
        />
      </div>
      <div className="text-sm text-gray-500 dark:text-gray-400 text-center">{percent}% complete</div>

      {/* Steps */}
      <div className="space-y-3">
        {EXPORT_STEPS.map((step) => {
          const status = getStepStatus(step.id);
          return (
            <div
              key={step.id}
              className={`flex items-center gap-3 ${
                status === "pending" ? "text-gray-400 dark:text-gray-500" : "text-gray-900 dark:text-gray-100"
              }`}
            >
              {status === "completed" ? (
                <CheckCircleIcon className="w-5 h-5 text-green-500" />
              ) : status === "in_progress" ? (
                <LoaderIcon className="w-5 h-5 text-primary-600 animate-spin" />
              ) : (
                <CircleIcon className="w-5 h-5 text-gray-300 dark:text-gray-600" />
              )}
              <span className={status === "in_progress" ? "font-medium" : ""}>
                {step.label}
              </span>
              {step.id === currentStep && detail && (
                <span className="text-sm text-gray-500 dark:text-gray-400 ml-auto">{detail}</span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
