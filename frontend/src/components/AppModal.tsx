import type { ReactNode } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";

type AppModalProps = {
  title: string;
  description?: string;
  tag?: ReactNode;
  headerIcon?: ReactNode;
  leadingAction?: ReactNode;
  className?: string;
  showCloseButton?: boolean;
  children: ReactNode;
  onClose: () => void;
};

export function AppModal({
  title,
  description,
  tag,
  headerIcon,
  leadingAction,
  className,
  showCloseButton = true,
  children,
  onClose,
}: AppModalProps) {
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent
        className={className}
        showCloseButton={showCloseButton}
        {...(!description && { "aria-describedby": undefined })}
      >
        <DialogHeader
          className={
            leadingAction
              ? "pt-6 text-left"
              : showCloseButton
                ? "pe-8 text-left"
                : "text-left"
          }
        >
          {leadingAction && (
            <div className="absolute start-3 top-3">{leadingAction}</div>
          )}
          {headerIcon}
          <div className="flex flex-wrap items-center gap-2">
            <DialogTitle className="m-0 wrap-anywhere">{title}</DialogTitle>
            {tag}
          </div>
          {description && <DialogDescription>{description}</DialogDescription>}
        </DialogHeader>
        {children}
      </DialogContent>
    </Dialog>
  );
}
