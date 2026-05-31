import { useEffect, useRef, useState } from "react";

type DelayedTooltipProps = {
  text: string;
  className?: string;
  delayMs?: number;
};

export function DelayedTooltip({ text, className, delayMs = 650 }: DelayedTooltipProps) {
  const labelRef = useRef<HTMLSpanElement | null>(null);
  const timerRef = useRef<number | null>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    return () => clearTimer();
  }, []);

  function clearTimer() {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }

  function showWhenTruncated() {
    clearTimer();
    timerRef.current = window.setTimeout(() => {
      const element = labelRef.current;
      if (element && element.scrollWidth > element.clientWidth + 2) {
        setVisible(true);
      }
    }, delayMs);
  }

  function hide() {
    clearTimer();
    setVisible(false);
  }

  return (
    <span className="delayed-tooltip-wrapper" onBlur={hide} onFocus={showWhenTruncated} onMouseEnter={showWhenTruncated} onMouseLeave={hide}>
      <span ref={labelRef} className={className}>
        {text}
      </span>
      {visible && <span className="delayed-tooltip">{text}</span>}
    </span>
  );
}
