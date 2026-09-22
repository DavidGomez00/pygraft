# Determining `relation_balance_ratio` (and friends) from real data

PyGraft's `{name}.yml` has a "KNOWLEDGE GRAPH ARGS" section (`num_entities`,
`num_triples`, `relation_balance_ratio`, `prop_untyped_entities`, ...) that
drives `generate_kg`. When the goal is a synthetic copy of a *real* graph
(e.g. `output/french_royalty/`), these shouldn't be guessed — they should be
measured from the target `.data/{name}/{name}.tsv` and, for
`relation_balance_ratio`, empirically swept. This note documents the method,
using the French royalty schema as the worked example.

## 1. Measure the target file

Count unique entities, whether they're all typed, and the per-relation
triple counts:

```python
entities, typed = set(), set()
rel_counts = {}
with open(".data/french_royalty/french_royalty.tsv") as f:
    for line in f:
        s, p, o = line.rstrip("\n").split("\t")
        if p == "type":
            typed.add(s)
            entities.add(s)
        else:
            entities.add(s); entities.add(o)
            rel_counts[p] = rel_counts.get(p, 0) + 1

print(len(entities), len(typed))       # 2211 2211 -- fully typed
print(rel_counts)
```

For French royalty this gave 2211 unique entities (100% typed) and:

| relation | count |
|---|---|
| child | 1897 |
| parent | 1239 |
| spouse | 1152 |
| father | 658 |
| mother | 534 |
| successor | 471 |
| predecessor | 471 |

6422 relation triples + 2211 `type` triples = **8633 total**.

Set directly from these numbers:
- `num_entities` = unique entity count (2211)
- `num_triples` = relation triples + type triples (8633)
- `prop_untyped_entities` = 0.0 if (and only if) every entity carries a
  `type` triple in the target, as here

The skew ratio (max count / min count) matters for the next step — here
1897/471 ≈ **4x**.

## 2. Why `relation_balance_ratio` can't be read off directly

PyGraft doesn't take per-relation target weights. It draws one random weight
per relation from `Normal(mean, (1 - relation_balance_ratio) * mean)`,
normalizes so weights sum to 1, then sets
`triples_per_rel[r] = ceil(weight * num_triples)`
([kg_generator.py](../pygraft/pygraft/kg_generator.py), `distribute_relations`).
A single scalar ratio controls *how much spread* is allowed, not the shape
of the real distribution — so there's no formula mapping "my real skew is
4x" to "use ratio X". Worse, a relation can still end up with **zero**
realized triples even when its target weight is nonzero: `generate_one_triple`
retries sampling head/tail pairs, and `check_consistency` /
`check_dom_range` / `procedure_1` / `procedure_2` throw invalid triples back
out (irreflexivity, asymmetry, domain/range, disjointness). With a small
entity pool relative to the requested triple count, a relation dealt a low
weight can lose its entire allocation to rejections. The only reliable way
to pick a ratio is to **empirically sweep it** against the actual
`num_entities`/`num_triples` you settled on in step 1.

## 3. Sweep empirically

Run the pipeline directly via `InstanceGenerator`, skipping `write_kg()`'s
RDF serialization and HermiT reasoner call (both slow and irrelevant to
just counting relations) — this needs `class_info.json`/`relation_info.json`
for the schema to already exist under `output/{name}/`:

```python
import sys
sys.path.insert(0, "/path/to/repo")
from pygraft.kg_generator import InstanceGenerator

ratio = float(sys.argv[1])
drops = 0
for _ in range(20):
    ig = InstanceGenerator(
        schema="french_royalty", num_entities=2211, num_triples=8633,
        relation_balance_ratio=ratio, fast_gen=True, oversample=False,
        prop_untyped_entities=0.0, avg_depth_specific_class=1.0,
        multityping=False, avg_multityping=1.0, format="xml",
    )
    ig.pipeline()
    ig.check_asymmetries()
    ig.check_inverseof_asymmetry()
    ig.check_dom_range()
    ig.procedure_1()
    ig.procedure_2()
    observed = {t[1] for t in ig.kg}
    if set(ig.relation_info["relations"]) - observed:
        drops += 1
print(f"ratio={ratio}: {drops}/20 trials dropped a relation to 0")
```

Each trial costs a few seconds (~5-6s at this graph size), so:
- Run candidate ratios **in parallel** (one process per ratio value,
  backgrounded with `&` / `wait`), not serially — a serial sweep over
  8 ratios x 50 trials took long enough to be worth killing and redoing
  this way.
- Use `flush=True` (or `python -u`) on every print — otherwise, piped to a
  log file, Python block-buffers stdout and nothing shows up until the
  whole sweep exits, which looks indistinguishable from a hang.
- Start with a coarse sweep (~20 trials/ratio) to find the neighborhood,
  then confirm the winning value with more trials (~60-100 combined) since
  the failure mode is a low-probability tail event, not a hard cutoff.

For French royalty (2211 entities / 8633 triples / 7 relations / ~4x skew):

| ratio | drop rate |
|---|---|
| 0.2 | 11/20 |
| 0.3 | 11/20 |
| 0.4 | 5/20 |
| 0.5 | 1/20 |
| 0.6 | 2/80 (confirmed over more trials) |
| 0.7 | 0/100 (confirmed over more trials) |

**0.7 was kept**, even though this dataset's skew (~4x) is far milder than
the previous non-literal dataset's (~95x, `child` 1897 vs `marriedTo` 20)
that had originally motivated testing 0.7 as "the lowest ratio that reliably
keeps all relations present". A milder real skew doesn't mean a lower ratio
is safe — it has to be re-verified against the actual `num_entities`/
`num_triples` in play, because those (not the real skew) are what determine
how much rejection-driven attrition a low-weight relation suffers.

## Summary checklist

1. Parse the target `.tsv`: unique entity count, whether it's fully typed,
   per-relation triple counts.
2. Set `num_entities`, `num_triples`, `prop_untyped_entities` directly from
   those measurements.
3. Sweep `relation_balance_ratio` empirically via `InstanceGenerator`
   (skipping serialization/reasoning) against those exact
   `num_entities`/`num_triples`, in parallel, with unbuffered per-trial
   output.
4. Pick the lowest ratio with ~0% drop rate over a large-enough confirming
   sample, and record the sweep results in the config's comments so the
   next person doesn't have to redo it from scratch.
