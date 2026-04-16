import { useSessionStore } from "../store";

const initialSessionStoreState = useSessionStore.getState();

export function resetSessionStore(): void {
  useSessionStore.setState(initialSessionStoreState, true);
}
