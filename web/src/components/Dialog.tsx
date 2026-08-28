import * as RadixDialog from "@radix-ui/react-dialog";
import { usePrefersReducedMotion } from "../hooks/usePrefersReducedMotion";

const MOTION_OVERLAY =
  "data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0";
const MOTION_PANEL =
  "data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95";

export const Dialog = RadixDialog;

export function useDialogMotionClasses(): {
  overlay: string;
  panel: string;
  reduced: boolean;
} {
  const reduced = usePrefersReducedMotion();
  return {
    overlay: reduced ? "" : MOTION_OVERLAY,
    panel: reduced ? "" : MOTION_PANEL,
    reduced,
  };
}

export function DialogOverlay({
  className = "",
  ...props
}: RadixDialog.DialogOverlayProps) {
  const { overlay } = useDialogMotionClasses();
  return (
    <RadixDialog.Overlay
      className={`fixed inset-0 bg-black/60 backdrop-blur-sm ${overlay} ${className}`.trim()}
      {...props}
    />
  );
}

export function DialogContent({
  className = "",
  ...props
}: RadixDialog.DialogContentProps) {
  const { panel } = useDialogMotionClasses();
  return (
    <RadixDialog.Content
      className={`focus:outline-none ${panel} ${className}`.trim()}
      {...props}
    />
  );
}
