// Tests de la logique de la carte (sans navigateur) : node tests/test_card.mjs
// La carte est un fork de heating-schedule-card (MIT) ; on teste ici ce qui a été modifié pour PocketHome.
import assert from "node:assert/strict";
import { pathToFileURL } from "node:url";
import path from "node:path";

const classes = {};
globalThis.HTMLElement = class {};
globalThis.customElements = { define: (n, c) => { classes[n] = c; }, get: () => undefined };
globalThis.window = {};
globalThis.document = {};
Object.defineProperty(globalThis, "navigator", { value: { language: "fr-FR" }, configurable: true });

const root = path.join(path.dirname(new URL(import.meta.url).pathname), "..", "custom_components", "pockethome", "www");
await import(pathToFileURL(path.join(root, "pockethome-program-card.js")).href);
const Card = classes["pockethome-program-card"];
assert.ok(Card, "carte enregistrée");

// Programme 10 lu sur la centrale : lundi et mardi réglés, les autres jours vides.
const program = {
  number: 10, name: "Test HA",
  days: [
    [{ start: "00:00", temperature: 17 }, { start: "06:30", temperature: 21 }, { start: "08:00", temperature: 17 }],
    [{ start: "00:00", temperature: 18 }, { start: "07:10", temperature: 24 }, { start: "09:00", temperature: 17 }],
    [], [], [], [], [],
  ],
};

async function newCard(prog = program) {
  const c = new Card();
  c.setConfig({ program: 10 });
  c.calls = [];
  c._hass = {
    callWS: async (msg) => { c.calls.push(msg); return { response: structuredClone(prog) }; },
    callService: async (d, s, data) => { c.calls.push({ d, s, data }); },
  };
  c._render = () => {};
  c._body = { querySelector: () => null, matches: () => false };
  await c._load();
  return c;
}
const blocks = (c, day) => c._data.days[day].map((b) => [b.from, b.to, b.value]);

// setConfig : le numéro de programme est obligatoire (1 à 22)
for (const bad of [{ program: 0 }, { program: 23 }, { program: "x" }]) {
  assert.throws(() => new Card().setConfig(bad));
}

// sans program : mode liste déroulante, rien n'est chargé tant qu'aucun programme n'est choisi
{
  const sel = new Card();
  sel.setConfig({});
  assert.equal(sel._fixed, false);
  assert.equal(sel._program, null);
  assert.match(sel._selectorHtml(), /<select class="prog-select"[^>]*>.*<option value="22">22<\/option>/);
  assert.equal(new Card().setConfig({ program: 3 }) ?? true, true);
  const fixed = new Card(); fixed.setConfig({ program: 3 });
  assert.equal(fixed._selectorHtml(), "");
}

// chargement : appel du service, blocs contigus jusqu'à 24:00, jours vides = température du dernier jour renseigné
let c = await newCard();
assert.deepEqual(c.calls[0], { type: "call_service", domain: "pockethome", service: "get_program", service_data: { program: 10 }, return_response: true });
assert.deepEqual(blocks(c, "monday"), [["00:00", "06:30", 17], ["06:30", "08:00", 21], ["08:00", "24:00", 17]]);
assert.deepEqual(blocks(c, "wednesday"), [["00:00", "24:00", 17]]);   // reprend le mardi
assert.deepEqual(blocks(c, "sunday"), [["00:00", "24:00", 17]]);      // jeudi à dimanche : toujours 17
assert.equal(c._data.name, "Test HA");
assert.equal(c._dirty, false);
assert.deepEqual(c._validationErrors(), []);

// un jour qui ne commence pas à 00:00 reçoit un bloc explicite avec la température de la veille
c = await newCard({ ...program, days: [[{ start: "05:30", temperature: 21 }, { start: "22:00", temperature: 18.5 }], ...program.days.slice(1)] });
assert.deepEqual(blocks(c, "monday"), [["00:00", "05:30", 17], ["05:30", "22:00", 21], ["22:00", "24:00", 18.5]]);

// ajout : coupe le bloc le plus long sur la grille de 10 min, même température
c = await newCard();
const group = { days: ["monday"] };
c._layout = [["monday"]];
c._add(group);
// 08:00-24:00 (960 min) est le plus long : coupé en deux à 16:00
assert.deepEqual(blocks(c, "monday"), [["00:00", "06:30", 17], ["06:30", "08:00", 21], ["08:00", "16:00", 17], ["16:00", "24:00", 17]]);
assert.equal(c._dirty, true);

// limite de la centrale : 6 plages par jour
for (let i = 0; i < 5; i++) { c._error = null; c._add(group); }
assert.equal(c._data.days.monday.length, 6);
c._add(group);
assert.match(c._error, /6 plages maximum|at most 6/);
assert.equal(c._data.days.monday.length, 6);
assert.deepEqual(c._validationErrors(), []);

// suppression : le premier bloc supprimé laisse le suivant à 00:00 ; on garde toujours un bloc
c = await newCard();
c._layout = [["monday"]];
c._remove({ days: ["monday"] }, 0);
assert.deepEqual(blocks(c, "monday")[0], ["00:00", "08:00", 21]);
c._remove({ days: ["wednesday"] }, 0);
assert.equal(c._data.days.wednesday.length, 1);

// déplacement d'un début : retri et recalcul des fins
c = await newCard();
c._change({ days: ["monday"] }, 1, "from", "07:30");
assert.deepEqual(blocks(c, "monday"), [["00:00", "07:30", 17], ["07:30", "08:00", 21], ["08:00", "24:00", 17]]);
c._change({ days: ["monday"] }, 1, "from", "09:00");   // dépasse le bloc suivant : réordonné
assert.deepEqual(blocks(c, "monday").map((b) => b[0]), ["00:00", "08:00", "09:00"]);

// validation : deux débuts identiques
c = await newCard();
c._change({ days: ["monday"] }, 2, "from", "06:30");
assert.equal(c._validationErrors().length, 1);
assert.match(c._validationErrors()[0], /strictement croissants/);

// température : changement de valeur sans rechargement, état modifié
c = await newCard();
c._body.querySelector = () => null;
c._refreshState = () => {};
c._change({ days: ["monday"] }, 1, "value", 21.5);
assert.equal(c._data.days.monday[1].value, 21.5);
c._dirty = c._signature() !== c._original;
assert.equal(c._dirty, true);

// enregistrement : set_program avec les débuts et températures, puis relecture de la centrale
c = await newCard();
c._layout = [["monday"]];
c._data.name = "Test HA 2";
c._change({ days: ["monday"] }, 1, "value", 22);
await c._save();
const call = c.calls.find((x) => x.s === "set_program");
assert.equal(call.d, "pockethome");
assert.equal(call.data.program, 10);
assert.equal(call.data.name, "Test HA 2");
assert.equal(call.data.days.length, 7);
assert.deepEqual(call.data.days[0], [{ start: "00:00", temperature: 17 }, { start: "06:30", temperature: 22 }, { start: "08:00", temperature: 17 }]);
assert.deepEqual(call.data.days[2], [{ start: "00:00", temperature: 17 }]);
assert.equal(c.calls.filter((x) => x.service === "get_program").length, 2, "relu après enregistrement");

// copier-coller d'un groupe de jours
c = await newCard();
c._layout = [["monday"], ["tuesday"], ["wednesday", "thursday", "friday", "saturday", "sunday"]];
c._copy({ days: ["monday"] });
c._paste({ days: ["tuesday"] });
assert.deepEqual(blocks(c, "tuesday"), blocks(c, "monday"));

console.log("carte : tous les tests passent");

