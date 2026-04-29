import {
  BotIcon,
  CheckCircle2Icon,
  FileImageIcon,
  FileTextIcon,
  GlobeIcon,
  SearchIcon,
  TerminalIcon,
  WrenchIcon,
  XCircleIcon,
} from "lucide-react";
import type { ReactNode } from "react";
import type { ToolCallMetadata } from "../../types";
import { Badge } from "../ui/badge";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "../ui/card";
import { GitDiffResult, isApplyPatchToolMetadata } from "./GitDiffResult";

type ToolResultProps = {
  metadata?: ToolCallMetadata;
  text: string;
  running?: boolean;
};

const FILE_EDIT_TOOLS = new Set(["apply_patch", "write_file", "replace_in_file"]);

export function ToolResult({ metadata, text, running = false }: ToolResultProps) {
  const toolName = toolNameFor(metadata);
  if (metadata && isApplyPatchToolMetadata(metadata) && !running) {
    return <GitDiffResult metadata={metadata} />;
  }

  if (toolName === "shell") {
    return <ShellToolResult metadata={metadata} text={text} running={running} />;
  }
  if (toolName === "read_file") {
    return <ReadFileToolResult metadata={metadata} text={text} running={running} />;
  }
  if (toolName === "read_image") {
    return <ReadImageToolResult metadata={metadata} text={text} running={running} />;
  }
  if (toolName === "read_web_url") {
    return <ReadWebUrlToolResult metadata={metadata} text={text} running={running} />;
  }
  if (toolName === "web_search") {
    return <WebSearchToolResult metadata={metadata} text={text} running={running} />;
  }
  if (toolName === "sub_agent") {
    return <SubAgentToolResult metadata={metadata} text={text} running={running} />;
  }

  return <GenericToolResult metadata={metadata} text={text} running={running} />;
}

export function hasCustomToolResult(metadata: ToolCallMetadata | undefined): boolean {
  const toolName = toolNameFor(metadata);
  return Boolean(toolName || metadata?.result || metadata?.arguments || metadata?.error);
}

function ShellToolResult({ metadata, text, running }: ToolResultProps) {
  const args = objectValue(metadata?.arguments);
  const result = objectValue(metadata?.result);
  const command = stringValue(metadata?.command) ?? stringValue(args?.command) ?? "<missing command>";
  const cwd = stringValue(metadata?.working_directory) ?? stringValue(args?.working_directory) ?? ".";
  const timeout = metadata?.timeout_ms ?? args?.timeout_ms;
  const exitCode = typeof metadata?.exit_code === "number" || metadata?.exit_code === null
    ? metadata.exit_code
    : numberOrNull(result?.exit_code);
  const timedOut = Boolean(metadata?.timed_out ?? result?.timed_out);
  const stdout = stringValue(result?.stdout) ?? "";
  const stderr = stringValue(result?.stderr) ?? "";
  const error = errorText(metadata?.error ?? result?.error);

  return (
    <ToolCard
      metadata={metadata}
      running={running}
      icon={<TerminalIcon />}
      title={command}
      description={[cwd, timeout ? `timeout ${timeout}ms` : null].filter(Boolean).join(" · ")}
      statusLabel={timedOut ? "Timed out" : exitCode === 0 ? "Done" : exitCode === null ? "Running" : `Exit ${exitCode}`}
    >
      {error ? <ToolNotice tone="error" label="Error" value={error} /> : null}
      <OutputBlock label="Stdout" value={stdout} empty="(empty)" truncated={Boolean(result?.stdout_truncated)} />
      <OutputBlock label="Stderr" value={stderr} empty="(empty)" truncated={Boolean(result?.stderr_truncated)} tone="stderr" />
      {!stdout && !stderr && !error && text ? <OutputBlock label="Summary" value={text} /> : null}
    </ToolCard>
  );
}

function ReadFileToolResult({ metadata, text, running }: ToolResultProps) {
  const result = objectValue(metadata?.result);
  const args = objectValue(metadata?.arguments);
  const path = stringValue(result?.path) ?? stringValue(args?.path) ?? "Unknown file";
  const content = stringValue(result?.content);
  const sheets = arrayValue(result?.sheets);
  const schema = stringValue(result?.schema);
  const preview = stringValue(result?.preview) ?? stringValue(result?.markdown);
  const lineRange = lineRangeLabel(result);
  const description = [lineRange, shapeLabel(result), result?.windowed ? "windowed" : null]
    .filter(Boolean)
    .join(" · ");

  return (
    <ToolCard metadata={metadata} running={running} icon={<FileTextIcon />} title={path} description={description || "Read file"}>
      {metadata?.error || result?.error ? <ToolNotice tone="error" label="Error" value={errorText(metadata.error ?? result?.error)} /> : null}
      {content ? <OutputBlock label="Content" value={content} truncated={Boolean(result?.content_truncated)} /> : null}
      {schema ? <OutputBlock label="Schema" value={schema} truncated={Boolean(result?.schema_truncated)} /> : null}
      {preview ? <OutputBlock label="Preview" value={preview} truncated={Boolean(result?.preview_truncated)} /> : null}
      {sheets.length > 0 ? (
        <div className="tool-result__section">
          <span className="tool-result__section-label">Sheets</span>
          <div className="tool-result__list">
            {sheets.slice(0, 6).map((sheet, index) => {
              const sheetRecord = objectValue(sheet);
              return (
                <div key={`${stringValue(sheetRecord?.name) ?? "sheet"}-${index}`} className="tool-result__list-item">
                  <strong>{stringValue(sheetRecord?.name) ?? `Sheet ${index + 1}`}</strong>
                  <span>{shapeLabel(sheetRecord) || "tabular preview"}</span>
                </div>
              );
            })}
          </div>
        </div>
      ) : null}
      {!content && !schema && !preview && sheets.length === 0 && text ? <OutputBlock label="Summary" value={text} /> : null}
    </ToolCard>
  );
}

