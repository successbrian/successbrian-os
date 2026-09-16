#!/usr/bin/env python3
"""
worker_builder.py — the "self-assembling workforce" pattern.

The idea this file demonstrates:

  1. You don't ship a fixed team of agents. You ship a *builder*.
  2. The builder watches what the ecosystem needs and assembles a specialized
     worker for each need — on its own, no instruction.
  3. Every worker carries a tuning loop: it records how it performed and gets
     better the more it runs for *that specific* environment.

This is the generalizable recipe. The production version swaps the toy worker
for a real agent and real model fine-tuning; those details are private.

Run:  python3 worker_builder.py
"""

from dataclasses import dataclass, field


@dataclass
class WorkerRecipe:
    """The spec for one kind of specialized worker."""
    name: str          # e.g. "refund"
    role: str          # the narrow job it does
    capability: str    # input -> output shape
    tuning_metric: str # what "better" means for this worker


@dataclass
class Worker:
    recipe: WorkerRecipe
    runs: int = 0
    score: float = 0.0      # quality on tuning_metric, 0..1
    history: list = field(default_factory=list)

    def run(self, task: str) -> str:
        raise NotImplementedError

    def feedback(self, good: bool):
        """Tuning loop: each outcome nudges the worker toward its local optimum."""
        self.runs += 1
        self.score = (self.score * (self.runs - 1) + (1.0 if good else 0.0)) / self.runs
        self.history.append(good)


class KeywordTagger(Worker):
    """A toy worker: tags a message by learning keywords from labeled feedback."""

    def __init__(self, recipe: WorkerRecipe):
        super().__init__(recipe)
        self.keywords: set = set()

    def run(self, task: str) -> str:
        hits = [k for k in self.keywords if k in task.lower()]
        return self.recipe.name if hits else "unknown"

    def feedback(self, good: bool, example: str = ""):
        super().feedback(good)
        if good and example:
            # crude learning: absorb useful keywords from the labeled example
            for word in example.lower().split():
                if len(word) > 3:
                    self.keywords.add(word)


class WorkerBuilder:
    """Assembles specialized workers from recipes, on demand, and tunes them."""

    def __init__(self):
        self.recipes = {}

    def register_recipe(self, recipe: WorkerRecipe):
        self.recipes[recipe.name] = recipe

    def observe_needs(self, tasks):
        """Decide what workers the ecosystem needs. Stub — production uses real signal."""
        return sorted({t for t in tasks})

    def build(self, name: str) -> KeywordTagger:
        return KeywordTagger(self.recipes[name])


def main():
    builder = WorkerBuilder()
    builder.register_recipe(WorkerRecipe("refund", "tag refund requests", "text->label", "f1"))
    builder.register_recipe(WorkerRecipe("pricing", "tag pricing questions", "text->label", "f1"))

    # 1. Observe what's needed, then assemble the team — no instruction.
    needs = builder.observe_needs(["refund", "pricing", "refund"])
    workers = {name: builder.build(name) for name in needs}
    print(f"assembled {len(workers)} specialized workers: {', '.join(workers)}")

    # 2. Before tuning, a worker knows nothing and fails to tag.
    before = workers["refund"].run("i want my money back for this order")
    print(f"  refund worker BEFORE tuning -> '{before}' (score {workers['refund'].score:.2f})")

    # 3. The tuning loop: real examples + feedback make each worker better.
    training = [
        ("refund", "i want my money back for this order", True),
        ("refund", "how do i return this item please", True),
        ("pricing", "what does the pro plan cost", True),
        ("pricing", "do you have a discount available", True),
    ]
    for name, example, good in training:
        workers[name].feedback(good, example)

    # 4. After tuning, the worker correctly tags the same task.
    after = workers["refund"].run("i want my money back for this order")
    print(f"  refund worker AFTER tuning  -> '{after}' (score {workers['refund'].score:.2f})")

    print("\nThis is the pattern, not the product: assemble -> tune -> improve.")
    print("The real workers are agents + fine-tuned models (kept private).")


if __name__ == "__main__":
    main()
