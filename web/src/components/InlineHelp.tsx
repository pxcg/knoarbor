import { useRef, useState } from "react";
import { createPortal } from "react-dom";

type InlineHelpProps = {
  text: string;
  label?: string;
};

export function InlineHelp({ text, label }: InlineHelpProps) {
  const ref = useRef<HTMLSpanElement | null>(null);
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState<{ left: number; top: number } | null>(null);

  if (!text) return null;

  function showTooltip() {
    const rect = ref.current?.getBoundingClientRect();
    if (!rect) return;
    const top = Math.min(window.innerHeight - 18, Math.max(12, rect.bottom + 10));
    const left = Math.min(window.innerWidth - 18, Math.max(18, rect.left + rect.width / 2));
    setPosition({ left, top });
    setOpen(true);
  }

  return (
    <>
      <span
        className="inline-help"
        ref={ref}
        aria-label={label || text}
        role="img"
        tabIndex={0}
        onBlur={() => setOpen(false)}
        onFocus={showTooltip}
        onMouseEnter={showTooltip}
        onMouseLeave={() => setOpen(false)}
      >
        ?
      </span>
      {open && position
        ? createPortal(
            <span className="inline-help-tooltip" style={{ left: position.left, top: position.top }}>
              {text}
            </span>,
            document.body,
          )
        : null}
    </>
  );
}
