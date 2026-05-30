export const EMPTY_SELECT_VALUE = "__pbi_agent_empty_select_value__";

export function toSelectValue(value: string | null | undefined): string {
  return value ? value : EMPTY_SELECT_VALUE;
}

export function fromSelectValue(value: string): string {
  return value === EMPTY_SELECT_VALUE ? "" : value;
}

export function fromSelectValueNullable(value: string): string | null {
  const selected = fromSelectValue(value);
  return selected || null;
}