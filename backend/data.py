"""Bounded input parsing and explicit, deliberately limited PII screening."""

import csv
import hashlib
import io
import json
import re

PATTERNS = {
    "email address": re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
    "US social security number": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "phone number": re.compile(
        r"(?<!\d)(?:\+1[ .-]?)?(?:\(\d{3}\)|\d{3})[ .-]\d{3}[ .-]\d{4}(?!\d)"
    ),
}


def parse_dataset(content: bytes, filename: str):
    if len(content) > 2 * 1024 * 1024:
        raise ValueError("Use a file smaller than 2 MB.")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError("Save your dataset as UTF-8 text.") from None
    try:
        if filename.lower().endswith(".csv"):
            raw = list(csv.DictReader(io.StringIO(text)))
        elif filename.lower().endswith(".jsonl"):
            raw = [json.loads(line) for line in text.splitlines() if line.strip()]
        else:
            raise ValueError(
                "Choose a .jsonl or .csv file with instruction and response fields."
            )
    except (json.JSONDecodeError, csv.Error, RecursionError):
        raise ValueError(
            "The file could not be parsed. Check the JSONL or CSV format."
        ) from None
    if not 6 <= len(raw) <= 500:
        raise ValueError("Include 6 to 500 examples for this local experiment.")
    clean, seen = [], set()
    for i, row in enumerate(raw, 1):
        if not isinstance(row, dict):
            raise ValueError(
                f"Row {i} must be an object with instruction and response fields."
            )
        instruction, response = row.get("instruction"), row.get("response")
        if (
            not isinstance(instruction, str)
            or not isinstance(response, str)
            or not instruction.strip()
            or not response.strip()
        ):
            raise ValueError(f"Row {i} needs a nonempty instruction and response.")
        instruction, response = instruction.strip(), response.strip()
        if len(instruction) > 1500 or len(response) > 1500:
            raise ValueError(
                f"Row {i} exceeds 1,500 characters per field. Shorten it for the local model."
            )
        for name, pattern in PATTERNS.items():
            if pattern.search(instruction + " " + response):
                raise ValueError(
                    f"Possible {name} in row {i}. Remove personal data and upload again. This screening cannot detect all sensitive information."
                )
        # Keep an identical question entirely out of the other split, even with a different answer.
        key = " ".join(instruction.casefold().split())
        if key not in seen:
            seen.add(key)
            clean.append({"instruction": instruction, "response": response})
    if len(clean) < 6:
        raise ValueError(
            "At least 6 unique instructions are needed after deduplication."
        )
    return clean


def split_dataset(rows):
    ordered = sorted(
        rows,
        key=lambda r: hashlib.sha256(r["instruction"].casefold().encode()).hexdigest(),
    )
    count = max(2, round(len(ordered) * 0.2))
    return ordered[count:], ordered[:count]


def sample_rows(school):
    topics = {
        "uga": [
            (
                "photosynthesis",
                "Plants use light energy to convert water and carbon dioxide into sugars and oxygen.",
            ),
            (
                "evaporation",
                "Liquid water becomes water vapor when molecules gain enough energy.",
            ),
            ("gravity", "Gravity is an attractive force between objects with mass."),
            (
                "ecosystems",
                "Organisms interact with each other and their physical environment.",
            ),
            ("friction", "Friction opposes motion between surfaces in contact."),
            (
                "conservation of matter",
                "Atoms are rearranged in a chemical reaction, but they are not created or destroyed.",
            ),
            ("density", "Density is mass divided by volume."),
            (
                "food webs",
                "A food web shows how energy passes through interconnected feeding relationships.",
            ),
        ],
        "gatech": [
            (
                "bridge design",
                "Compare load, span, material strength, and constraints before selecting a design.",
            ),
            (
                "circuits",
                "A closed circuit provides a continuous path for electrical current.",
            ),
            (
                "prototypes",
                "Build a small testable version, collect observations, and revise the design.",
            ),
            (
                "insulation",
                "Compare temperature change while keeping container size and starting temperature fixed.",
            ),
            (
                "water filters",
                "Compare the clarity of filtered samples while controlling initial water conditions.",
            ),
            (
                "simple machines",
                "A lever trades force for distance and pivots around a fulcrum.",
            ),
            (
                "renewable energy",
                "Compare the energy source, reliability, and environmental impacts.",
            ),
            (
                "thermal expansion",
                "Most materials expand when heated because particles move farther apart.",
            ),
        ],
        "emory": [
            (
                "experimental controls",
                "Keep other variables constant so a change can be linked to the independent variable.",
            ),
            (
                "correlation",
                "Two variables changing together does not establish that one causes the other.",
            ),
            (
                "sample size",
                "More representative observations can reduce random error in an estimate.",
            ),
            (
                "bias",
                "Look for systematic differences in how observations were selected or measured.",
            ),
            (
                "replication",
                "Repeating a study tests whether its results hold under similar conditions.",
            ),
            (
                "uncertainty",
                "Report limitations and plausible alternative explanations alongside the claim.",
            ),
            (
                "measurement",
                "Use consistent units and calibrated instruments to make observations comparable.",
            ),
            (
                "evidence quality",
                "Prefer relevant observations with a clear method and transparent limitations.",
            ),
        ],
    }
    output = []
    for topic, fact in topics[school]:
        output += [
            {
                "instruction": f"Help a student explain {topic} using evidence.",
                "response": f"Start with this idea: {fact} What observation supports it? Connect that evidence to your claim.",
            },
            {
                "instruction": f"Suggest a classroom discussion question about {topic}.",
                "response": f"Ask: what evidence would help us investigate {topic}? {fact} Invite learners to compare explanations.",
            },
            {
                "instruction": f"Give constructive feedback on an unsupported claim about {topic}.",
                "response": f"You have a starting claim. Add a specific observation and explain why it supports your reasoning. Remember: {fact}",
            },
        ]
    return output
