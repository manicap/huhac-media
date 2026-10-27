from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable
import webbrowser

from media_desk.contract import ContractError

from huhac_launcher.config import (
    LauncherConfigurationError,
    LauncherProfile,
    LauncherStore,
    open_launcher_store,
    parse_port,
)
from huhac_launcher.controller import ActionResult, BackendController, LauncherState
from huhac_launcher.snapshots import NormalizerChoice, scan_normalizer_snapshots, validate_profile_selection


_STATE_LABELS = {
    LauncherState.OFF: "Vypnuto",
    LauncherState.STARTING: "Spouští se",
    LauncherState.RUNNING: "Spuštěno",
    LauncherState.STOPPING: "Zastavuje se",
    LauncherState.ERROR: "Chyba",
}


class ProfileDialog:
    def __init__(self, parent: tk.Misc, profile: LauncherProfile | None) -> None:
        self.result: LauncherProfile | None = None
        self._id = profile.id if profile else LauncherStore.new_id()
        self.window = tk.Toplevel(parent)
        self.window.title("Upravit profil" if profile else "Přidat profil")
        self.window.transient(parent)
        self.window.grab_set()
        self.window.resizable(False, False)
        frame = ttk.Frame(self.window, padding=16)
        frame.grid(sticky="nsew")
        self.name = tk.StringVar(value=profile.name if profile else "")
        self.workspace = tk.StringVar(value=str(profile.workspace) if profile else "")
        self.profile_root = tk.StringVar(value=str(profile.profile) if profile else "")
        self.keyframes = tk.StringVar(value=profile.keyframe_fingerprint or "" if profile else "")
        fields = (
            ("Název", self.name), ("Workspace", self.workspace),
            ("Media Desk profil", self.profile_root),
            ("Keyframes fingerprint", self.keyframes),
        )
        for row, (label, variable) in enumerate(fields):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=4)
            ttk.Entry(frame, textvariable=variable, width=58).grid(row=row, column=1, sticky="ew", padx=8, pady=4)
            if row in {1, 2}:
                ttk.Button(frame, text="Vybrat…", command=lambda target=variable: self._browse(target)).grid(row=row, column=2)
        buttons = ttk.Frame(frame)
        buttons.grid(row=len(fields), column=0, columnspan=3, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="Zrušit", command=self.window.destroy).grid(row=0, column=0, padx=4)
        ttk.Button(buttons, text="Uložit", command=self._save).grid(row=0, column=1, padx=4)

    def _browse(self, target: tk.StringVar) -> None:
        selected = filedialog.askdirectory(parent=self.window, initialdir=target.get() or None)
        if selected:
            target.set(selected)

    def _save(self) -> None:
        try:
            values = {
                "name": self.name.get().strip(),
                "workspace": Path(self.workspace.get()).expanduser(),
                "profile": Path(self.profile_root.get()).expanduser(),
            }
            if not values["name"]:
                raise LauncherConfigurationError("Název profilu nesmí být prázdný")
            if not values["workspace"].is_absolute() or not values["profile"].is_absolute():
                raise LauncherConfigurationError("Workspace a profil musí být absolutní cesty")
            keyframes = self.keyframes.get().strip() or None
            if keyframes is not None and (len(keyframes) != 64 or any(c not in "0123456789abcdef" for c in keyframes)):
                raise LauncherConfigurationError("Keyframes fingerprint musí mít 64 malých hex znaků")
            profile = LauncherProfile(
                self._id, str(values["name"]), values["workspace"], values["profile"],
                8878, keyframes,
            )
            validate_profile_selection(profile)
            if not profile.profile.is_dir():
                raise LauncherConfigurationError("Media Desk profil musí být existující adresář")
        except (LauncherConfigurationError, ContractError, OSError) as exc:
            messagebox.showerror("HUHÁČ Launcher", str(exc), parent=self.window)
            return
        self.result = profile
        self.window.destroy()

    def show(self) -> LauncherProfile | None:
        self.window.wait_window()
        return self.result


