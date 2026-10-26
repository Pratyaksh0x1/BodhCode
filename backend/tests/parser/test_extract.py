from app.parser.extract import extract_file
from app.parser.types import ImportRef


def test_basic_imports():
    source = b"""
import defaultExport from "mod-default";
import { namedA, namedB as aliasB } from "mod-named";
import * as namespaceA from "mod-namespace";
import "mod-side-effect";
import type { TypeOnlyA } from "mod-type-only";
import { type AllType1, type AllType2 } from "mod-all-type";
import { type MixedType, regularValue } from "mod-mixed";
"""
    facts = extract_file("src/index.ts", source)
    assert facts.path == "src/index.ts"
    assert len(facts.imports) == 7

    assert facts.imports[0] == ImportRef("mod-default", "import", 2, False)
    assert facts.imports[1] == ImportRef("mod-named", "import", 3, False)
    assert facts.imports[2] == ImportRef("mod-namespace", "import", 4, False)
    assert facts.imports[3] == ImportRef("mod-side-effect", "import", 5, False)
    assert facts.imports[4] == ImportRef("mod-type-only", "import", 6, True)
    assert facts.imports[5] == ImportRef("mod-all-type", "import", 7, True)
    assert facts.imports[6] == ImportRef("mod-mixed", "import", 8, False)
    assert facts.unresolved_dynamic == 0
    assert facts.flags == ()


def test_reexports():
    source = b"""
export * from "./barrel-all";
export * as ns from "./barrel-ns";
export { itemA, itemB as itemBAlias } from "./barrel-named";
export type { TypeItem } from "./barrel-type";
"""
    facts = extract_file("src/barrel.ts", source)
    assert len(facts.imports) == 4
    assert facts.imports[0] == ImportRef("./barrel-all", "reexport", 2, False)
    assert facts.imports[1] == ImportRef("./barrel-ns", "reexport", 3, False)
    assert facts.imports[2] == ImportRef("./barrel-named", "reexport", 4, False)
    assert facts.imports[3] == ImportRef("./barrel-type", "reexport", 5, True)

    # export * as ns exports "ns"
    # export { itemA, itemB as itemBAlias } exports "itemA", "itemBAlias"
    # export * does not add names
    assert facts.exports == ("TypeItem", "itemA", "itemBAlias", "ns")


def test_dynamic_imports_and_require():
    source = b"""
const a = import("dyn-lit");
const b = import(someVar);
const c = import(`template-lit`);
const d = import(`prefix/${dynamicVar}`);
const e = require("req-lit");
const f = require(otherVar);
const g = otherObj.require("ignored-member-call");
import tsReq = require("ts-req-lit");
"""
    facts = extract_file("src/dynamic.ts", source)

    # 4 resolved literal calls/imports
    # 3 unresolved: import(someVar), import(`prefix/${dynamicVar}`), require(otherVar)
    assert facts.unresolved_dynamic == 3

    assert ImportRef("dyn-lit", "dynamic", 2, False) in facts.imports
    assert ImportRef("template-lit", "dynamic", 4, False) in facts.imports
    assert ImportRef("req-lit", "require", 6, False) in facts.imports
    assert ImportRef("ts-req-lit", "require", 9, False) in facts.imports
    assert len(facts.imports) == 4


def test_named_and_default_exports():
    source = b"""
export function testFn() {}
export class TestClass {}
export const c1 = 1, c2 = 2;
export let l1 = 3;
export var v1 = 4;
export enum TestEnum { A }
export interface TestInterface {}
export type TestType = string;
export namespace TestNamespace {}
export { localX, localY as aliasY };
export default function defaultFn() {}
"""
    facts = extract_file("src/exports.ts", source)
    assert facts.has_default_export is True
    assert facts.exports == (
        "TestClass",
        "TestEnum",
        "TestInterface",
        "TestNamespace",
        "TestType",
        "aliasY",
        "c1",
        "c2",
        "l1",
        "localX",
        "testFn",
        "v1",
    )


def test_broken_syntax():
    source = b"""
import { good } from "valid-import";
export const a = 1;
function broken( {
"""
    facts = extract_file("src/broken.ts", source)
    assert "parse_error" in facts.flags
    assert ImportRef("valid-import", "import", 2, False) in facts.imports
    assert "a" in facts.exports


def test_skipped_large_and_unsupported():
    large_source = b"const x = 1;\n" * 100_000  # > 1MB
    facts_large = extract_file("src/large.ts", large_source)
    assert facts_large.flags == ("skipped_large",)
    assert facts_large.imports == ()
    assert facts_large.exports == ()

    facts_unsupported = extract_file("src/image.png", b"fake binary")
    assert facts_unsupported.flags == ("skipped_unsupported",)


def test_determinism_and_sorting():
    source = b"""
import { z } from "z-mod";
import { a } from "a-mod";
export const z_var = 1;
export const a_var = 2;
"""
    facts1 = extract_file("src/det.ts", source)
    facts2 = extract_file("src/det.ts", source)
    assert facts1 == facts2
    assert facts1.exports == ("a_var", "z_var")
    assert [imp.specifier for imp in facts1.imports] == ["z-mod", "a-mod"]
