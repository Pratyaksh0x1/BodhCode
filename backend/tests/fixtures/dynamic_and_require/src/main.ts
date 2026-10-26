import("./dynamic-target").then((m) => m.run());
const dyn = import(someVar);
const req1 = require("./required-target");
const req2 = require(anotherVar);
import tsReq = require("./ts-required");
