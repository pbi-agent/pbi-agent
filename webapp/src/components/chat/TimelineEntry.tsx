import { useState } from "react";
import ReactMarkdown from "react-markdown";
import type { TimelineItem } from "../../types";

export function TimelineEntry({
  item,
  subAgentTitle,
  subAgentStatus,
}: {
  item: TimelineItem;
  subAgentTitle?: string;
  subAgentStatus?: string;
}) {
  const [collapsed, setCollapsed] = useState(true);

  const subAgentBanner =
    subAgentTitle || subAgentStatus ? (
      <div className="timeline-entry__subagent">
        <span className={`indicator-dot indicator-dot--${subAgentStatus === "running" ? "connecting" : "connected"}`} />
        <span>{subAgentTitle ?? "sub_agent"} &middot; {subAgentStatus ?? "running"}</span>
      </div>
    ) : null;

  if (item.kind === "message") {
    const roleClass =
      item.role === "user" ? "user"
      : item.role === "error" ? "error"
      : item.role === "notice" ? "notice"
      : item.role === "debug" ? "debug"
      : "assistant";

    return (
      <div className={`timeline-entry timeline-entry--${roleClass}`}>
        {subAgentBanner}
        <div className="timeline-entry__content">
          {item.markdown && roleClass !== "user" ? (
            <ReactMarkdown>{item.content}</ReactMarkdown>
          ) : (
            <p>{item.content}</p>
          )}
        </div>
      </div>
    );
  }

  if (item.kind === "thinking") {
    return (
      <div className="timeline-entry timeline-entry--thinking">
        {subAgentBanner}
        <div
          className="timeline-entry__header"
          onClick={() => setCollapsed((prev) => !prev)}
        >
          <span className={`timeline-entry__chevron ${collapsed ? "" : "timeline-entry__chevron--open"}`}>
            &#9654;
          </span>
          <span>{item.title}</span>
        </div>
        {!collapsed ? (
          <div className="timeline-entry__body">
            <ReactMarkdown>{item.content}</ReactMarkdown>
          </div>
        ) : null}
      </div>
    );
  }

  // tool_group
  return (
    <div className="timeline-entry timeline-entry--tool">
      {subAgentBanner}
      <div
        className="timeline-entry__header"
        onClick={() => setCollapsed((prev) => !prev)}
      >
        <span className={`timeline-entry__chevron ${collapsed ? "" : "timeline-entry__chevron--open"}`}>
          &#9654;
        </span>
        <span>{item.label}</span>
        <span className="timeline-entry__count">{item.items.length}</span>
      </div>
      {!collapsed ? (
        <div className="timeline-entry__body">
          {item.items.map((toolItem, index) => (
            <pre key={`${item.itemId}-${index}`} className="timeline-entry__tool-item">
              {toolItem.text}
            </pre>
          ))}
        </div>
      ) : null}
    </div>
  );
}
