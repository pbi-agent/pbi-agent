import { useRef } from "react";
import { SearchIcon, XIcon } from "lucide-react";
import { cn } from "../../lib/utils";
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupInput,
} from "../ui/input-group";

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
    <InputGroup className={cn("w-full", className)}>
      <InputGroupAddon align="inline-start">
        <SearchIcon aria-hidden="true" />
      </InputGroupAddon>
      <InputGroupInput
        ref={inputRef}
        type="search"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        aria-label={ariaLabel}
      />
      {value ? (
        <InputGroupAddon align="inline-end">
          <InputGroupButton
            type="button"
            size="icon-xs"
            aria-label={clearLabel}
            onClick={clearSearch}
          >
            <XIcon aria-hidden="true" />
          </InputGroupButton>
        </InputGroupAddon>
      ) : null}
    </InputGroup>
  );
}
