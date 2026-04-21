import { useCallback } from "react";
import { useSession } from "@/store/useSession";

interface ToastOpts {
  description?: string;
  timeout?: number;
}

/**
 * Ergonomic helper: `const toast = useToast(); toast.success("Saved");`.
 * Thin wrapper over `useSession.pushToast`.
 */
export function useToast() {
  const push = useSession((s) => s.pushToast);

  return {
    success: useCallback(
      (title: string, opts?: ToastOpts) =>
        push({ severity: "success", title, ...opts }),
      [push]
    ),
    info: useCallback(
      (title: string, opts?: ToastOpts) =>
        push({ severity: "info", title, ...opts }),
      [push]
    ),
    warning: useCallback(
      (title: string, opts?: ToastOpts) =>
        push({ severity: "warning", title, ...opts }),
      [push]
    ),
    error: useCallback(
      (title: string, opts?: ToastOpts) =>
        push({ severity: "error", title, timeout: 0, ...opts }),
      [push]
    ),
  };
}
