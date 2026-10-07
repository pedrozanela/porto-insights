// Testes do frontend sem npm:  node --import ./frontend/tests/register.mjs --test 'frontend/tests/*.test.ts'
import { register } from "node:module";

register("./hooks.mjs", import.meta.url);
