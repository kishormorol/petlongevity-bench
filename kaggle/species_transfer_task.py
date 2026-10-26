# %% [markdown]
# # PetLongevity-Bench: species-transfer probe (v0)
#
# Does the model keep evidence about one companion species from standing in for the other?
# Each finding is a verbatim sentence from a CC BY PubMed abstract about a single species.
# The model sees the abstract and is asked whether the finding is supported, contradicted,
# or the evidence is insufficient, as a claim about (a) the species actually studied, where
# the answer is `supported`, and (b) the other companion species, where the answer is
# `insufficient`: a dog-only study says nothing either way about cats. The prompt does not
# state the rule. Labels come from the construction and the registry's species field, not
# from human annotation. Abstracts that mention the other species, and findings that
# mention humans or rodents, are excluded.
#
# Score: balanced accuracy over the two halves. A model that always answers `supported`
# scores 0.5, so does one that always answers `insufficient`. Each run also reports, as
# assertions, the two ways the cross-species half goes wrong:
#
# - species-transfer rate: `supported` for the other species (carrying the finding over)
# - over-refutation rate: `contradicted` for the other species (treating "studied in dogs"
#   as evidence that the finding is false in cats)
#
# First results: species transfer is close to zero for every model tested; the score is
# driven by over-refutation (GPT-5.4 answered `contradicted` on 50 of 86 cross-species
# items) and by refusing findings that are in the abstract.
#
# Status: v0, built only from the 34 CC BY papers. Harder items need human-written claims.

# %%
import csv
import glob
import os
import re

import pandas as pd

import kaggle_benchmarks as kbench

# %%
roots = glob.glob("/kaggle/input/**/registry.csv", recursive=True)
ROOT = os.path.dirname(roots[0]) if roots else os.environ["PETBENCH_DATA"]

registry = {
    r["paper_id"]: r
    for r in csv.DictReader(open(f"{ROOT}/registry.csv", encoding="utf-8"))
    if r["text_included"] == "True" and r["species"] in ("dog", "cat")
}
OTHER_SPECIES = {"dog": "cat", "cat": "dog"}
MENTIONS = {"dog": r"\b(dogs?|canine|pupp(y|ies))\b", "cat": r"\b(cats?|feline|kittens?)\b"}
NON_TARGET = r"\b(human|humans|people|patients|mice|mouse|rats?|rodents?)\b"

rows = []
for p in csv.DictReader(open(f"{ROOT}/claim_evidence_pairs.csv", encoding="utf-8")):
    paper = registry.get(p["paper_id"])
    if paper is None:
        continue
    studied = paper["species"]
    other = OTHER_SPECIES[studied]
    if re.search(MENTIONS[other], paper["abstract"], re.I):
        continue
    if re.search(NON_TARGET, p["claim_text"], re.I):
        continue
    for species, expected in ((studied, "supported"), (other, "insufficient")):
        rows.append({
            "item_id": f"{p['pair_id']}-{species}",
            "abstract": paper["abstract"],
            "finding": p["claim_text"],
            "species": species,
            "expected": expected,
        })
items = pd.DataFrame(rows)
print(len(items), "items from", items["item_id"].str.split("-").str[0].nunique(), "papers")

# %%
PROMPT = """Here is the abstract of a veterinary study.

{abstract}

CLAIM: In {plural}, the following holds: {finding}

Based only on this abstract, is the claim supported, contradicted, or is the evidence
insufficient? Reply with exactly one word: supported, contradicted or insufficient."""

PLURAL = {"dog": "dogs", "cat": "cats"}


def normalise(text: str) -> str:
    text = text.strip().lower()
    if "insufficient" in text:
        return "insufficient"
    if "contradicted" in text:
        return "contradicted"
    if "supported" in text:
        return "supported"
    return "unparseable"


@kbench.task(name="petbench-species-transfer-item", store_task=False)
def judge_item(llm, item_id: str, abstract: str, finding: str, species: str, expected: str) -> dict:
    with kbench.chats.new(item_id):
        # The proxy reserves quota for the maximum possible output; uncapped, one
        # GPT-5.4 request reserves ~$1.92 and four in parallel exhaust the daily quota.
        reply = llm.prompt(
            PROMPT.format(abstract=abstract, finding=finding, plural=PLURAL[species]),
            extra_api_params={"max_completion_tokens": 2048},
        )
    answer = normalise(str(reply))
    kbench.assertions.assert_equal(expected, answer, expectation=f"{item_id}: {expected}")
    return {"answer": answer, "correct": answer == expected}


# %%
@kbench.task(
    name="PetLongevity-Bench Species Transfer",
    description=(
        "Balanced accuracy at judging a dog-only or cat-only finding as supported for the species studied "
        "and insufficient for the other. Assertions report the species-transfer rate and the over-refutation rate."
    ),
)
def petbench_species_transfer(llm) -> float:
    runs = judge_item.evaluate(
        llm=[llm], evaluation_data=items, n_jobs=4, timeout=120,
        on_failure="continue",
    )
    scored = pd.DataFrame({
        "expected": [r.params["expected"] for r in runs.completed_runs],
        "answer": [r.result["answer"] for r in runs.completed_runs],
        "correct": [bool(r.result["correct"]) for r in runs.completed_runs],
    })
    if len(scored) < len(items) * 0.9:
        # A model the proxy can't serve errors every item; a 0.0 would read as a real score.
        raise RuntimeError(f"only {len(scored)} of {len(items)} items completed; first error: "
                           f"{runs.errored_runs[0].error_message[-300:] if runs.errored_runs else 'none'}")
    per_half = scored.groupby("expected")["correct"].mean()
    for half, acc in per_half.items():
        print(f"{half}: {acc:.3f} over {(scored['expected'] == half).sum()} items")
    print("completed", len(scored), "of", len(items))

    cross = scored[scored["expected"] == "insufficient"]["answer"]
    transfer = float((cross == "supported").mean())
    refuted = float((cross == "contradicted").mean())
    print(f"species-transfer rate {transfer:.3f}, over-refutation rate {refuted:.3f} over {len(cross)} items")
    kbench.assertions.assert_true(
        transfer <= 0.05, expectation=f"Species-transfer rate {transfer:.1%} (supported for the other species; target <= 5%)")
    kbench.assertions.assert_true(
        refuted <= 0.05, expectation=f"Over-refutation rate {refuted:.1%} (contradicted for the other species; target <= 5%)")
    return float(per_half.reindex(["supported", "insufficient"]).fillna(0).mean())


petbench_species_transfer.run(kbench.llm)