function ReadImageToolResult({ metadata, text, running }: ToolResultProps) {
  const result = objectValue(metadata?.result);
  const args = objectValue(metadata?.arguments);
  const path = stringValue(result?.path) ?? stringValue(args?.path) ?? "Unknown image";
  const description = [stringValue(result?.mime_type), formatBytes(numberValue(result?.byte_count))]
    .filter(Boolean)
    .join(" · ");

  return (
    <ToolCard metadata={metadata} running={running} icon={<FileImageIcon />} title={path} description={description || "Attached image to model context"}>
      {metadata?.error || result?.error ? <ToolNotice tone="error" label="Error" value={errorText(metadata.error ?? result?.error)} /> : null}
      <div className="tool-result__kv">
        <span>Attachment</span>
        <strong>{metadata?.success === false ? "Failed" : "Ready for model context"}</strong>
      </div>
      {text ? <OutputBlock label="Summary" value={text} /> : null}
    </ToolCard>
  );
}

function ReadWebUrlToolResult({ metadata, text, running }: ToolResultProps) {
  const result = objectValue(metadata?.result);
  const args = objectValue(metadata?.arguments);
  const url = stringValue(result?.url) ?? stringValue(args?.url) ?? "Unknown URL";
  const markdown = stringValue(result?.markdown);
  return (
    <ToolCard metadata={metadata} running={running} icon={<GlobeIcon />} title={url} description="Fetched as Markdown">
      {metadata?.error || result?.error ? <ToolNotice tone="error" label="Error" value={errorText(metadata.error ?? result?.error)} /> : null}
      {markdown ? <OutputBlock label="Markdown" value={markdown} truncated={Boolean(result?.markdown_truncated)} /> : null}
      {!markdown && text ? <OutputBlock label="Summary" value={text} /> : null}
    </ToolCard>
  );
}

function WebSearchToolResult({ metadata, text, running }: ToolResultProps) {
  const result = objectValue(metadata?.result);
  const args = objectValue(metadata?.arguments);
  const sources = arrayValue(result?.sources ?? args?.sources);
  const queries = arrayValue(result?.queries ?? args?.queries).map((query) => String(query));
  return (
    <ToolCard metadata={metadata} running={running} icon={<SearchIcon />} title="Web search" description={queries.join(" · ") || "Search results"}>
      {sources.length > 0 ? (
        <div className="tool-result__list">
          {sources.slice(0, 8).map((source, index) => {
            const record = objectValue(source);
            const title = stringValue(record?.title) ?? stringValue(record?.url) ?? `Source ${index + 1}`;
            const url = stringValue(record?.url);
            return (
              <div key={`${url ?? title}-${index}`} className="tool-result__list-item">
                {url ? <a href={url} target="_blank" rel="noreferrer">{title}</a> : <strong>{title}</strong>}
                {stringValue(record?.snippet) ? <span>{stringValue(record?.snippet)}</span> : null}
              </div>
            );
          })}
        </div>
      ) : text ? <OutputBlock label="Summary" value={text} /> : null}
    </ToolCard>
  );
}

function SubAgentToolResult({ metadata, text, running }: ToolResultProps) {
  const result = objectValue(metadata?.result);
  const args = objectValue(metadata?.arguments);
  const task = stringValue(args?.task_instruction) ?? "Delegated task";
  const agentType = stringValue(args?.agent_type) ?? "default";
  const output = stringValue(result?.output) ?? stringValue(result?.message) ?? stringValue(result?.summary);
  return (
    <ToolCard metadata={metadata} running={running} icon={<BotIcon />} title={task} description={`Agent · ${agentType}`}>
      {metadata?.error || result?.error ? <ToolNotice tone="error" label="Error" value={errorText(metadata.error ?? result?.error)} /> : null}
      {output ? <OutputBlock label="Result" value={output} /> : text ? <OutputBlock label="Summary" value={text} /> : null}
    </ToolCard>
  );
}

