import { useState, useEffect, useCallback, useRef } from "react";
import api from "../../services/api";

interface GooglePhotosPickerProps {
  projectId: string;
  onClose: () => void;
  onImportComplete: () => void;
}

type PickerState = "checking" | "not_connected" | "creating_session" | "picking" | "importing" | "done" | "error";

export default function GooglePhotosPicker({
  projectId,
  onClose,
  onImportComplete,
}: GooglePhotosPickerProps) {
  const [state, setState] = useState<PickerState>("checking");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [pickerUri, setPickerUri] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [importProgress, setImportProgress] = useState<string>("");
  const pollingRef = useRef<NodeJS.Timeout | null>(null);
  const popupRef = useRef<Window | null>(null);
  const isImportingRef = useRef(false);

  // Check connection status on mount
  useEffect(() => {
    checkConnectionStatus();
    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
      }
    };
  }, []);

  const checkConnectionStatus = async () => {
    try {
      const response = await api.get("/auth/google/photos/status");
      if (response.data.connected) {
        // Connected - create a picker session
        createPickerSession();
      } else {
        setState("not_connected");
      }
    } catch (err) {
      setState("not_connected");
    }
  };

  const connectGooglePhotos = async () => {
    try {
      const response = await api.get("/auth/google/photos");
      // Open OAuth in a popup
      const width = 600;
      const height = 700;
      const left = window.screenX + (window.outerWidth - width) / 2;
      const top = window.screenY + (window.outerHeight - height) / 2;

      const popup = window.open(
        response.data.auth_url,
        "Google Photos Authorization",
        `width=${width},height=${height},left=${left},top=${top}`
      );

      // Listen for postMessage from popup
      const handleMessage = (event: MessageEvent) => {
        if (event.data?.type === "google_photos_connected") {
          window.removeEventListener("message", handleMessage);
          checkConnectionStatus();
        }
      };
      window.addEventListener("message", handleMessage);

      // Also poll for popup close as fallback
      const pollInterval = setInterval(() => {
        if (popup?.closed) {
          clearInterval(pollInterval);
          window.removeEventListener("message", handleMessage);
          setTimeout(() => checkConnectionStatus(), 500);
        }
      }, 500);
    } catch (err) {
      setError("Failed to initiate Google Photos connection");
      setState("error");
    }
  };

  const createPickerSession = async () => {
    setState("creating_session");
    try {
      const response = await api.post("/google-photos/session");
      setSessionId(response.data.session_id);
      setPickerUri(response.data.picker_uri);
      setState("picking");

      // Open the picker in a popup
      openPickerPopup(response.data.picker_uri, response.data.session_id);
    } catch (err: unknown) {
      const error = err as { response?: { status?: number; data?: { detail?: string } } };
      if (error.response?.status === 401) {
        setState("not_connected");
      } else {
        setError(error.response?.data?.detail || "Failed to create picker session");
        setState("error");
      }
    }
  };

  const openPickerPopup = (uri: string, sessionId: string) => {
    const width = 800;
    const height = 600;
    const left = window.screenX + (window.outerWidth - width) / 2;
    const top = window.screenY + (window.outerHeight - height) / 2;

    popupRef.current = window.open(
      uri,
      "Google Photos Picker",
      `width=${width},height=${height},left=${left},top=${top}`
    );

    // Start polling for session completion
    pollingRef.current = setInterval(() => {
      checkSessionStatus(sessionId);

      // Also check if popup was closed manually
      if (popupRef.current?.closed) {
        // Give it one more check before giving up
        setTimeout(() => {
          checkSessionStatus(sessionId);
        }, 1000);
      }
    }, 2000);
  };

  const checkSessionStatus = async (sid: string) => {
    // Prevent duplicate imports
    if (isImportingRef.current) {
      return;
    }

    try {
      const response = await api.get(`/google-photos/session/${sid}`);
      if (response.data.media_items_set) {
        // User finished picking - import the photos
        // Set flag before clearing interval to prevent race conditions
        isImportingRef.current = true;

        if (pollingRef.current) {
          clearInterval(pollingRef.current);
          pollingRef.current = null;
        }
        if (popupRef.current && !popupRef.current.closed) {
          popupRef.current.close();
        }
        importPhotos(sid);
      }
    } catch (err) {
      console.error("Failed to check session status:", err);
    }
  };

  const importPhotos = async (sid: string) => {
    setState("importing");
    setImportProgress("Downloading photos from Google Photos...");

    try {
      const response = await api.post(`/projects/${projectId}/import-google-photos`, {
        session_id: sid,
      });

      const { imported_count, errors } = response.data;

      if (errors && errors.length > 0) {
        console.warn("Some photos failed to import:", errors);
      }

      setImportProgress(`Successfully imported ${imported_count} photo${imported_count !== 1 ? "s" : ""}!`);
      setState("done");

      // Auto-close after a short delay
      setTimeout(() => {
        onImportComplete();
        onClose();
      }, 1500);
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } };
      setError(error.response?.data?.detail || "Failed to import photos");
      setState("error");
    }
  };

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape" && state !== "importing") {
        onClose();
      }
    },
    [onClose, state]
  );

  useEffect(() => {
    document.addEventListener("keydown", handleKeyDown);
    document.body.style.overflow = "hidden";

    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = "unset";
    };
  }, [handleKeyDown]);

  const handleRetry = () => {
    setError(null);
    checkConnectionStatus();
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"
      onClick={state !== "importing" ? onClose : undefined}
    >
      <div
        className="bg-white dark:bg-gray-800 rounded-xl shadow-xl w-full max-w-md p-6 flex flex-col items-center"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center gap-3 mb-6">
          <svg
            className="w-8 h-8"
            viewBox="0 0 24 24"
            fill="none"
          >
            <circle cx="12" cy="12" r="10" stroke="#EA4335" strokeWidth="2" />
            <path d="M8 12h8" stroke="#34A853" strokeWidth="2" strokeLinecap="round" />
            <path d="M12 8v8" stroke="#FBBC05" strokeWidth="2" strokeLinecap="round" />
          </svg>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100">Import from Google Photos</h2>
        </div>

        {/* States */}
        {state === "checking" && (
          <div className="flex flex-col items-center py-8">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600 mb-4"></div>
            <p className="text-gray-600 dark:text-gray-400">Checking connection...</p>
          </div>
        )}

        {state === "not_connected" && (
          <div className="flex flex-col items-center py-4">
            <svg
              className="w-16 h-16 text-gray-300 dark:text-gray-600 mb-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
              />
            </svg>
            <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-2">
              Connect Google Photos
            </h3>
            <p className="text-gray-500 dark:text-gray-400 text-center mb-6 max-w-sm">
              Allow access to select photos from your Google Photos library.
            </p>
            <button
              onClick={connectGooglePhotos}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
            >
              <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
                <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
                <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
                <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
              </svg>
              Connect Google Photos
            </button>
          </div>
        )}

        {state === "creating_session" && (
          <div className="flex flex-col items-center py-8">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600 mb-4"></div>
            <p className="text-gray-600 dark:text-gray-400">Opening photo picker...</p>
          </div>
        )}

        {state === "picking" && (
          <div className="flex flex-col items-center py-4">
            <svg
              className="w-16 h-16 text-blue-500 mb-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
              />
            </svg>
            <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-2">
              Select Your Photos
            </h3>
            <p className="text-gray-500 dark:text-gray-400 text-center mb-6 max-w-sm">
              A Google Photos picker window has opened. Select the photos you want to import and click "Done".
            </p>
            <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
              <div className="animate-pulse w-2 h-2 bg-blue-500 rounded-full"></div>
              Waiting for selection...
            </div>
            {pickerUri && (
              <button
                onClick={() => openPickerPopup(pickerUri, sessionId!)}
                className="mt-4 text-sm text-blue-600 hover:text-blue-700"
              >
                Picker didn't open? Click here
              </button>
            )}
          </div>
        )}

        {state === "importing" && (
          <div className="flex flex-col items-center py-8">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600 mb-4"></div>
            <p className="text-gray-600 dark:text-gray-400">{importProgress}</p>
          </div>
        )}

        {state === "done" && (
          <div className="flex flex-col items-center py-8">
            <svg
              className="w-16 h-16 text-green-500 mb-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M5 13l4 4L19 7"
              />
            </svg>
            <p className="text-gray-600 dark:text-gray-400">{importProgress}</p>
          </div>
        )}

        {state === "error" && (
          <div className="flex flex-col items-center py-4">
            <svg
              className="w-16 h-16 text-red-500 mb-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
              />
            </svg>
            <p className="text-red-600 dark:text-red-400 text-center mb-4">{error}</p>
            <div className="flex gap-3">
              <button
                onClick={handleRetry}
                className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700"
              >
                Try Again
              </button>
              <button
                onClick={onClose}
                className="px-4 py-2 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100"
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {/* Close button for non-importing states */}
        {state !== "importing" && state !== "done" && (
          <button
            onClick={onClose}
            className="absolute top-4 right-4 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        )}
      </div>
    </div>
  );
}
