"""Random deity names for sub-agent display labels."""

from __future__ import annotations

import random

DEITY_NAMES: tuple[str, ...] = (
    "Apollo",
    "Artemis",
    "Athena",
    "Demeter",
    "Dionysus",
    "Hephaestus",
    "Hera",
    "Hermes",
    "Persephone",
    "Poseidon",
    "Ares",
    "Aphrodite",
    "Hestia",
    "Selene",
    "Eos",
    "Nike",
    "Iris",
    "Helios",
    "Pan",
    "Tyche",
    "Nemesis",
    "Hecate",
    "Morpheus",
    "Triton",
    "Calliope",
    "Thalia",
    "Clio",
    "Erato",
    "Maia",
    "Rhea",
)


def pick_deity_name() -> str:
    """Return a random Greek deity name for use as a sub-agent label."""
    return random.choice(DEITY_NAMES)
