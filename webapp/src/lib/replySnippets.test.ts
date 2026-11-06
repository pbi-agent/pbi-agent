import { describe, expect, it } from "vitest";
import { parseReplyMessage, serializeReplyMessage } from "./replySnippets";

describe("reply snippets", () => {
  it("serializes snippets before text and round-trips", () => {
    const value = serializeReplyMessage(
      [
        { quote: "use <div> & span", comment: "why?" },
        { quote: "second", comment: "ok" },
      ],
      "  general note ",
    );
    expect(value).toContain('<reply_snippet index="1">');
    expect(value).toContain("use &lt;div&gt; &amp; span");
    expect(value.endsWith("\n\ngeneral note")).toBe(true);
    expect(parseReplyMessage(value)).toEqual({
      snippets: [
        { quote: "use <div> & span", comment: "why?" },
        { quote: "second", comment: "ok" },
      ],
      text: "general note",
    });
  });

  it("leaves plain messages untouched", () => {
    expect(parseReplyMessage("hello")).toEqual({ snippets: [], text: "hello" });
    expect(serializeReplyMessage([], " hi ")).toBe("hi");
  });
});
