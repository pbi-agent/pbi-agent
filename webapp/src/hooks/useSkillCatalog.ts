import { useEffect, useState } from "react";
import { searchSkillMentions } from "../api";

type SkillCatalog = {
  names: Set<string>;
  /** Workspace-relative `SKILL.md` path → skill name. */
  namesByPath: Map<string, string>;
};

const EMPTY_CATALOG: SkillCatalog = { names: new Set(), namesByPath: new Map() };

let catalogPromise: Promise<SkillCatalog> | null = null;
let catalog: SkillCatalog | null = null;

function loadSkillCatalog(): Promise<SkillCatalog> {
  if (catalog) return Promise.resolve(catalog);
  catalogPromise ??= searchSkillMentions("", 200)
    .then((result) => {
      catalog = {
        names: new Set(result.items.map((item) => item.name)),
        namesByPath: new Map(result.items.map((item) => [item.path, item.name])),
      };
      return catalog;
    })
    .catch(() => {
      catalog = EMPTY_CATALOG;
      return catalog;
    });
  return catalogPromise;
}

function useLoadedSkillCatalog(): SkillCatalog {
  const [loaded, setLoaded] = useState<SkillCatalog>(() => catalog ?? EMPTY_CATALOG);

  useEffect(() => {
    let cancelled = false;
    void loadSkillCatalog().then((next) => {
      if (!cancelled) setLoaded(next);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return loaded;
}

export function useSkillCatalog(): Set<string> {
  return useLoadedSkillCatalog().names;
}

export function useSkillNamesByPath(): Map<string, string> {
  return useLoadedSkillCatalog().namesByPath;
}

export function resetSkillCatalogForTest(): void {
  catalogPromise = null;
  catalog = null;
}
