export type ReplySnippet = {
  id: string;
  quote: string;
  comment: string;
};

export type ParsedReplyMessage = {
  snippets: Array<{ quote: string; comment: string }>;
  text: string;
};

const SNIPPET_PATTERN =
  /<reply_snippet(?:\s+index="\d+")?>\s*<quoted_text>\n?([\s\S]*?)\n?<\/quoted_text>\s*<user_comment>\n?([\s\S]*?)\n?<\/user_comment>\s*<\/reply_snippet>/g;

function escapeXmlText(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function unescapeXmlText(value: string): string {
  return value.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");
}

/**
 * Serialize reply snippets ahead of the free-form message so the model can
 * tell which part of its previous answer each comment refers to.
 */
export function serializeReplyMessage(
  snippets: ReadonlyArray<Pick<ReplySnippet, "quote" | "comment">>,
  text: string,
): string {
  const trimmedText = text.trim();
  if (snippets.length === 0) return trimmedText;
  const blocks = snippets.map(
    (snippet, index) =>
      `<reply_snippet index="${index + 1}">\n<quoted_text>\n${escapeXmlText(snippet.quote.trim())}\n</quoted_text>\n<user_comment>\n${escapeXmlText(snippet.comment.trim())}\n</user_comment>\n</reply_snippet>`,
  );
  return trimmedText ? `${blocks.join("\n")}\n\n${trimmedText}` : blocks.join("\n");
}

export function parseReplyMessage(content: string): ParsedReplyMessage {
  const snippets: ParsedReplyMessage["snippets"] = [];
  if (!content.includes("<reply_snippet")) return { snippets, text: content };
  const text = content.replace(SNIPPET_PATTERN, (_match, quote: string, comment: string) => {
    snippets.push({ quote: unescapeXmlText(quote), comment: unescapeXmlText(comment) });
    return "";
  });
  return snippets.length > 0 ? { snippets, text: text.trim() } : { snippets, text: content };
}
