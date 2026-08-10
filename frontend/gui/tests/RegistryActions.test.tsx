import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import { describe, expect, it, vi } from "vitest";
import { RegistryActions } from "../src/renderer/RegistryActions.js";

function renderRegistryActions() {
  const props = {
    onRegistryValidate: vi.fn().mockResolvedValue({ valid: true }),
    onRegistryPublish: vi.fn().mockResolvedValue({ published: true }),
    onRegistryReindex: vi.fn().mockResolvedValue({ indexed: true }),
    onRegistryRetire: vi.fn().mockResolvedValue({ retired: true }),
    onRegistryTrust: vi.fn().mockResolvedValue({ trust_status: "trusted" }),
  };
  render(<RegistryActions {...props} />);
  return props;
}

describe("RegistryActions", () => {
  it("initiates explicit registry actions through supplied handlers", async () => {
    const props = renderRegistryActions();

    fireEvent.change(screen.getByLabelText("Registry draft path"), { target: { value: "/tmp/demo.yaml" } });
    fireEvent.change(screen.getByLabelText("Registry kind"), { target: { value: "skills" } });
    fireEvent.change(screen.getByLabelText("Registry name"), { target: { value: "demo" } });
    fireEvent.change(screen.getByLabelText("Registry version"), { target: { value: "1.2.3" } });
    fireEvent.change(screen.getByLabelText("Registry trust status"), { target: { value: "blocked" } });

    fireEvent.click(screen.getByText("Validate"));
    await waitFor(() => expect(props.onRegistryValidate).toHaveBeenCalledWith("/tmp/demo.yaml", "skills"));

    fireEvent.click(screen.getByText("Publish"));
    await waitFor(() => expect(props.onRegistryPublish).toHaveBeenCalledWith("/tmp/demo.yaml", "skills"));

    fireEvent.click(screen.getByText("Reindex"));
    await waitFor(() => expect(props.onRegistryReindex).toHaveBeenCalled());

    fireEvent.click(screen.getByText("Retire"));
    await waitFor(() => expect(props.onRegistryRetire).toHaveBeenCalledWith("skills", "demo", "1.2.3"));

    fireEvent.click(screen.getByText("Set trust"));
    await waitFor(() => expect(props.onRegistryTrust).toHaveBeenCalledWith("skills", "demo", "1.2.3", "blocked"));

    expect(await screen.findByLabelText("Registry action result")).toBeTruthy();
  });
});
