import { useEffect, useState } from "react";
import { searchSkillMentions } from "../api";

let catalogPromise: Promise<Set<string>> | null = null;
let catalogNames: Set<string> | null = null;

function loadSkillCatalog(): Promise<Set<string>> {
  if (catalogNames) return Promise.resolve(catalogNames);
  catalogPromise ??= searchSkillMentions("", 200)
    .then((result) => {
      catalogNames = new Set(result.items.map((item) => item.name));
      return catalogNames;
    })
    .catch(() => {
      catalogNames = new Set();
      return catalogNames;
    });
  return catalogPromise;
}

export function useSkillCatalog(): Set<string> {
  const [skillNames, setSkillNames] = useState<Set<string>>(() => catalogNames ?? new Set());

  useEffect(() => {
    let cancelled = false;
    void loadSkillCatalog().then((names) => {
      if (!cancelled) setSkillNames(names);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return skillNames;
}

export function resetSkillCatalogForTest(): void {
  catalogPromise = null;
  catalogNames = null;
}
