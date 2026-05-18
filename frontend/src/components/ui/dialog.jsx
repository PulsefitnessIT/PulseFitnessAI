import * as React from "react"
import * as DialogPrimitive from "@radix-ui/react-dialog"
import { X } from "lucide-react"

import { cn } from "@/lib/utils"

const Dialog = DialogPrimitive.Root

const DialogTrigger = DialogPrimitive.Trigger

const DialogPortal = DialogPrimitive.Portal

const DialogClose = DialogPrimitive.Close

const DialogOverlay = React.forwardRef(({ className, ...props }, ref) => (
  <DialogPrimitive.Overlay
    ref={ref}
    className={cn(
      "fixed inset-0 z-50 bg-black/80  data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0",
      className
    )}
    {...props} />
))
DialogOverlay.displayName = DialogPrimitive.Overlay.displayName

const DialogContent = React.forwardRef(({ className, children, onPointerDownOutside: _onPointerDownOutside, onInteractOutside: _onInteractOutside, onFocusOutside: _onFocusOutside, ...props }, ref) => {
  // Iter 216h205 — Radix Select/Popover inside Dialog fix.
  // When a Select dropdown is open inside a Dialog, clicking on an option
  // fires onPointerDownOutside/onInteractOutside because the Select content
  // is portaled outside the Dialog. We intercept these events and check if
  // the click target is inside a Radix popper/select/popover element.
  const isRadixPopperElement = (target) => {
    if (!target || !target.closest) return false;
    return !!(
      target.closest('[data-radix-popper-content-wrapper]') ||
      target.closest('[data-radix-select-content]') ||
      target.closest('[data-radix-select-viewport]') ||
      target.closest('[data-radix-popover-content]') ||
      target.closest('[role="listbox"]') ||
      target.closest('[role="option"]')
    );
  };

  const handlePointerDownOutside = React.useCallback((e) => {
    const target = e.target;
    console.log('[Dialog] onPointerDownOutside target:', target?.tagName, target?.className?.substring?.(0, 50), target?.getAttribute?.('role'));
    if (isRadixPopperElement(target)) {
      console.log('[Dialog] Preventing dialog close - click was inside Radix popper');
      e.preventDefault();
      return;
    }
    _onPointerDownOutside?.(e);
  }, [_onPointerDownOutside]);

  const handleInteractOutside = React.useCallback((e) => {
    const target = e.target;
    console.log('[Dialog] onInteractOutside target:', target?.tagName, target?.className?.substring?.(0, 50), target?.getAttribute?.('role'));
    if (isRadixPopperElement(target)) {
      console.log('[Dialog] Preventing dialog close - interaction was inside Radix popper');
      e.preventDefault();
      return;
    }
    _onInteractOutside?.(e);
  }, [_onInteractOutside]);

  const handleFocusOutside = React.useCallback((e) => {
    const target = e.target;
    console.log('[Dialog] onFocusOutside target:', target?.tagName, target?.className?.substring?.(0, 50), target?.getAttribute?.('role'));
    if (isRadixPopperElement(target)) {
      console.log('[Dialog] Preventing dialog close - focus was inside Radix popper');
      e.preventDefault();
      return;
    }
    _onFocusOutside?.(e);
  }, [_onFocusOutside]);

  return (
  <DialogPortal>
    <DialogOverlay />
    <DialogPrimitive.Content
      ref={ref}
      onPointerDownOutside={handlePointerDownOutside}
      onInteractOutside={handleInteractOutside}
      onFocusOutside={handleFocusOutside}
      className={cn(
        // Iter 215d6 — mobile: dialog centres inside the safe zone
        // (top-16 to bottom-16) so its close button and any footer
        // actions are never hidden under the fixed navs. Desktop is
        // unchanged and continues to centre at 50%/50%.
        "fixed left-[50%] top-[calc(50%+1rem)] sm:top-[50%] z-50 grid w-full max-w-lg translate-x-[-50%] translate-y-[-50%] gap-4 border bg-background p-6 shadow-xl duration-200 max-h-[calc(100vh-8rem)] sm:max-h-[90vh] overflow-y-auto rounded-2xl data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95",
        className
      )}
      {...props}>
      {/* Iter 215bu — sticky close button. The dialog scrolls internally
          (max-h-[90vh] + overflow-y-auto), so a `sticky top-2` Close stays
          pinned to the top of the viewport as users scroll long forms.
          Negative margins keep it visually anchored to the top-right
          corner of the dialog's padding, matching the previous absolute
          layout. row-start-1 + col-start-1 pulls it visually to the top
          even though it's the last grid child. */}
      <DialogPrimitive.Close
        className="sticky top-0 z-20 row-start-1 col-start-1 justify-self-end -mt-2 -mr-2 mb-[-2rem] h-9 w-9 rounded-full border border-[color:var(--theme-border)] bg-background flex items-center justify-center text-[color:var(--theme-text)] hover:bg-[color:var(--theme-surface-hover)] focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1 transition-colors disabled:pointer-events-none">
        <X className="h-[18px] w-[18px]" />
        <span className="sr-only">Close</span>
      </DialogPrimitive.Close>
      {children}
    </DialogPrimitive.Content>
  </DialogPortal>
);
})
DialogContent.displayName = DialogPrimitive.Content.displayName

const DialogHeader = ({
  className,
  ...props
}) => (
  <div
    className={cn("flex flex-col space-y-1.5 text-center sm:text-left", className)}
    {...props} />
)
DialogHeader.displayName = "DialogHeader"

const DialogFooter = ({
  className,
  ...props
}) => (
  <div
    className={cn("flex flex-col-reverse sm:flex-row sm:justify-end sm:space-x-2", className)}
    {...props} />
)
DialogFooter.displayName = "DialogFooter"

const DialogTitle = React.forwardRef(({ className, ...props }, ref) => (
  <DialogPrimitive.Title
    ref={ref}
    className={cn("text-lg font-semibold leading-none tracking-tight", className)}
    {...props} />
))
DialogTitle.displayName = DialogPrimitive.Title.displayName

const DialogDescription = React.forwardRef(({ className, ...props }, ref) => (
  <DialogPrimitive.Description
    ref={ref}
    className={cn("text-sm text-muted-foreground", className)}
    {...props} />
))
DialogDescription.displayName = DialogPrimitive.Description.displayName

export {
  Dialog,
  DialogPortal,
  DialogOverlay,
  DialogTrigger,
  DialogClose,
  DialogContent,
  DialogHeader,
  DialogFooter,
  DialogTitle,
  DialogDescription,
}
