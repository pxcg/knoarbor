import ClaudeCodeLogo from "@lobehub/icons-static-svg/icons/claudecode.svg?url";
import CodexLogo from "@lobehub/icons-static-svg/icons/codex.svg?url";
import HermesLogo from "@lobehub/icons-static-svg/icons/hermesagent.svg?url";
import OpenClawLogo from "@lobehub/icons-static-svg/icons/openclaw-color.svg?url";

export type BrandIconName = "markdown" | "hermes" | "codex" | "openclaw" | "claude_code" | "generic_chat" | "mineru" | "knoarbor";

const THIRD_PARTY_SOURCE_ICONS: Partial<Record<BrandIconName, { src: string; alt: string }>> = {
  claude_code: { src: ClaudeCodeLogo, alt: "Claude Code" },
  codex: { src: CodexLogo, alt: "Codex" },
  hermes: { src: HermesLogo, alt: "Hermes Agent" },
  openclaw: { src: OpenClawLogo, alt: "OpenClaw" },
};

export function BrandIcon({ name, className }: { name: BrandIconName; className?: string }) {
  const thirdPartyIcon = THIRD_PARTY_SOURCE_ICONS[name];
  if (thirdPartyIcon) {
    return (
      <img
        alt={thirdPartyIcon.alt}
        aria-hidden="true"
        className={className}
        draggable={false}
        src={thirdPartyIcon.src}
      />
    );
  }

  switch (name) {
    case "markdown":
      return <MarkdownLogo className={className} />;
    case "mineru":
      return <PreprocessLogo className={className} />;
    case "knoarbor":
      return <KnoArborSourceLogo className={className} />;
    case "generic_chat":
    default:
      return <GenericChatLogo className={className} />;
  }
}

function KnoArborSourceLogo({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path d="M12 3.5c3.4 2.2 5.2 4.7 5.2 7.2 0 2.7-2.1 4.9-5.2 4.9s-5.2-2.2-5.2-4.9c0-2.5 1.8-5 5.2-7.2Z" fill="none" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.8" />
      <path d="M12 10v10M8.5 14.2 12 17l3.5-2.8" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" />
    </svg>
  );
}

function GenericChatLogo({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path d="M5 6.5A3.5 3.5 0 0 1 8.5 3h7A3.5 3.5 0 0 1 19 6.5v5A3.5 3.5 0 0 1 15.5 15H12l-4.8 4.2V15A3.5 3.5 0 0 1 5 11.5v-5Z" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <path d="M8.5 8h7M8.5 11h4.5" fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" />
    </svg>
  );
}

function PreprocessLogo({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path d="M7 3h7l3 3v5.5A5.5 5.5 0 0 1 11.5 17H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z" fill="none" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.8" />
      <path d="M14 3v4h4M9 9h5M9 12h3" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" />
      <path d="M15.5 15.5 19 19M17 14a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" />
    </svg>
  );
}

function MarkdownLogo({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <rect x="3" y="5" width="18" height="14" rx="2.4" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <path d="M6.5 15V9.5l2.3 2.8 2.3-2.8V15" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" />
      <path d="M14 10.2h2.2v4.6M16.2 14.8l2-2" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" />
    </svg>
  );
}
