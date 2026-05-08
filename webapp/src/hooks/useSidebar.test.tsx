import { act, render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { useSidebarShortcut, useSidebarStore } from "./useSidebar";

function ShortcutHost() {
  useSidebarShortcut();
  return null;
}

describe("useSidebarStore", () => {
  beforeEach(() => {
    act(() => {
      useSidebarStore.setState({ isOpen: true });
    });
  });

  it("toggles, opens, closes and sets the open state", () => {
    expect(useSidebarStore.getState().isOpen).toBe(true);

    act(() => useSidebarStore.getState().toggle());
    expect(useSidebarStore.getState().isOpen).toBe(false);

    act(() => useSidebarStore.getState().open());
    expect(useSidebarStore.getState().isOpen).toBe(true);

    act(() => useSidebarStore.getState().close());
    expect(useSidebarStore.getState().isOpen).toBe(false);

    act(() => useSidebarStore.getState().setOpen(true));
    expect(useSidebarStore.getState().isOpen).toBe(true);
  });
});

describe("useSidebarShortcut", () => {
  beforeEach(() => {
    act(() => {
      useSidebarStore.setState({ isOpen: true });
    });
  });

  afterEach(() => {
    act(() => {
      useSidebarStore.setState({ isOpen: true });
    });
  });

  it("toggles the sidebar when Ctrl+B is pressed", async () => {
    const user = userEvent.setup();
    render(<ShortcutHost />);

    await user.keyboard("{Control>}b{/Control}");
    expect(useSidebarStore.getState().isOpen).toBe(false);

    await user.keyboard("{Control>}b{/Control}");
    expect(useSidebarStore.getState().isOpen).toBe(true);
  });

  it("toggles the sidebar when Cmd+B is pressed", async () => {
    const user = userEvent.setup();
    render(<ShortcutHost />);

    await user.keyboard("{Meta>}b{/Meta}");
    expect(useSidebarStore.getState().isOpen).toBe(false);
  });

  it("ignores Ctrl+B when shift or alt are also held", async () => {
    const user = userEvent.setup();
    render(<ShortcutHost />);

    await user.keyboard("{Control>}{Shift>}b{/Shift}{/Control}");
    expect(useSidebarStore.getState().isOpen).toBe(true);

    await user.keyboard("{Control>}{Alt>}b{/Alt}{/Control}");
    expect(useSidebarStore.getState().isOpen).toBe(true);
  });

  it("ignores other keys with the modifier", async () => {
    const user = userEvent.setup();
    render(<ShortcutHost />);

    await user.keyboard("{Control>}a{/Control}");
    expect(useSidebarStore.getState().isOpen).toBe(true);
  });

  it("ignores plain b without a modifier", async () => {
    const user = userEvent.setup();
    render(<ShortcutHost />);

    await user.keyboard("b");
    expect(useSidebarStore.getState().isOpen).toBe(true);
  });
});
