type PagePathLink = {
  label?: string;
  path: string;
};

type PagePathLinksProps = {
  links: PagePathLink[];
  inline?: boolean;
  onOpenPage: (path: string) => void;
};

export function PagePathLinks({ links, inline = false, onOpenPage }: PagePathLinksProps) {
  if (!links.length) return null;
  const className = `page-path-links${inline ? " inline-links" : ""}`;
  return (
    <span className={className}>
      {links.map((link) => (
        <button key={link.path} type="button" onClick={() => onOpenPage(link.path)}>
          {link.label || link.path}
        </button>
      ))}
    </span>
  );
}
