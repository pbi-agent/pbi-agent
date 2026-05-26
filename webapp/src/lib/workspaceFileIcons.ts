import materialIconTheme from "material-icon-theme/dist/material-icons.json";

type IconDefinition = {
  iconPath: string;
};

type IconManifest = {
  iconDefinitions: Record<string, IconDefinition | undefined>;
  fileNames: Record<string, string | undefined>;
  fileExtensions: Record<string, string | undefined>;
  folderNames: Record<string, string | undefined>;
  folderNamesExpanded: Record<string, string | undefined>;
  file: string;
  folder: string;
  folderExpanded: string;
};

export type WorkspaceTreeIcon = {
  iconName: string;
  url: string;
};

const manifest = materialIconTheme as IconManifest;
const iconModules = import.meta.glob<string>(
  "../../../node_modules/material-icon-theme/icons/*.svg",
  {
    eager: true,
    import: "default",
    query: "?url&no-inline",
  },
);
const iconUrlsByFileName = new Map(
  Object.entries(iconModules).map(([path, url]) => [path.split("/").at(-1) ?? path, url]),
);

export function getWorkspaceFileIcon(
  path: string,
  fallbackIconName = manifest.file || "file",
): WorkspaceTreeIcon {
  const normalizedPath = normalizePath(path);
  const fileName = getBaseName(normalizedPath);
  const iconName =
    findAssociation(manifest.fileNames, [
      ...pathSuffixCandidates(normalizedPath),
      fileName,
      fileName.toLowerCase(),
    ])
    ?? findAssociation(manifest.fileExtensions, extensionCandidates(fileName));
  return resolveIcon(iconName, fallbackIconName);
}

export function getWorkspaceFolderIcon(
  path: string,
  expanded: boolean,
): WorkspaceTreeIcon {
  const normalizedPath = normalizePath(path);
  const folderName = getBaseName(normalizedPath);
  const associations = expanded ? manifest.folderNamesExpanded : manifest.folderNames;
  const defaultIcon = expanded
    ? manifest.folderExpanded || "folder-open"
    : manifest.folder || "folder";
  const iconName = findAssociation(associations, [
    ...pathSuffixCandidates(normalizedPath),
    folderName,
    folderName.toLowerCase(),
  ]);
  return resolveIcon(iconName, defaultIcon);
}

function resolveIcon(
  iconName: string | undefined,
  fallbackIconName: string,
): WorkspaceTreeIcon {
  const fallbackName = fallbackIconName || "file";
  const resolvedName = iconName && materialIconUrl(iconName) ? iconName : fallbackName;
  return {
    iconName: resolvedName,
    url: materialIconUrl(resolvedName) ?? materialIconUrl("file") ?? "",
  };
}

function materialIconUrl(iconName: string): string | null {
  const iconPath = manifest.iconDefinitions[iconName]?.iconPath;
  if (!iconPath) return null;
  const fileName = iconPath.split("/").at(-1);
  if (!fileName) return null;
  return iconUrlsByFileName.get(fileName) ?? null;
}

function findAssociation(
  associations: Record<string, string | undefined>,
  candidates: string[],
): string | undefined {
  const seen = new Set<string>();
  for (const candidate of candidates) {
    if (!candidate || seen.has(candidate)) continue;
    seen.add(candidate);
    const iconName = associations[candidate] ?? associations[candidate.toLowerCase()];
    if (iconName) return iconName;
  }
  return undefined;
}

function pathSuffixCandidates(path: string): string[] {
  const parts = path.split("/").filter(Boolean);
  return parts.flatMap((_part, index) => {
    const suffix = parts.slice(index).join("/");
    return [suffix, suffix.toLowerCase()];
  });
}

function extensionCandidates(fileName: string): string[] {
  const lowerFileName = fileName.toLowerCase();
  const parts = lowerFileName.split(".");
  if (parts.length < 2) return [];
  return parts
    .slice(1)
    .map((_part, index) => parts.slice(index + 1).join("."))
    .filter(Boolean);
}

function normalizePath(path: string): string {
  return path.replaceAll("\\", "/");
}

function getBaseName(path: string): string {
  return path.split("/").filter(Boolean).at(-1) ?? path;
}