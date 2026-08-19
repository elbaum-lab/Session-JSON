#!/usr/bin/env python3
"""
Session-JSON
A GUI for generating metadata-entry JSON files documenting microscopy STEM sessions.

Requirements:
    Python 3.11 or newer. No third-party packages are required.

Run:
    python metadata_gui.py master.json
    
Designed by: Shahar Seifer, Elbaum lab, Weizmann Institute of Science (2026)
Assisted by: M365 coPilot
License: GPL-v3    
"""

import argparse
import copy
import json
import traceback
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path


PRIMITIVE_TYPES = {"string", "integer", "float", "boolean"}
ANGLE_SCHEMES = {"dose_symmetric", "even_step_angle_scheme"}
ARBITRARY_SCHEME = "arbitrary_angle_scheme"
TILT_SETTINGS_BRANCH = "single_tilt_series_settings"
ADDITIONAL_SCAN_BRANCH = "additional_scan"
NUMBER_OF_ADDITIONAL_SCANS = "number_of_additional_scans_per_tilt"
NUMBER_OF_ADDITIONAL_SCANS_ALIASES = (
    "number_of_additional_scan_per_tilt",
    "number_of_additional_scans_per_tilt",
)
ANGLE_REPETITION_FACTOR = "angle_repetition_factor"


