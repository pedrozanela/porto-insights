import { describe, it, expect } from "vitest";
import { bfs, buildNeighbors, degreeMap, neighborsOf } from "../graphModel";

// grafo: a-b, b-c, c-d, a-e  (cadeia + ramo)
const edges = [
  { source: "a", target: "b" },
  { source: "b", target: "c" },
  { source: "c", target: "d" },
  { source: "a", target: "e" },
];

describe("graphModel", () => {
  it("degreeMap conta grau não-direcionado", () => {
    const d = degreeMap(edges);
    expect(d.get("a")).toBe(2);
    expect(d.get("b")).toBe(2);
    expect(d.get("d")).toBe(1);
  });

  it("buildNeighbors é simétrico e aceita pontas como objeto", () => {
    const n = buildNeighbors([{ source: { id: "x" }, target: { id: "y" } }]);
    expect(neighborsOf(n, "x").has("y")).toBe(true);
    expect(neighborsOf(n, "y").has("x")).toBe(true);
  });

  it("bfs por profundidade 1/2/3 a partir de a", () => {
    const n = buildNeighbors(edges);
    expect(bfs(n, "a", 1)).toEqual(new Set(["a", "b", "e"]));
    expect(bfs(n, "a", 2)).toEqual(new Set(["a", "b", "e", "c"]));
    expect(bfs(n, "a", 3)).toEqual(new Set(["a", "b", "e", "c", "d"]));
  });

  it("bfs respeita o conjunto `allowed` (não atravessa nós escondidos)", () => {
    const n = buildNeighbors(edges);
    const allowed = new Set(["a", "b", "e"]); // c/d escondidos
    expect(bfs(n, "a", 3, allowed)).toEqual(new Set(["a", "b", "e"]));
  });
});