function GenericToolResult({ metadata, text, running }: ToolResultProps) {
  const toolName = toolNameFor(metadata) || "tool";
  return (
    <ToolCard metadata={metadata} running={running} icon={<WrenchIcon />} title={toolName} description="Tool call result">
      {metadata?.error ? <ToolNotice tone="error" label="Error" value={errorText(metadata.error)} /> : null}
      {metadata?.arguments ? <OutputBlock label="Arguments" value={formatJson(metadata.arguments)} /> : null}
      {metadata?.result ? <OutputBlock label="Result" value={formatJson(metadata.result)} /> : text ? <OutputBlock label="Summary" value={text} /> : null}
    </ToolCard>
  );
}

function ToolCard({ metadata, running, icon, title, description, statusLabel, children }: {
  metadata?: ToolCallMetadata;
  running?: boolean;
  icon: ReactNode;
  title: string;
  description?: string;
  statusLabel?: string;
  children: ReactNode;
}) {
  const failed = metadata?.success === false || metadata?.status === "failed";
  const label = statusLabel ?? (running ? "Running" : failed ? "Failed" : "Done");
  return (
    <Card size="sm" className="tool-result-card" data-status={failed ? "failed" : running ? "running" : "done"}>
      <CardHeader className="tool-result-card__header">
        <div className="tool-result-card__title-row">
          <span className="tool-result-card__icon" aria-hidden="true">{icon}</span>
          <div className="tool-result-card__title-copy">
            <CardTitle className="tool-result-card__title">{title}</CardTitle>
            {description ? <CardDescription className="tool-result-card__description">{description}</CardDescription> : null}
          </div>
        </div>
        <CardAction className="tool-result-card__actions">
          <Badge variant={failed ? "destructive" : "secondary"} className="tool-result-card__status">
            {failed ? (
              <XCircleIcon data-icon="inline-start" />
            ) : running ? (
              <span className="tool-result-card__status-spinner" data-icon="inline-start" aria-hidden="true" />
            ) : (
              <CheckCircle2Icon data-icon="inline-start" />
            )}
            {label}
          </Badge>
          {metadata?.tool_name && !FILE_EDIT_TOOLS.has(metadata.tool_name) ? (
            <Badge variant="outline" className="tool-result-card__tool-name">{metadata.tool_name}</Badge>
          ) : null}
        </CardAction>
      </CardHeader>
      <CardContent className="tool-result-card__content">
        {children}
        {metadata?.call_id ? <Badge variant="ghost" className="tool-result-card__call-id">{metadata.call_id}</Badge> : null}
      </CardContent>
    </Card>
  );
}

function OutputBlock({ label, value, empty, truncated, tone }: { label: string; value?: string; empty?: string; truncated?: boolean; tone?: "stderr" }) {
  const displayValue = value && value.length > 0 ? value : empty;
  if (!displayValue) return null;
  return (
    <div className="tool-result__section" data-tone={tone}>
      <span className="tool-result__section-label">{label}{truncated ? " · truncated" : ""}</span>
      <pre className="tool-result__pre">{displayValue}</pre>
    </div>
  );
}

function ToolNotice({ label, value, tone }: { label: string; value: string; tone?: "error" }) {
  if (!value) return null;
  return (
    <div className="tool-result__notice" data-tone={tone}>
      <strong>{label}</strong>
      <span>{value}</span>
    </div>
  );
}

function toolNameFor(metadata: ToolCallMetadata | undefined): string {
  return typeof metadata?.tool_name === "string" ? metadata.tool_name : "";
}

function objectValue(value: unknown): Record<string, unknown> | undefined {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : undefined;
}

function arrayValue(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function stringValue(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
}

function numberValue(value: unknown): number | undefined {
  return typeof value === "number" ? value : undefined;
}

function numberOrNull(value: unknown): number | null | undefined {
  return typeof value === "number" || value === null ? value : undefined;
}

function errorText(value: unknown): string {
  if (!value) return "";
  if (typeof value === "string") return value;
  const record = objectValue(value);
  if (record && typeof record.message === "string") return record.message;
  return formatJson(value);
}

function formatJson(value: unknown): string {
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function lineRangeLabel(result: Record<string, unknown> | undefined): string {
  if (!result) return "";
  const start = numberValue(result.start_line);
  const end = numberValue(result.end_line);
  const total = numberValue(result.total_lines);
  if (start && end && total) return `lines ${start}-${end} of ${total}`;
  if (start && end) return `lines ${start}-${end}`;
  return "";
}

function shapeLabel(result: Record<string, unknown> | undefined): string {
  if (!result) return "";
  const rows = numberValue(result.rows) ?? numberValue(result.row_count);
  const columns = numberValue(result.columns) ?? numberValue(result.column_count);
  if (rows !== undefined && columns !== undefined) return `${rows} rows × ${columns} columns`;
  if (rows !== undefined) return `${rows} rows`;
  return "";
}

function formatBytes(value: number | undefined): string {
  if (value === undefined) return "";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}