class MetadataGUI:
    def __init__(self, master_file):
        self.master_file = Path(master_file)
        self.schema = self.load_json(self.master_file)
        self.branches = self.schema["branches"]
        self.root_schema = self.schema["root"]

        self.metadata = {}
        self.tk_vars = {}
        self.open_windows = {}

        self.self_dropdown_paths = set()
        self.additional_scan_index_vars = {}
        self.additional_scan_index_combos = {}
        
        self.root = tk.Tk()
        self.root.title("Session-JSON")
        self.root.geometry("650x550")
        self.root.protocol("WM_DELETE_WINDOW", self.on_root_close)
        self.build_root_window()

    # ------------------------------------------------------------
    # Basic utilities
    # ------------------------------------------------------------

    def load_json(self, filename):
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_json(self, filename, data):
        filename = Path(filename)
        filename.parent.mkdir(parents=True, exist_ok=True)
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def run(self):
        self.root.mainloop()

    # ------------------------------------------------------------
    # Window construction
    # ------------------------------------------------------------

    def build_root_window(self):
        frame = ttk.Frame(self.root, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            frame,
            text="Microscopy Metadata",
            font=("TkDefaultFont", 16, "bold")
        ).pack(anchor="w", pady=(0, 12))

        control_frame = ttk.Frame(frame)
        control_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Button(control_frame, text="Load", command=lambda: self.load_into_branch(())).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(control_frame, text="Save now", command=self.save_current_metadata).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(control_frame, text="Show metadata", command=self.show_metadata_preview).pack(side=tk.LEFT, padx=(0, 5))

        ttk.Separator(frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=8)

        fields_frame = ttk.Frame(frame)
        fields_frame.pack(fill=tk.BOTH, expand=True)

        for child_name in self.root_schema.get("children", []):
            self.add_field_or_button(fields_frame, child_name, self.metadata, (child_name,))

    def build_branch_window(self, window, branch_name, metadata_node, path):
        branch_schema = self.branches[branch_name]

        container = ttk.Frame(window, padding=12)
        container.pack(fill=tk.BOTH, expand=True)

        title = branch_schema.get("label", branch_name)
        ttk.Label(container, text=title, font=("TkDefaultFont", 15, "bold")).pack(anchor="w", pady=(0, 12))

        control_frame = ttk.Frame(container)
        control_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Button(control_frame, text="Load", command=lambda: self.load_into_branch(path)).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(control_frame, text="Save now", command=self.save_current_metadata).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(control_frame, text="Show metadata", command=self.show_metadata_preview).pack(side=tk.LEFT, padx=(0, 5))

        ttk.Separator(container, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=8)

        fields_frame = ttk.Frame(container)
        fields_frame.pack(fill=tk.BOTH, expand=True)

        # If the opened branch itself is a dropdown, display that dropdown directly.
        if branch_schema.get("type") == "dropdown":
            self.add_self_dropdown_field(fields_frame, branch_name, metadata_node, path)
            return

        for child_name in branch_schema.get("children", []):
            self.add_field_or_button(fields_frame, child_name, metadata_node, path + (child_name,))

    def add_self_dropdown_field(self, parent, branch_name, metadata_node, path):
        """
        Display a dropdown branch that was opened as its own window.

        """
        branch = self.branches[branch_name]
        label = branch.get("label", branch_name)

        metadata_node.setdefault("selected", branch.get("default", ""))
        metadata_node.setdefault("data", {})

        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=4)

        ttk.Label(row, text=label, width=30).pack(side=tk.LEFT)

        var = tk.StringVar()
        var.set(metadata_node.get("selected", ""))
        self.tk_vars[path] = var
        self.self_dropdown_paths.add(path)

        combo = ttk.Combobox(
            row,
            textvariable=var,
            values=branch.get("choices", []),
            state="readonly",
            width=28
        )
        combo.pack(side=tk.LEFT, padx=5)
        combo.bind(
            "<<ComboboxSelected>>",
            lambda event, bn=branch_name, p=path: self.on_self_dropdown_selected(bn, p)
        )

        # Settings button for standalone dropdown branches.
        if branch.get("opens"):
            ttk.Button(
                row,
                text="Settings",
                command=lambda bn=branch_name, p=path: self.open_dropdown_settings(bn, p)
            ).pack(side=tk.LEFT, padx=5)

    def add_field_or_button(self, parent, branch_name, metadata_node, path):
        if branch_name not in self.branches:
            raise KeyError(f"Branch '{branch_name}' does not exist in schema['branches'].")

        branch = self.branches[branch_name]
        node_type = branch["type"]
        label = branch.get("label", branch_name)

        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=4)

        if node_type == "button":
            if branch_name == ADDITIONAL_SCAN_BRANCH:
                # Special case: Additional scan [index selector] [Settings].
                # Slots are stored as metadata_node["additional_scan"]["1"], ["2"], ...
                row.destroy()
                self.add_additional_scan_selector(parent, branch_name, metadata_node, path)
                return

            metadata_node.setdefault(branch_name, {})
            ttk.Button(row, text=label, command=lambda: self.open_branch_window(branch_name, path)).pack(anchor="w")

        elif node_type == "dropdown":
            ttk.Label(row, text=label, width=30).pack(side=tk.LEFT)
            metadata_node.setdefault(branch_name, {"selected": branch.get("default", ""), "data": {}})

            var = tk.StringVar()
            var.set(metadata_node[branch_name].get("selected", ""))
            self.tk_vars[path] = var

            combo = ttk.Combobox(
                row,
                textvariable=var,
                values=branch.get("choices", []),
                state="readonly",
                width=28
            )
            combo.pack(side=tk.LEFT, padx=5)
            combo.bind(
                "<<ComboboxSelected>>",
                lambda event, bn=branch_name, p=path: self.on_dropdown_selected(bn, p)
            )

            # Settings button for normal dropdown branches.
            if branch.get("opens"):
                ttk.Button(
                    row,
                    text="Settings",
                    command=lambda bn=branch_name, p=path: self.open_dropdown_settings(bn, p)
                ).pack(side=tk.LEFT, padx=5)

        elif node_type in PRIMITIVE_TYPES:
            ttk.Label(row, text=label, width=30).pack(side=tk.LEFT)
            default = branch.get("default", "")
            value = metadata_node.get(branch_name, default)
            if value is None:
                value = ""

            if node_type == "boolean":
                var = tk.BooleanVar()
                var.set(bool(value))
                self.tk_vars[path] = var
                ttk.Checkbutton(row, variable=var, command=lambda p=path: self.update_value_from_widget(p)).pack(side=tk.LEFT)
            else:
                var = tk.StringVar()
                var.set(str(value))
                self.tk_vars[path] = var
                entry = ttk.Entry(row, textvariable=var, width=45)
                entry.pack(side=tk.LEFT, padx=5)
                entry.bind("<FocusOut>", lambda event, p=path: self.update_value_from_widget(p))
                entry.bind("<Return>", lambda event, p=path: self.update_value_from_widget(p))

            unit = branch.get("unit")
            if unit:
                ttk.Label(row, text=unit).pack(side=tk.LEFT, padx=5)

        else:
            raise ValueError(f"Unsupported branch type '{node_type}' in branch '{branch_name}'.")


    # ------------------------------------------------------------
    # Additional scan selector
    # ------------------------------------------------------------

    def add_additional_scan_selector(self, parent, branch_name, metadata_node, path):
        """Draw Additional scan [index selector] [Settings]."""
        branch = self.branches[branch_name]
        label = branch.get("label", branch_name)

        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=4)

        #ttk.Label(row, text=label, width=16).pack(side=tk.LEFT)
        ttk.Label(row, text=label).pack(side=tk.LEFT, padx=(0, 8))
        
        choices = self.get_additional_scan_index_choices()
        var = tk.StringVar()
        var.set(choices[0] if choices else "")

        combo = ttk.Combobox(row, textvariable=var, values=choices, state="readonly", width=5)
        combo.pack(side=tk.LEFT, padx=5)

        self.additional_scan_index_vars[path] = var
        self.additional_scan_index_combos[path] = combo

        combo.bind(
            "<<ComboboxSelected>>",
            lambda event, mn=metadata_node, p=path: self.open_selected_additional_scan(mn, p)
        )

        ttk.Button(
            row,
            text="Settings",
            command=lambda mn=metadata_node, p=path: self.open_selected_additional_scan(mn, p)
        ).pack(side=tk.LEFT, padx=5)

    def get_additional_scan_count(self):
        """Read number_of_additional_scans_per_tilt from metadata without updating widgets."""
        value = 0
        for key in NUMBER_OF_ADDITIONAL_SCANS_ALIASES:
            if key in self.metadata:
                value = self.metadata.get(key, 0)
                break

        try:
            count = int(round(float(value)))
        except Exception:
            count = 0

        count = max(count, 0)
        self.metadata[NUMBER_OF_ADDITIONAL_SCANS] = count
        return count

    def get_additional_scan_index_choices(self):
        return [str(i) for i in range(1, self.get_additional_scan_count() + 1)]

    def refresh_additional_scan_selector_choices(self, path):
        """
        Refresh one visible additional-scan index selector.

        This function is defensive because the selector may belong to a Toplevel
        window that is currently being closed or has already been destroyed.
        """
        choices = self.get_additional_scan_index_choices()

        if not hasattr(self, "additional_scan_index_combos"):
            self.additional_scan_index_combos = {}
        if not hasattr(self, "additional_scan_index_vars"):
            self.additional_scan_index_vars = {}

        combo = self.additional_scan_index_combos.get(path)
        var = self.additional_scan_index_vars.get(path)

        if combo is not None:
            try:
                if not combo.winfo_exists():
                    self.additional_scan_index_combos.pop(path, None)
                    self.additional_scan_index_vars.pop(path, None)
                    return choices
                combo.configure(values=choices)
            except tk.TclError:
                self.additional_scan_index_combos.pop(path, None)
                self.additional_scan_index_vars.pop(path, None)
                return choices

        if var is not None:
            if not choices:
                var.set("")
            elif var.get() not in choices:
                var.set(choices[0])

        return choices

    def refresh_all_additional_scan_selectors(self):
        """
        Refresh all visible additional-scan index selectors.

        Safe when no selectors exist and safe when a selector's window has
        already been destroyed.
        """
        if not hasattr(self, "additional_scan_index_combos"):
            self.additional_scan_index_combos = {}
        if not hasattr(self, "additional_scan_index_vars"):
            self.additional_scan_index_vars = {}

        for path in list(self.additional_scan_index_combos.keys()):
            self.refresh_additional_scan_selector_choices(path)

    def ensure_additional_scan_slots(self, metadata_node):
        """Ensure metadata_node['additional_scan'] contains slots 1..N."""
        count = self.get_additional_scan_count()
        scans = metadata_node.setdefault(ADDITIONAL_SCAN_BRANCH, {})

        if not isinstance(scans, dict):
            scans = {}
            metadata_node[ADDITIONAL_SCAN_BRANCH] = scans

        wanted = {str(i) for i in range(1, count + 1)}

        for idx in wanted:
            scans.setdefault(idx, {})

        for idx in list(scans.keys()):
            if idx not in wanted:
                del scans[idx]

        return scans

    def update_all_additional_scan_containers(self):
        """Update all additional_scan containers according to the requested count."""
        def walk(obj):
            if isinstance(obj, dict):
                if "main_scan" in obj or ADDITIONAL_SCAN_BRANCH in obj:
                    self.ensure_additional_scan_slots(obj)
                for value in obj.values():
                    walk(value)
            elif isinstance(obj, list):
                for item in obj:
                    walk(item)

        walk(self.metadata)
        self.refresh_all_additional_scan_selectors()

    def open_selected_additional_scan(self, metadata_node, path):
        """Open selected additional_scan slot, initializing it from main_scan if empty."""
        # First push current GUI values into metadata so main_scan and the count are current.
        self.update_all_widgets_to_metadata()
        choices = self.refresh_additional_scan_selector_choices(path)

        if not choices:
            metadata_node[ADDITIONAL_SCAN_BRANCH] = {}
            messagebox.showwarning(
                "No additional scans",
                "number_of_additional_scans_per_tilt is 0.\n\n"
                "Increase this value before editing additional scans."
            )
            return

        var = self.additional_scan_index_vars.get(path)
        if var is None:
            return

        selected_index = var.get()
        if selected_index not in choices:
            selected_index = choices[0]
            var.set(selected_index)

        scans = self.ensure_additional_scan_slots(metadata_node)
        slot = scans.setdefault(selected_index, {})

        if not slot:
            main_scan = metadata_node.get("main_scan")
            if not isinstance(main_scan, dict):
                main_scan = self.find_best_main_scan_template()

            if isinstance(main_scan, dict):
                slot.update(copy.deepcopy(main_scan))


        window_path = path + (selected_index,)
        self.open_additional_scan_window(selected_index, slot, window_path)

    def open_additional_scan_window(self, selected_index, slot_node, path):
        key = path
        if key in self.open_windows:
            try:
                self.open_windows[key].lift()
                return
            except tk.TclError:
                del self.open_windows[key]

        window = tk.Toplevel(self.root)
        window.title(f"Additional scan #{selected_index}")
        window.geometry("650x550")
        self.open_windows[key] = window
        window.protocol("WM_DELETE_WINDOW", lambda w=window, k=key: self.on_subwindow_close(w, k))

        self.build_branch_window(
            window=window,
            branch_name=ADDITIONAL_SCAN_BRANCH,
            metadata_node=slot_node,
            path=path
        )

    def find_best_main_scan_template(self):
        """Return the most populated main_scan found in metadata."""
        candidates = [node for node in self.find_all_key_values_recursive(self.metadata, "main_scan") if isinstance(node, dict)]
        if not candidates:
            return {}
        return max(candidates, key=self.count_json_leaf_values)

    def count_json_leaf_values(self, obj):
        if isinstance(obj, dict):
            return sum(self.count_json_leaf_values(v) for v in obj.values())
        if isinstance(obj, list):
            return sum(self.count_json_leaf_values(v) for v in obj)
        if obj is None or obj == "":
            return 0
        return 1

    def open_branch_window(self, branch_name, path):
        key = path
        if key in self.open_windows:
            try:
                self.open_windows[key].lift()
                return
            except tk.TclError:
                del self.open_windows[key]

        metadata_node = self.get_metadata_node_for_path(path, create=True)

        window = tk.Toplevel(self.root)
        window.title(self.branches[branch_name].get("label", branch_name))
        window.geometry("650x550")
        self.open_windows[key] = window
        window.protocol("WM_DELETE_WINDOW", lambda w=window, k=key: self.on_subwindow_close(w, k))

        self.build_branch_window(window, branch_name, metadata_node, path)

    def open_dropdown_settings(self, branch_name, path):
        if path not in self.tk_vars:
            return

        branch = self.branches[branch_name]
        selected = self.tk_vars[path].get()
        target_branch = branch.get("opens", {}).get(selected)

        if target_branch is None:
            return

        self.open_branch_window(target_branch, path + (target_branch,))

    def on_dropdown_selected(self, branch_name, path):
        self.update_value_from_widget(path)

        branch = self.branches[branch_name]
        selected = self.tk_vars[path].get()
        parent_node = self.get_parent_metadata_node(path, create=True)

        parent_node.setdefault(branch_name, {"selected": selected, "data": {}})
        parent_node[branch_name]["selected"] = selected
        parent_node[branch_name].setdefault("data", {})

        target_branch = branch.get("opens", {}).get(selected)
        if target_branch is not None:
            self.open_branch_window(target_branch, path + (target_branch,))

    def on_self_dropdown_selected(self, branch_name, path):
        branch = self.branches[branch_name]
        selected = self.tk_vars[path].get()

        dropdown_node = self.get_metadata_node_for_path(path, create=True)
        dropdown_node["selected"] = selected
        dropdown_node.setdefault("data", {})

        target_branch = branch.get("opens", {}).get(selected)
        if target_branch is not None:
            self.open_branch_window(target_branch, path + (target_branch,))

    def cleanup_additional_scan_selectors_for_closed_path(self, closed_path):
        """Remove selector widget references that were inside a closed window."""
        if not hasattr(self, "additional_scan_index_combos"):
            self.additional_scan_index_combos = {}
        if not hasattr(self, "additional_scan_index_vars"):
            self.additional_scan_index_vars = {}

        for path in list(self.additional_scan_index_combos.keys()):
            remove = False
            if len(path) >= len(closed_path) and path[:len(closed_path)] == closed_path:
                remove = True
            else:
                combo = self.additional_scan_index_combos.get(path)
                try:
                    if combo is None or not combo.winfo_exists():
                        remove = True
                except tk.TclError:
                    remove = True

            if remove:
                self.additional_scan_index_combos.pop(path, None)
                self.additional_scan_index_vars.pop(path, None)

    def on_subwindow_close(self, window, key):
        try:
            self.save_current_metadata(show_message=False)
        finally:
            self.cleanup_additional_scan_selectors_for_closed_path(key)
            self.open_windows.pop(key, None)
            window.destroy()

    def on_root_close(self):
        # Keep the current behavior: close windows without forcing a root save.
        for window in list(self.open_windows.values()):
            try:
                window.destroy()
            except Exception:
                pass
        self.open_windows.clear()
        self.root.destroy()

    # ------------------------------------------------------------
    # Metadata path utilities
    # ------------------------------------------------------------

    def get_parent_metadata_node(self, path, create=False):
        if len(path) == 0:
            return self.metadata
        return self.get_metadata_node_for_path(path[:-1], create=create)

    def get_metadata_node_for_path(self, path, create=False):
        node = self.metadata
        i = 0

        while i < len(path):
            # If the already-consumed prefix is a standalone dropdown path,
            # the next path component is a target branch stored under node["data"].
            if tuple(path[:i]) in self.self_dropdown_paths and i < len(path):
                target_branch = path[i]
                if create:
                    node.setdefault("data", {})
                    node["data"].setdefault(target_branch, {})
                node = node["data"][target_branch]
                i += 1
                continue

            name = path[i]

            # Support pseudo-path pieces used for indexed additional_scan slots,
            # e.g. additional_scan -> "1" -> scan_mode.
            if name not in self.branches:
                if create:
                    node.setdefault(name, {})
                    node = node[name]
                    i += 1
                    continue
                node = node[name]
                i += 1
                continue

            branch = self.branches[name]
            node_type = branch["type"]

            if node_type == "dropdown":
                if create:
                    node.setdefault(name, {"selected": branch.get("default", ""), "data": {}})
                node = node[name]

                if i + 1 < len(path):
                    target_branch = path[i + 1]
                    if create:
                        node.setdefault("data", {})
                        node["data"].setdefault(target_branch, {})
                    node = node["data"][target_branch]
                    i += 2
                else:
                    return node

            elif node_type == "button":
                if create:
                    node.setdefault(name, {})
                node = node[name]
                i += 1

            elif node_type in PRIMITIVE_TYPES:
                if create:
                    node.setdefault(name, branch.get("default"))
                node = node[name]
                i += 1

            else:
                raise ValueError(f"Unknown node type: {node_type}")

        return node

    # ------------------------------------------------------------
    # Value updating
    # ------------------------------------------------------------

    def update_value_from_widget(self, path):
        if path not in self.tk_vars:
            return

        # Standalone dropdown branch: store selected/data directly in that node.
        if path in self.self_dropdown_paths:
            selected = self.tk_vars[path].get()
            dropdown_node = self.get_metadata_node_for_path(path, create=True)
            dropdown_node["selected"] = selected
            dropdown_node.setdefault("data", {})
            return

        branch_name = path[-1]
        branch = self.branches[branch_name]
        node_type = branch["type"]
        var = self.tk_vars[path]
        parent_node = self.get_parent_metadata_node(path, create=True)

        if node_type == "dropdown":
            selected = var.get()
            parent_node.setdefault(branch_name, {"selected": selected, "data": {}})
            parent_node[branch_name]["selected"] = selected
            parent_node[branch_name].setdefault("data", {})

        elif node_type in PRIMITIVE_TYPES:
            raw = var.get()
            try:
                parent_node[branch_name] = self.cast_value(raw, node_type)
                if branch_name in NUMBER_OF_ADDITIONAL_SCANS_ALIASES:
                    self.refresh_all_additional_scan_selectors()
            except ValueError as e:
                messagebox.showerror("Invalid value", f"Invalid value for '{branch_name}':\n{e}")

    def update_all_widgets_to_metadata(self):
        for path in list(self.tk_vars.keys()):
            self.update_value_from_widget(path)

    def cast_value(self, value, node_type):
        if node_type == "string":
            return str(value)
        if node_type == "integer":
            if value == "":
                return None
            return int(value)
        if node_type == "float":
            if value == "":
                return None
            return float(value)
        if node_type == "boolean":
            return bool(value)
        return value

    # ------------------------------------------------------------
    # Angle generation and duplication flags
    # ------------------------------------------------------------

    def add_derived_tilt_angles(self):
        """
        Generate a new base tilt_angles_deg only if a generating scheme is active.
        Arbitrary mode preserves manual edits.
        """
        selected_scheme = self.find_selected_tilt_scheme_recursive(self.metadata)

        if selected_scheme == ARBITRARY_SCHEME:
            if "tilt_angles_deg" not in self.metadata:
                self.metadata["tilt_angles_deg"] = []
                self.metadata["angles_duplicated"] = False
            return

        dose_nodes = self.find_all_key_values_recursive(self.metadata, "dose_symmetric")
        even_nodes = self.find_all_key_values_recursive(self.metadata, "even_step_angle_scheme")

        angles = None

        if selected_scheme == "dose_symmetric":
            for node in dose_nodes:
                if isinstance(node, dict):
                    angles = self.generate_dose_symmetric_angles(node)
                    if angles is not None:
                        break

        elif selected_scheme == "even_step_angle_scheme":
            for node in even_nodes:
                if isinstance(node, dict):
                    angles = self.generate_even_step_angles(node)
                    if angles is not None:
                        break

        if angles is None:
            for node in dose_nodes:
                if isinstance(node, dict):
                    angles = self.generate_dose_symmetric_angles(node)
                    if angles is not None:
                        break

        if angles is None:
            for node in even_nodes:
                if isinstance(node, dict):
                    angles = self.generate_even_step_angles(node)
                    if angles is not None:
                        break

        if angles is not None:
            self.metadata["tilt_angles_deg"] = angles
            self.metadata["angles_duplicated"] = False
            self.metadata[ANGLE_REPETITION_FACTOR] = 1
            self.convert_single_tilt_to_arbitrary_scheme(self.metadata)
            self.force_arbitrary_tilt_gui_state()
        else:
            if "tilt_angles_deg" not in self.metadata:
                self.metadata["tilt_angles_deg"] = []
                self.metadata["angles_duplicated"] = False

    def duplicate_angles_once_if_requested(self):
        """
        Apply number_of_additional_scans_per_tilt to tilt_angles_deg.

        If N additional scans are requested, each tilt angle appears 1 + N times.
        angle_repetition_factor tracks the current expansion so repeated saves
        do not multiply the list repeatedly.
        """
        n_additional = self.get_additional_scan_count()
        desired_factor = 1 + n_additional

        angles = self.metadata.get("tilt_angles_deg", None)
        if not isinstance(angles, list):
            return

        try:
            old_factor = int(self.metadata.get(ANGLE_REPETITION_FACTOR, 1))
        except Exception:
            old_factor = 1
        if old_factor < 1:
            old_factor = 1

        angles_duplicated = self.as_bool(
            self.metadata.get("angles_duplicated", False),
            default=False
        )

        if angles_duplicated and old_factor > 1:
            base_angles = angles[::old_factor]
        else:
            base_angles = list(angles)

        if desired_factor <= 1:
            self.metadata["tilt_angles_deg"] = base_angles
            self.metadata["angles_duplicated"] = False
            self.metadata[ANGLE_REPETITION_FACTOR] = 1
            return

        if angles_duplicated and old_factor == desired_factor:
            return

        repeated = []
        for angle in base_angles:
            repeated.extend([angle] * desired_factor)

        self.metadata["tilt_angles_deg"] = repeated
        self.metadata["angles_duplicated"] = True
        self.metadata[ANGLE_REPETITION_FACTOR] = desired_factor

    def convert_single_tilt_to_arbitrary_scheme(self, obj):
        """
        Convert the tilt-settings dropdown node to arbitrary/manual mode.
        """
        if isinstance(obj, dict):
            for key, value in list(obj.items()):
                if key == TILT_SETTINGS_BRANCH and isinstance(value, dict):
                    value["selected"] = ARBITRARY_SCHEME
                    value["data"] = {}
                else:
                    self.convert_single_tilt_to_arbitrary_scheme(value)
        elif isinstance(obj, list):
            for item in obj:
                self.convert_single_tilt_to_arbitrary_scheme(item)

    def force_arbitrary_tilt_gui_state(self):
        """
        Update visible GUI state after automatic angle generation.
        """
        scheme_branch_names = set(ANGLE_SCHEMES)

        for path, var in list(self.tk_vars.items()):
            if len(path) > 0 and path[-1] == TILT_SETTINGS_BRANCH:
                try:
                    var.set(ARBITRARY_SCHEME)
                except Exception:
                    pass

        for path in list(self.tk_vars.keys()):
            if any(part in scheme_branch_names for part in path):
                self.tk_vars.pop(path, None)
                self.self_dropdown_paths.discard(path)

        for key, window in list(self.open_windows.items()):
            if any(part in scheme_branch_names for part in key):
                try:
                    window.destroy()
                except Exception:
                    pass
                self.open_windows.pop(key, None)

    def find_all_key_values_recursive(self, obj, target_key):
        matches = []

        def walk(x):
            if isinstance(x, dict):
                for key, value in x.items():
                    if key == target_key:
                        matches.append(value)
                    walk(value)
            elif isinstance(x, list):
                for item in x:
                    walk(item)

        walk(obj)
        return matches

    def find_selected_tilt_scheme_recursive(self, obj):
        if isinstance(obj, dict):
            selected = obj.get("selected")
            if selected in ANGLE_SCHEMES or selected == ARBITRARY_SCHEME:
                return selected
            for value in obj.values():
                found = self.find_selected_tilt_scheme_recursive(value)
                if found is not None:
                    return found
        elif isinstance(obj, list):
            for item in obj:
                found = self.find_selected_tilt_scheme_recursive(item)
                if found is not None:
                    return found
        return None

    def as_float(self, value, default=None):
        try:
            if value is None or value == "":
                return default
            return float(value)
        except Exception:
            return default

    def as_int(self, value, default=None):
        try:
            if value is None or value == "":
                return default
            return int(round(float(value)))
        except Exception:
            return default

    def as_bool(self, value, default=False):
        if isinstance(value, bool):
            return value
        if value is None or value == "":
            return default
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "y", "on")
        return bool(value)

    def clean_angle_number(self, x):
        x = round(float(x), 10)
        if abs(x - round(x)) < 1e-10:
            return int(round(x))
        return x

    def generate_even_step_angles(self, node):
        start = self.as_float(node.get("start_tilt_angle"))
        end = self.as_float(node.get("end_tilt_angle"))
        step = self.as_float(node.get("step_tilt_angle"))

        if start is None or end is None or step is None or step == 0:
            return None

        if end < start and step > 0:
            step = -step
        elif end > start and step < 0:
            step = -step

        angles = []
        x = start
        eps = abs(step) * 1e-9 + 1e-12

        if step > 0:
            while x <= end + eps:
                angles.append(self.clean_angle_number(x))
                x += step
        else:
            while x >= end - eps:
                angles.append(self.clean_angle_number(x))
                x += step

        return angles

    def generate_dose_symmetric_angles(self, node):
        end = self.as_float(node.get("end_tilt_angle"))
        step = self.as_float(node.get("step_tilt_angle"))
        group_size = self.as_int(node.get("group_size"), default=1)
        negative_then_positive = self.as_bool(node.get("negative_then_positive", True), default=True)

        if end is None or step is None or step == 0:
            return None
        if group_size is None or group_size < 1:
            return None

        max_abs_angle = abs(end)
        step_abs = abs(step)
        eps = step_abs * 1e-9 + 1e-12

        angles = [0.0]
        first_sign = -1 if negative_then_positive else 1
        second_sign = -first_sign
        sign_order = [first_sign, second_sign]
        next_abs_angle = {-1: step_abs, 1: step_abs}

        while True:
            added_any = False
            for sign in sign_order:
                for _ in range(group_size):
                    angle_abs = next_abs_angle[sign]
                    if angle_abs > max_abs_angle + eps:
                        break
                    angles.append(sign * angle_abs)
                    next_abs_angle[sign] += step_abs
                    added_any = True
            if not added_any:
                break

        return [self.clean_angle_number(a) for a in angles]

    # ------------------------------------------------------------
    # Saving, loading, preview
    # ------------------------------------------------------------

    def get_output_folder_and_name(self):
        folder_name = self.metadata.get("folder_name", "")
        master_name = self.metadata.get("master_name", "")

        if folder_name is None:
            folder_name = ""
        if master_name is None:
            master_name = ""

        folder_name = str(folder_name).strip()
        master_name = str(master_name).strip()

        if not folder_name or not master_name:
            return None, None
        folder = Path(folder_name)
        output_file = folder / f"{master_name}.JSON"
        return folder, output_file
        
    def warn_missing_output_name(self):
        messagebox.showwarning(
            "Missing output filename",
            "The metadata file was not saved.\n\n"
            "Please enter both required fields:\n\n"
            "  1. Folder name\n"
            "  2. Master name\n\n"
            "The output file will be saved as:\n"
            "  <folder_name>/<master_name>.JSON"
        )

    def save_current_metadata(self, show_message=True):
        self.update_all_widgets_to_metadata()

        folder, output_file = self.get_output_folder_and_name()

        if folder is None or output_file is None:
            if show_message:
                self.warn_missing_output_name()
            return False

        if not folder.exists():
            messagebox.showerror(
                "Folder not found",
                "The metadata file was not saved because the folder does not exist "
                "or is not accessible from this computer:\n\n"
                f"{folder}\n\n"
                "Please edit the Folder name field to a path that is valid on this "
                "computer."
            )
            return False

        if not folder.is_dir():
            messagebox.showerror(
                "Invalid folder",
                "The metadata file was not saved because the Folder name is not a folder:\n\n"
                f"{folder}"
            )
            return False

        self.add_derived_tilt_angles()
        self.duplicate_angles_once_if_requested()

        self.metadata["schema_name"] = self.schema.get("schema_name", "unknown")
        self.metadata["schema_version"] = self.schema.get("schema_version", "unknown")

        try:
            self.save_json(output_file, self.metadata)

            if show_message:
                messagebox.showinfo(
                    "Saved",
                    f"Saved metadata file:\n{output_file}\n"
                )

            return True

        except Exception as e:
            messagebox.showerror(
                "Save error",
                f"Could not save metadata:\n{e}"
            )
            return False

        
    def show_metadata_preview(self):
        self.update_all_widgets_to_metadata()
        self.add_derived_tilt_angles()
        self.duplicate_angles_once_if_requested()

        preview = tk.Toplevel(self.root)
        preview.title("Current metadata preview")
        preview.geometry("750x550")

        text = tk.Text(preview, wrap=tk.NONE)
        text.pack(fill=tk.BOTH, expand=True)
        text.insert("1.0", json.dumps(self.metadata, indent=2, ensure_ascii=False))
        text.configure(state=tk.DISABLED)

    def load_into_branch(self, path):
        filename = filedialog.askopenfilename(
            title="Load metadata/settings JSON",
            filetypes=[("JSON files", "*.json *.JSON"), ("All files", "*.*")]
        )
        if not filename:
            return

        try:
            loaded = self.load_json(filename)

            if path == ():
                self.metadata.clear()
                self.metadata.update(copy.deepcopy(loaded))
            else:
                source_node = self.find_matching_source_node(loaded, path)
                if source_node is None:
                    messagebox.showwarning("No matching branch", "Could not find a matching branch in the selected file.")
                    return

                target_node = self.get_metadata_node_for_path(path, create=True)
                if isinstance(source_node, dict):
                    target_node.clear()
                    target_node.update(copy.deepcopy(source_node))
                else:
                    messagebox.showwarning("Load skipped", "The matching source branch is not a dictionary.")
                    return

            self.refresh_visible_variables()

        except Exception as e:
            messagebox.showerror("Load error", f"Could not load JSON file:\n{e}")

    def find_matching_source_node(self, loaded_metadata, path):
        if len(path) == 0:
            return loaded_metadata

        target_name = path[-1]
        matches = []

        def recursive_search(obj):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if key == target_name:
                        matches.append(value)
                    recursive_search(value)
            elif isinstance(obj, list):
                for item in obj:
                    recursive_search(item)

        recursive_search(loaded_metadata)
        if not matches:
            return None
        return copy.deepcopy(matches[0])

    def refresh_visible_variables(self):
        for path, var in self.tk_vars.items():
            branch_name = path[-1]
            if branch_name not in self.branches:
                continue

            branch = self.branches[branch_name]
            node_type = branch["type"]

            if path in self.self_dropdown_paths:
                try:
                    dropdown_node = self.get_metadata_node_for_path(path, create=False)
                    var.set(dropdown_node.get("selected", ""))
                except Exception:
                    pass
                continue

            try:
                parent_node = self.get_parent_metadata_node(path, create=False)
            except Exception:
                continue

            if node_type == "dropdown":
                var.set(parent_node.get(branch_name, {}).get("selected", ""))
            elif node_type in PRIMITIVE_TYPES:
                value = parent_node.get(branch_name, branch.get("default", ""))
                if value is None:
                    value = ""
                var.set(value)


def main():
    parser = argparse.ArgumentParser(description="GUI editor for microscopy metadata JSON files.")
    parser.add_argument("master_json", nargs="?", default="master.json", help="Path to the master.JSON schema file.")
    args = parser.parse_args()

    app = MetadataGUI(args.master_json)
    app.run()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        input("\nAn error occurred. Press Enter to close...")
