import { describe, expect, it } from "vitest";
import { initialTabState, tabReducer } from "./tabState";

describe("tabReducer", () => {
  it("opens a new tab and sets it active", () => {
    const s1 = tabReducer(initialTabState, {
      type: "OPEN_TAB",
      payload: { path: "src/index.ts", content: "console.log('hi');" },
    });
    expect(s1.tabs).toHaveLength(1);
    expect(s1.activePath).toBe("src/index.ts");
    expect(s1.tabs[0].dirty).toBe(false);
  });

  it("does not duplicate already opened tab", () => {
    let state = tabReducer(initialTabState, {
      type: "OPEN_TAB",
      payload: { path: "src/index.ts", content: "first" },
    });
    state = tabReducer(state, {
      type: "OPEN_TAB",
      payload: { path: "src/index.ts", content: "second" },
    });
    expect(state.tabs).toHaveLength(1);
    expect(state.activePath).toBe("src/index.ts");
  });

  it("updates dirty state when content differs from saved content", () => {
    let state = tabReducer(initialTabState, {
      type: "OPEN_TAB",
      payload: { path: "src/index.ts", content: "initial" },
    });
    expect(state.tabs[0].dirty).toBe(false);

    state = tabReducer(state, {
      type: "SET_CONTENT",
      payload: { path: "src/index.ts", content: "modified" },
    });
    expect(state.tabs[0].dirty).toBe(true);

    // Editing back to saved content clears dirty
    state = tabReducer(state, {
      type: "SET_CONTENT",
      payload: { path: "src/index.ts", content: "initial" },
    });
    expect(state.tabs[0].dirty).toBe(false);
  });

  it("clears dirty state on MARK_SAVED", () => {
    let state = tabReducer(initialTabState, {
      type: "OPEN_TAB",
      payload: { path: "src/index.ts", content: "initial" },
    });
    state = tabReducer(state, {
      type: "SET_CONTENT",
      payload: { path: "src/index.ts", content: "new content" },
    });
    expect(state.tabs[0].dirty).toBe(true);

    state = tabReducer(state, {
      type: "MARK_SAVED",
      payload: { path: "src/index.ts", contentHash: "new_hash_123" },
    });
    expect(state.tabs[0].dirty).toBe(false);
    expect(state.tabs[0].savedContent).toBe("new content");
    expect(state.tabs[0].contentHash).toBe("new_hash_123");
  });

  it("closes tab and switches active tab properly", () => {
    let state = tabReducer(initialTabState, {
      type: "OPEN_TAB",
      payload: { path: "file1.ts" },
    });
    state = tabReducer(state, {
      type: "OPEN_TAB",
      payload: { path: "file2.ts" },
    });
    state = tabReducer(state, {
      type: "OPEN_TAB",
      payload: { path: "file3.ts" },
    });
    expect(state.tabs).toHaveLength(3);
    expect(state.activePath).toBe("file3.ts");

    // Close active tab file3.ts -> switches to file2.ts
    state = tabReducer(state, {
      type: "CLOSE_TAB",
      payload: { path: "file3.ts" },
    });
    expect(state.tabs).toHaveLength(2);
    expect(state.activePath).toBe("file2.ts");
  });

  it("closes other tabs on CLOSE_OTHERS", () => {
    let state = tabReducer(initialTabState, {
      type: "OPEN_TAB",
      payload: { path: "file1.ts" },
    });
    state = tabReducer(state, {
      type: "OPEN_TAB",
      payload: { path: "file2.ts" },
    });
    state = tabReducer(state, {
      type: "OPEN_TAB",
      payload: { path: "file3.ts" },
    });

    state = tabReducer(state, {
      type: "CLOSE_OTHERS",
      payload: { path: "file2.ts" },
    });
    expect(state.tabs).toHaveLength(1);
    expect(state.tabs[0].path).toBe("file2.ts");
    expect(state.activePath).toBe("file2.ts");
  });
});
