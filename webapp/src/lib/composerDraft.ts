// Unsent composer text, kept outside React so it survives the composer being
// unmounted (route changes between the new-session page, a session, and a
// sub-agent view). In-memory only: a page reload starts with an empty draft.
let draftText = "";

export function getComposerDraft(): string {
  return draftText;
}

export function setComposerDraft(text: string): void {
  draftText = text;
}

export function resetComposerDraft(): void {
  draftText = "";
}
