import { screen } from "@testing-library/react";
import { StageColumn } from "./StageColumn";
import { renderWithProviders } from "../../test/render";
import type { BoardStage } from "../../types";

vi.mock("@dnd-kit/core", () => ({
  useDroppable: () => ({
    isOver: false,
    setNodeRef: vi.fn(),
  }),
}));

vi.mock("@dnd-kit/sortable", () => ({
  useSortable: () => ({
    attributes: {},
    listeners: {},
    setNodeRef: vi.fn(),
    transform: null,
    transition: undefined,
    isDragging: false,
  }),
}));

vi.mock("@dnd-kit/utilities", () => ({
  CSS: {
    Transform: {
      toString: () => undefined,
    },
  },
}));

function makeStage(overrides: Partial<BoardStage> = {}): BoardStage {
  return {
    id: "review",
    name: "Review",
    position: 1,
    profile_id: "some-profile",
    command_id: "some-command",
    auto_start: true,
    ...overrides,
  };
}

describe("StageColumn", () => {
  it("renders the stage name and count without metadata badges in the header", () => {
    const { container } = renderWithProviders(
      <StageColumn
        stage={makeStage()}
        tasks={[]}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        onRun={vi.fn()}
      />,
    );

    expect(screen.getByText("Review")).toBeInTheDocument();
    expect(screen.queryByText("auto-start")).not.toBeInTheDocument();
    expect(screen.queryByText("command:some-command")).not.toBeInTheDocument();
    expect(screen.queryByText("profile:some-profile")).not.toBeInTheDocument();
    expect(container.querySelector(".board-column__meta")).toBeNull();
  });
});