class LauncherWindow:
    def __init__(
        self,
        root: tk.Tk,
        controller: BackendController,
        store: LauncherStore,
        project_root: Path,
        *,
        browser_opener: Callable[[str], object] = webbrowser.open,
    ) -> None:
        self.root = root
        self.controller = controller
        self.store = store
        self.project_root = Path(project_root)
        self.browser_opener = browser_opener
        self._worker: threading.Thread | None = None
        self._snapshot_worker: threading.Thread | None = None
        self._closing = False
        self._snapshot_by_label: dict[str, NormalizerChoice | None] = {}
        self._profile_labels: list[str] = []

        root.title("HUHÁČ Launcher v0.2")
        root.resizable(False, False)
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        frame = ttk.Frame(root, padding=18)
        frame.grid(sticky="nsew")
        ttk.Label(frame, text="Media Desk", font=("Segoe UI", 14, "bold")).grid(row=0, column=0, columnspan=4, sticky="w")

        ttk.Label(frame, text="Profil").grid(row=1, column=0, sticky="w", pady=(12, 4))
        self.profile_var = tk.StringVar()
        self.profile_combo = ttk.Combobox(frame, textvariable=self.profile_var, state="readonly", width=42)
        self.profile_combo.grid(row=1, column=1, columnspan=3, sticky="ew", pady=(12, 4))
        self.profile_combo.bind("<<ComboboxSelected>>", self._profile_changed)

        self.add_button = ttk.Button(frame, text="Přidat", command=self._add_profile)
        self.edit_button = ttk.Button(frame, text="Upravit", command=self._edit_profile)
        self.remove_button = ttk.Button(frame, text="Odebrat", command=self._remove_profile)
        self.add_button.grid(row=2, column=1, sticky="ew", padx=(0, 4))
        self.edit_button.grid(row=2, column=2, sticky="ew", padx=4)
        self.remove_button.grid(row=2, column=3, sticky="ew", padx=(4, 0))

        ttk.Label(frame, text="Normalizer").grid(row=3, column=0, sticky="w", pady=(12, 4))
        self.snapshot_var = tk.StringVar()
        self.snapshot_combo = ttk.Combobox(frame, textvariable=self.snapshot_var, state="readonly", width=58)
        self.snapshot_combo.grid(row=3, column=1, columnspan=3, sticky="ew", pady=(12, 4))
        self.snapshot_combo.bind("<<ComboboxSelected>>", self._snapshot_changed)

        ttk.Label(frame, text="Port backendu").grid(row=4, column=0, sticky="w", pady=4)
        self.port_var = tk.StringVar()
        self.port_entry = ttk.Entry(frame, textvariable=self.port_var, width=10)
        self.port_entry.grid(row=4, column=1, sticky="w", pady=4)
        self.port_entry.bind("<FocusOut>", self._port_focus_out)
        self.address_value = ttk.Label(frame, text="")
        self.address_value.grid(row=4, column=2, columnspan=2, sticky="e")

        ttk.Separator(frame).grid(row=5, column=0, columnspan=4, sticky="ew", pady=12)
        ttk.Label(frame, text="Stav").grid(row=6, column=0, sticky="w")
        self.state_value = ttk.Label(frame, text="Vypnuto")
        self.state_value.grid(row=6, column=1, columnspan=3, sticky="w")
        self.start_button = ttk.Button(frame, text="Start", command=self._start)
        self.stop_button = ttk.Button(frame, text="Stop", command=self._stop)
        self.open_button = ttk.Button(frame, text="Otevřít Media Desk", command=self._open_ui)
        self.start_button.grid(row=7, column=1, sticky="ew", padx=(0, 4), pady=(12, 0))
        self.stop_button.grid(row=7, column=2, sticky="ew", padx=4, pady=(12, 0))
        self.open_button.grid(row=7, column=3, sticky="ew", padx=(4, 0), pady=(12, 0))
        self.error_value = ttk.Label(frame, text="", foreground="#a11", wraplength=540, justify="left")
        self.error_value.grid(row=8, column=0, columnspan=4, sticky="w", pady=(12, 0))
        for column in range(1, 4):
            frame.columnconfigure(column, weight=1)
        self._load_active_profile()
        self._refresh()

    @property
    def active_profile(self) -> LauncherProfile:
        return self.store.settings.active_profile

    def _busy(self) -> bool:
        return self._worker is not None and self._worker.is_alive()

    def _locked(self) -> bool:
        return self._busy() or self.controller.owns_process or self.controller.state in {LauncherState.STARTING, LauncherState.STOPPING}

    def _refresh(self) -> None:
        state = self.controller.state
        self.state_value.configure(text=_STATE_LABELS[state])
        if self.controller.error:
            self.error_value.configure(text=self.controller.error)
        locked = self._locked()
        owns = self.controller.owns_process
        self.start_button.configure(state="disabled" if locked else "normal")
        self.stop_button.configure(state="normal" if owns and not self._busy() else "disabled")
        self.open_button.configure(state="normal" if state is LauncherState.RUNNING and owns else "disabled")
        for widget in (self.profile_combo, self.snapshot_combo, self.port_entry, self.add_button, self.edit_button, self.remove_button):
            widget.configure(state="disabled" if locked else ("readonly" if widget in {self.profile_combo, self.snapshot_combo} else "normal"))
        self.root.after(150, self._refresh)

    def _profile_label(self, profile: LauncherProfile) -> str:
        return f"{profile.name}  [{profile.id}]"

    def _load_active_profile(self) -> None:
        self._profile_labels = [self._profile_label(profile) for profile in self.store.settings.profiles]
        self.profile_combo.configure(values=self._profile_labels)
        active = self.active_profile
        self.profile_var.set(self._profile_label(active))
        self.port_var.set(str(active.port))
        self.address_value.configure(text=f"http://127.0.0.1:{active.port}")
        self._set_controller(active)
        self._scan_snapshots(active)

    def _set_controller(self, profile: LauncherProfile) -> None:
        if self.controller.owns_process:
            raise LauncherConfigurationError("Běžící backend nelze překonfigurovat")
        self.controller = BackendController(self.store.settings.runtime(profile), self.project_root)

    def _profile_changed(self, _event=None) -> None:
        if self._locked():
            return
        index = self.profile_combo.current()
        if index < 0:
            return
        profile = self.store.settings.profiles[index]
        try:
            self.store.activate(profile.id)
            self._load_active_profile()
            self.error_value.configure(text="")
        except LauncherConfigurationError as exc:
            messagebox.showerror("HUHÁČ Launcher", str(exc), parent=self.root)

    def _scan_snapshots(self, profile: LauncherProfile) -> None:
        self.snapshot_combo.configure(values=("Načítám snapshoty…",))
        self.snapshot_var.set("Načítám snapshoty…")
        profile_id = profile.id

        def work() -> None:
            try:
                _workspace_id, choices = scan_normalizer_snapshots(profile.workspace)
                error = ""
            except Exception as exc:
                choices = ()
                error = str(exc)
            self.root.after(0, lambda: self._finish_snapshot_scan(profile_id, choices, error))

        self._snapshot_worker = threading.Thread(target=work, name="huhac-launcher-snapshots", daemon=True)
        self._snapshot_worker.start()

    def _finish_snapshot_scan(self, profile_id: str, choices: tuple[NormalizerChoice, ...], error: str) -> None:
        if self.active_profile.id != profile_id:
            return
        self._snapshot_by_label = {"Bez Normalizeru": None}
        for choice in choices:
            self._snapshot_by_label[choice.label] = choice
        selected = self.active_profile.normalizer_selection
        selected_label = "Bez Normalizeru"
        if selected is not None:
            found = next((choice for choice in choices if choice.key == selected), None)
            if found is None:
                selected_label = f"Uložený snapshot chybí · {selected[0][:8]} / {selected[1][:8]}"
                self._snapshot_by_label[selected_label] = NormalizerChoice(*selected, None, None, "missing", "Uložený snapshot neexistuje")
            else:
                selected_label = found.label
        self.snapshot_combo.configure(values=tuple(self._snapshot_by_label))
        self.snapshot_var.set(selected_label)
        self.error_value.configure(text=error or (self._snapshot_by_label[selected_label].message if self._snapshot_by_label[selected_label] and not self._snapshot_by_label[selected_label].valid else ""))

    def _snapshot_changed(self, _event=None) -> None:
        if self._locked():
            return
        choice = self._snapshot_by_label.get(self.snapshot_var.get())
        if choice is not None and not choice.valid:
            messagebox.showerror("HUHÁČ Launcher", choice.message, parent=self.root)
            self._scan_snapshots(self.active_profile)
            return
        updated = replace(
            self.active_profile,
            normalizer_configuration_fingerprint=choice.configuration_fingerprint if choice else None,
            normalizer_input_set_fingerprint=choice.input_set_fingerprint if choice else None,
        )
        try:
            self.store.update(updated)
            self._set_controller(updated)
            self.error_value.configure(text="")
        except LauncherConfigurationError as exc:
            messagebox.showerror("HUHÁČ Launcher", str(exc), parent=self.root)

    def _persist_port(self) -> bool:
        try:
            port = parse_port(self.port_var.get().strip())
            updated = replace(self.active_profile, port=port)
            if updated != self.active_profile:
                self.store.update(updated)
                self._set_controller(updated)
            self.address_value.configure(text=f"http://127.0.0.1:{port}")
            self.error_value.configure(text="")
            return True
        except LauncherConfigurationError as exc:
            self.error_value.configure(text=str(exc))
            return False

    def _port_focus_out(self, _event=None) -> None:
        if not self._locked():
            self._persist_port()

    def _add_profile(self) -> None:
        profile = ProfileDialog(self.root, None).show()
        if profile is None:
            return
        try:
            self.store.add(profile)
            self._load_active_profile()
        except LauncherConfigurationError as exc:
            messagebox.showerror("HUHÁČ Launcher", str(exc), parent=self.root)

    def _edit_profile(self) -> None:
        previous = self.active_profile
        profile = ProfileDialog(self.root, previous).show()
        if profile is None:
            return
        profile = replace(
            profile, port=previous.port,
            normalizer_configuration_fingerprint=(previous.normalizer_configuration_fingerprint if profile.workspace == previous.workspace else None),
            normalizer_input_set_fingerprint=(previous.normalizer_input_set_fingerprint if profile.workspace == previous.workspace else None),
        )
        try:
            self.store.update(profile)
            self._load_active_profile()
        except LauncherConfigurationError as exc:
            messagebox.showerror("HUHÁČ Launcher", str(exc), parent=self.root)

    def _remove_profile(self) -> None:
        profile = self.active_profile
        if not messagebox.askyesno(
            "HUHÁČ Launcher",
            f"Odebrat profil „{profile.name}“ pouze z launcheru?\nWorkspace ani uživatelská data se nesmažou.",
            parent=self.root,
        ):
            return
        try:
            self.store.remove(profile.id)
            self._load_active_profile()
        except LauncherConfigurationError as exc:
            messagebox.showerror("HUHÁČ Launcher", str(exc), parent=self.root)

    def _run(self, action: Callable[[], ActionResult], finished: Callable[[ActionResult], None]) -> None:
        if self._busy():
            return
        def work() -> None:
            result = action()
            self.root.after(0, lambda: finished(result))
        self._worker = threading.Thread(target=work, daemon=True)
        self._worker.start()

    def _start(self) -> None:
        if not self._persist_port():
            return
        self._run(self.controller.start, lambda _result: None)

    def _stop(self) -> None:
        self._run(self.controller.stop, self._after_stop)

    def _open_ui(self) -> None:
        if self.controller.state is LauncherState.RUNNING and self.controller.owns_process:
            self.browser_opener(self.controller.config.address)

    def _after_stop(self, result: ActionResult) -> None:
        if result.needs_force and messagebox.askyesno("HUHÁČ Launcher", "Media Desk nereaguje. Vynutit ukončení pouze procesu spuštěného launcherem?", parent=self.root):
            self._run(self.controller.force_stop, lambda _forced: None)

    def _on_close(self) -> None:
        if self._closing:
            return
        if not self.controller.owns_process:
            self.root.destroy()
            return
        self._closing = True
        self._run(self.controller.stop, self._finish_close)

    def _finish_close(self, result: ActionResult) -> None:
        if result.ok:
            self.root.destroy()
        elif result.needs_force and messagebox.askyesno("HUHÁČ Launcher", "Media Desk nereaguje. Vynutit ukončení pouze vlastněného procesu?", parent=self.root):
            self._run(self.controller.force_stop, self._finish_force_close)
        else:
            self._closing = False

    def _finish_force_close(self, result: ActionResult) -> None:
        if result.ok:
            self.root.destroy()
        else:
            messagebox.showerror("HUHÁČ Launcher", result.message, parent=self.root)
            self._closing = False


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="HUHÁČ Launcher v0.2")
    parser.add_argument("--project-root", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--example-config", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    project_root = (args.project_root or Path(__file__).resolve().parents[2]).resolve()
    try:
        store = open_launcher_store(
            project_root,
            explicit_config=args.config,
            example_config=args.example_config,
        )
    except LauncherConfigurationError as exc:
        root = tk.Tk(); root.withdraw()
        messagebox.showerror("HUHÁČ Launcher", str(exc), parent=root)
        root.destroy()
        return 2
    root = tk.Tk()
    controller = BackendController(store.settings.runtime(), project_root)
    LauncherWindow(root, controller, store, project_root)
    root.mainloop()
    return 0
