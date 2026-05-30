import { useRef } from "react";
import { SearchIcon, XIcon } from "lucide-react";
import { cn } from "../../lib/utils";
import { Button } from "../ui/button";
import { Input } from "../ui/input";

export function SidebarSearchField({
  value,
  onChange,
  placeholder,
  ariaLabel,
  clearLabel = "Clear search",
  className,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  ariaLabel: string;
  clearLabel?: string;
  className?: string;
}) {
  const inputRef = useRef<HTMLInputElement>(null);

  const clearSearch = () => {
    onChange("");
    inputRef.current?.focus();
  };

  return (
    <div className={cn("session-sidebar__search", className)}>
      <SearchIcon className="session-sidebar__search-icon" aria-hidden="true" />
      <Input
        ref={inputRef}
        type="search"
        className="session-sidebar__search-input"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        aria-label={ariaLabel}
      />
      {value ? (
        <Button
          type="button"
          variant="ghost"
          size="icon-xs"
          className="session-sidebar__search-clear"
          aria-label={clearLabel}
          onClick={clearSearch}
        >
          <XIcon aria-hidden="true" />
        </Button>
      ) : null}
    </div>
  );
}
