import { useQuery } from "@tanstack/react-query";
import { fetchLocalSttStatus } from "../api";
import type { LocalSttStatus } from "../types";

export const LOCAL_STT_STATUS_QUERY_KEY = ["stt-local-status"];

/** Install state of the on-device speech model; polls while it downloads. */
export function useLocalSttStatus(enabled = true): LocalSttStatus | undefined {
  const query = useQuery({
    queryKey: LOCAL_STT_STATUS_QUERY_KEY,
    queryFn: fetchLocalSttStatus,
    enabled,
    retry: false,
    refetchInterval: (current) =>
      current.state.data?.state === "downloading" ? 1_500 : false,
  });
  return query.data;
}

export function localSttDownloadPercent(status: LocalSttStatus): number {
  if (status.total_bytes <= 0) return 0;
  return Math.floor((100 * status.downloaded_bytes) / status.total_bytes);
}
