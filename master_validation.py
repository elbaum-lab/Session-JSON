#!/usr/bin/env python3
#
# Purpose: To validate consistency in new versions of master.json


import json
import sys
from pathlib import Path


PRIMITIVE_TYPES = {
    "string",
    "integer",
    "float",
    "boolean"
}


class ValidationError(Exception):
    pass


def load_json(filename):
    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_schema(schema):

    errors = []
    warnings = []

    # ----------------------------------------------------------
    # Basic structure
    # ----------------------------------------------------------

    if "root" not in schema:
        errors.append("Missing top-level key: root")

    if "branches" not in schema:
        errors.append("Missing top-level key: branches")

    if errors:
        return errors, warnings

    branches = schema["branches"]

    if not isinstance(branches, dict):
        errors.append("'branches' must be a dictionary")
        return errors, warnings

    # ----------------------------------------------------------
    # Validate each branch
    # ----------------------------------------------------------

    for name, branch in branches.items():

        if not isinstance(branch, dict):
            errors.append(f"Branch '{name}' is not a dictionary")
            continue

        node_type = branch.get("type")

        if node_type is None:
            errors.append(f"Branch '{name}' missing 'type'")
            continue

        # ------------------------------------------------------
        # Primitive
        # ------------------------------------------------------

        if node_type in PRIMITIVE_TYPES:

            if "children" in branch:
                errors.append(
                    f"Primitive branch '{name}' "
                    f"should not contain 'children'"
                )

            if "choices" in branch:
                errors.append(
                    f"Primitive branch '{name}' "
                    f"should not contain 'choices'"
                )

        # ------------------------------------------------------
        # Button
        # ------------------------------------------------------

        elif node_type == "button":

            children = branch.get("children")

            if not isinstance(children, list):
                errors.append(
                    f"Button branch '{name}' "
                    f"must contain a children list"
                )
                continue

            for child in children:
                if child not in branches:
                    errors.append(
                        f"Branch '{name}' references "
                        f"missing child '{child}'"
                    )

        # ------------------------------------------------------
        # Dropdown
        # ------------------------------------------------------

        elif node_type == "dropdown":

            choices = branch.get("choices")

            if not isinstance(choices, list):
                errors.append(
                    f"Dropdown '{name}' must contain a choices list"
                )
                continue

            opens = branch.get("opens", {})

            if not isinstance(opens, dict):
                errors.append(
                    f"Dropdown '{name}' opens field must be a dictionary"
                )
                continue

            for choice, target in opens.items():

                if choice not in choices:
                    warnings.append(
                        f"Dropdown '{name}' has opens entry "
                        f"for non-choice '{choice}'"
                    )

                if target is not None and target not in branches:
                    errors.append(
                        f"Dropdown '{name}' opens "
                        f"missing branch '{target}'"
                    )

        else:
            errors.append(
                f"Branch '{name}' has unknown type '{node_type}'"
            )

    # ----------------------------------------------------------
    # Validate root
    # ----------------------------------------------------------

    root = schema["root"]

    if not isinstance(root, dict):
        errors.append("'root' must be a dictionary")
        return errors, warnings

    root_children = root.get("children", [])

    if not isinstance(root_children, list):
        errors.append("root.children must be a list")

    for child in root_children:
        if child not in branches:
            errors.append(
                f"Root references missing branch '{child}'"
            )

    # ----------------------------------------------------------
    # Graph creation
    # ----------------------------------------------------------

    graph = {}

    for name in branches:
        graph[name] = []

    for name, branch in branches.items():

        node_type = branch["type"]

        if node_type == "button":
            graph[name].extend(branch.get("children", []))

        elif node_type == "dropdown":

            for target in branch.get("opens", {}).values():
                if target is not None:
                    graph[name].append(target)

    # root node
    graph["__ROOT__"] = list(root_children)

    # ----------------------------------------------------------
    # Cycle detection
    # ----------------------------------------------------------

    visited = set()
    stack = set()

    def dfs_cycle(node):

        visited.add(node)
        stack.add(node)

        for nxt in graph.get(node, []):

            if nxt not in visited:
                if dfs_cycle(nxt):
                    return True

            elif nxt in stack:
                return True

        stack.remove(node)
        return False

    if dfs_cycle("__ROOT__"):
        errors.append("Cycle detected in schema")

    # ----------------------------------------------------------
    # Reachability analysis
    # ----------------------------------------------------------

    reachable = set()

    def dfs_reachable(node):

        if node in reachable:
            return

        reachable.add(node)

        for nxt in graph.get(node, []):
            dfs_reachable(nxt)

    dfs_reachable("__ROOT__")

    for branch_name in branches:

        if branch_name not in reachable:
            warnings.append(
                f"Branch '{branch_name}' is unreachable"
            )

    # ----------------------------------------------------------
    # Label checks
    # ----------------------------------------------------------

    labels = {}

    for name, branch in branches.items():

        label = branch.get("label")

        if label:

            if label in labels:
                warnings.append(
                    f"Duplicate label '{label}' "
                    f"used by '{labels[label]}' and '{name}'"
                )

            labels[label] = name

    return errors, warnings


def main():

    if len(sys.argv) != 2:
        print("Usage:")
        print("    python validate_master.py master.json")
        sys.exit(1)

    filename = Path(sys.argv[1])

    try:
        schema = load_json(filename)

        errors, warnings = validate_schema(schema)

        print("\nVALIDATION REPORT")
        print("=" * 60)

        if warnings:
            print("\nWarnings:")
            for w in warnings:
                print(f"  [WARNING] {w}")

        if errors:
            print("\nErrors:")
            for e in errors:
                print(f"  [ERROR] {e}")

            print("\nSchema is INVALID")
            sys.exit(2)

        print("\nSchema is VALID")

    except ValidationError as e:
        print(f"Validation error: {e}")
        sys.exit(2)

    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(3)


if __name__ == "__main__":
    main()