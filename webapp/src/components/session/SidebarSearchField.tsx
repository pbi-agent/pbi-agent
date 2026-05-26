import { SearchIcon } from "lucide-react";
import { cn } from "../../lib/utils";
import { Input } from "../ui/input";

export function SidebarSearchField({
  value,
  onChange,
  placeholder,
  ariaLabel,
  className,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  ariaLabel: string;
  className?: string;
}) {
  return (
    <div className={cn("session-sidebar__search", className)}>
      <SearchIcon className="session-sidebar__search-icon" aria-hidden="true" />
      <Input
        type="search"
        className="session-sidebar__search-input"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        aria-label={ariaLabel}
      />
    </div>
  );
}
