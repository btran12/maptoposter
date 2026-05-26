#!/usr/bin/env python3
"""
Tkinter launcher for City Map Poster Generator.

This GUI keeps the command-line generator unchanged while making common options
easy to select and showing live logs during poster generation.
"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
from pathlib import Path
from tkinter import (
    BooleanVar,
    Button,
    Checkbutton,
    DoubleVar,
    END,
    Entry,
    Frame,
    IntVar,
    Label,
    LabelFrame,
    Radiobutton,
    StringVar,
    Text,
    Tk,
    Toplevel,
    messagebox,
)
from tkinter import ttk


APP_DIR = Path(__file__).resolve().parent
GENERATOR_SCRIPT = APP_DIR / "create_map_poster.py"
THEMES_DIR = APP_DIR / "themes"
POSTERS_DIR = APP_DIR / "posters"
TOOLTIP_BG = "#ffffe0"
TOOLTIP_FG = "#222222"
TOOLTIP_WRAP = 300
DEFAULT_WIDTH = 12.0
DEFAULT_HEIGHT = 16.0
RESOLUTION_PRESETS = {
    "Custom": None,
    "Instagram Post - 1080 x 1080": (3.6, 3.6),
    "Mobile Wallpaper - 1080 x 1920": (3.6, 6.4),
    "HD Wallpaper - 1920 x 1080": (6.4, 3.6),
    "4K Wallpaper - 3840 x 2160": (12.8, 7.2),
    "A4 Print - 2480 x 3508": (8.3, 11.7),
    "US Letter Print - 2550 x 3300": (8.5, 11.0),
    "Square Print - 3600 x 3600": (12.0, 12.0),
    "Portrait Poster - 3600 x 5400": (12.0, 18.0),
    "Landscape Poster - 5400 x 3600": (18.0, 12.0),
}


class ToolTip:
    def __init__(self, widget, text: str) -> None:
        self.widget = widget
        self.text = text
        self.tip_window: Toplevel | None = None
        self.widget.tooltip = self
        self.widget.bind("<Enter>", self.show)
        self.widget.bind("<Leave>", self.hide)
        self.widget.bind("<ButtonPress>", self.hide)

    def show(self, _event=None) -> None:
        if self.tip_window or not self.text:
            return

        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8

        self.tip_window = Toplevel(self.widget)
        self.tip_window.wm_overrideredirect(True)
        self.tip_window.wm_geometry(f"+{x}+{y}")

        Label(
            self.tip_window,
            text=self.text,
            justify="left",
            background=TOOLTIP_BG,
            foreground=TOOLTIP_FG,
            relief="solid",
            borderwidth=1,
            padx=8,
            pady=5,
            wraplength=TOOLTIP_WRAP,
        ).pack()

    def hide(self, _event=None) -> None:
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None


class PosterGeneratorGui:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title("City Map Poster Generator")
        self.root.minsize(980, 720)

        self.log_queue: queue.Queue[tuple[str, str | int | None]] = queue.Queue()
        self.process: subprocess.Popen[str] | None = None

        self.city = StringVar(value="Paris")
        self.country = StringVar(value="France")
        self.latitude = StringVar()
        self.longitude = StringVar()
        self.country_label = StringVar()
        self.display_city = StringVar()
        self.display_country = StringVar()
        self.font_family = StringVar()
        self.theme = StringVar()
        self.all_themes = BooleanVar(value=False)
        self.hide_text = BooleanVar(value=False)
        self.transparent_background = BooleanVar(value=False)
        self.distance = IntVar(value=18000)
        self.width = DoubleVar(value=DEFAULT_WIDTH)
        self.height = DoubleVar(value=DEFAULT_HEIGHT)
        self.resolution_preset = StringVar(value="Custom")
        self.output_format = StringVar(value="png")
        self.status = StringVar(value="Ready")
        self.updating_size_from_preset = False

        self.theme_names = self.load_themes()
        if self.theme_names:
            self.theme.set("terracotta" if "terracotta" in self.theme_names else self.theme_names[0])

        self.build_ui()
        self.update_command_preview()
        self.root.after(100, self.process_log_queue)

    def load_themes(self) -> list[str]:
        if not THEMES_DIR.exists():
            return []
        return sorted(path.stem for path in THEMES_DIR.glob("*.json"))

    def build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        main = Frame(self.root, padx=12, pady=12)
        main.grid(row=0, column=0, sticky="nsew")
        main.columnconfigure(0, weight=0)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(0, weight=1)

        controls = Frame(main)
        controls.grid(row=0, column=0, sticky="nsw", padx=(0, 12))

        self.build_location_section(controls)
        self.build_style_section(controls)
        self.build_output_section(controls)
        self.build_actions(controls)

        logs = Frame(main)
        logs.grid(row=0, column=1, sticky="nsew")
        logs.columnconfigure(0, weight=1)
        logs.rowconfigure(1, weight=1)

        Label(logs, textvariable=self.status, anchor="w").grid(row=0, column=0, sticky="ew")

        self.log_text = Text(logs, wrap="word", height=28, state="disabled")
        self.log_text.grid(row=1, column=0, sticky="nsew", pady=(6, 8))

        log_scroll = ttk.Scrollbar(logs, orient="vertical", command=self.log_text.yview)
        log_scroll.grid(row=1, column=1, sticky="ns", pady=(6, 8))
        self.log_text.configure(yscrollcommand=log_scroll.set)

        preview_box = LabelFrame(logs, text="Command Preview", padx=8, pady=8)
        preview_box.grid(row=2, column=0, columnspan=2, sticky="ew")
        preview_box.columnconfigure(0, weight=1)
        self.command_preview = Text(preview_box, height=3, wrap="word", state="disabled")
        self.command_preview.grid(row=0, column=0, sticky="ew")

        for variable in [
            self.city,
            self.country,
            self.latitude,
            self.longitude,
            self.country_label,
            self.display_city,
            self.display_country,
            self.font_family,
            self.theme,
            self.resolution_preset,
            self.output_format,
        ]:
            variable.trace_add("write", lambda *_: self.update_command_preview())
        for variable in [
            self.all_themes,
            self.hide_text,
            self.transparent_background,
            self.distance,
            self.width,
            self.height,
        ]:
            variable.trace_add("write", lambda *_: self.update_command_preview())
        self.width.trace_add("write", lambda *_: self.on_custom_size_changed())
        self.height.trace_add("write", lambda *_: self.on_custom_size_changed())

    def build_location_section(self, parent: Frame) -> None:
        section = LabelFrame(parent, text="Location", padx=10, pady=10)
        section.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        section.columnconfigure(1, weight=1)

        self.add_labeled_entry(
            section,
            "City",
            self.city,
            0,
            "Used for geocoding and as the default city text on the poster.",
        )
        self.add_labeled_entry(
            section,
            "Country",
            self.country,
            2,
            "Helps find the right city when names exist in multiple countries.",
        )
        self.add_labeled_entry(
            section,
            "Latitude override",
            self.latitude,
            4,
            "Optional center point. Leave blank to look up the city automatically.",
        )
        self.add_labeled_entry(
            section,
            "Longitude override",
            self.longitude,
            6,
            "Use with latitude to focus the poster on a specific neighborhood.",
        )

    def build_style_section(self, parent: Frame) -> None:
        section = LabelFrame(parent, text="Poster Options", padx=10, pady=10)
        section.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        section.columnconfigure(1, weight=1)

        theme_help = "Controls the poster colors for roads, water, parks, background, and text."
        theme_label = Label(section, text="Theme")
        theme_label.grid(row=0, column=0, sticky="w", pady=3)
        self.theme_combo = ttk.Combobox(
            section,
            textvariable=self.theme,
            values=self.theme_names,
            state="readonly",
            width=28,
        )
        self.theme_combo.grid(row=0, column=1, sticky="ew", pady=3)
        ToolTip(theme_label, theme_help)
        ToolTip(self.theme_combo, theme_help)

        all_themes_check = Checkbutton(
            section,
            text="Generate all themes",
            variable=self.all_themes,
            command=self.on_all_themes_changed,
        )
        all_themes_check.grid(row=2, column=0, columnspan=2, sticky="w", pady=3)
        ToolTip(all_themes_check, "Creates one poster for every theme in the themes folder.")

        hide_text_check = Checkbutton(
            section,
            text="Hide all poster text",
            variable=self.hide_text,
        )
        hide_text_check.grid(row=4, column=0, columnspan=2, sticky="w", pady=3)
        ToolTip(hide_text_check, "Removes city, country, coordinates, separator line, and attribution.")

        transparent_background_check = Checkbutton(
            section,
            text="Transparent background",
            variable=self.transparent_background,
        )
        transparent_background_check.grid(row=5, column=0, columnspan=2, sticky="w", pady=3)
        ToolTip(
            transparent_background_check,
            "Saves without the theme background fill. Roads, water, parks, and text remain visible.",
        )

        self.add_labeled_entry(
            section,
            "Country label",
            self.country_label,
            7,
            "Optional replacement for the country text shown on the poster.",
        )
        self.add_labeled_entry(
            section,
            "Display city",
            self.display_city,
            9,
            "Optional poster text. Useful for local names or non-Latin scripts.",
        )
        self.add_labeled_entry(
            section,
            "Display country",
            self.display_country,
            11,
            "Optional poster country text, independent from the geocoding country.",
        )
        self.add_labeled_entry(
            section,
            "Font family",
            self.font_family,
            13,
            'Optional Google Fonts family, for example "Noto Sans JP" or "Cairo".',
        )

    def build_output_section(self, parent: Frame) -> None:
        section = LabelFrame(parent, text="Size & Output", padx=10, pady=10)
        section.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        section.columnconfigure(1, weight=1)

        preset_help = "Choose a common target size. Custom keeps your manual width and height values."
        preset_label = Label(section, text="Resolution preset")
        preset_label.grid(row=0, column=0, sticky="w", pady=3)
        preset_combo = ttk.Combobox(
            section,
            textvariable=self.resolution_preset,
            values=list(RESOLUTION_PRESETS.keys()),
            state="readonly",
            width=28,
        )
        preset_combo.grid(row=0, column=1, sticky="ew", pady=3)
        preset_combo.bind("<<ComboboxSelected>>", self.on_resolution_preset_changed)
        ToolTip(preset_label, preset_help)
        ToolTip(preset_combo, preset_help)

        self.add_labeled_spinbox(
            section,
            "Distance (m)",
            self.distance,
            2,
            1000,
            60000,
            500,
            "Map radius around the center. Smaller values zoom in; larger values show more city.",
        )
        self.add_labeled_spinbox(
            section,
            "Width (in)",
            self.width,
            4,
            1,
            20,
            0.1,
            "Output width in inches. PNG files save at 300 DPI, so 3.6 inches becomes 1080 pixels.",
        )
        self.add_labeled_spinbox(
            section,
            "Height (in)",
            self.height,
            6,
            1,
            20,
            0.1,
            "Output height in inches. Use portrait, landscape, or square dimensions.",
        )

        format_help = "PNG is best for previews; SVG and PDF are useful for print workflows."
        format_label = Label(section, text="Format")
        format_label.grid(row=8, column=0, sticky="w", pady=3)
        ToolTip(format_label, format_help)
        formats = Frame(section)
        formats.grid(row=8, column=1, sticky="w", pady=3)
        for value in ["png", "svg", "pdf"]:
            radio = Radiobutton(
                formats,
                text=value.upper(),
                value=value,
                variable=self.output_format,
            )
            radio.pack(side="left", padx=(0, 12))
            ToolTip(radio, format_help)

    def build_actions(self, parent: Frame) -> None:
        section = Frame(parent)
        section.grid(row=3, column=0, sticky="ew")
        section.columnconfigure(0, weight=1)
        section.columnconfigure(1, weight=1)

        self.generate_button = Button(section, text="Generate Poster", command=self.start_generation)
        self.generate_button.grid(row=0, column=0, sticky="ew", padx=(0, 6), pady=(0, 8))

        self.cancel_button = Button(section, text="Cancel", command=self.cancel_generation, state="disabled")
        self.cancel_button.grid(row=0, column=1, sticky="ew", padx=(6, 0), pady=(0, 8))

        Button(section, text="Open Posters Folder", command=self.open_posters_folder).grid(
            row=1, column=0, columnspan=2, sticky="ew", pady=(0, 8)
        )

        self.progress = ttk.Progressbar(parent, mode="indeterminate")
        self.progress.grid(row=4, column=0, sticky="ew", pady=(10, 0))

    def add_labeled_entry(
        self,
        parent: Frame,
        label: str,
        variable: StringVar,
        row: int,
        helper: str | None = None,
    ) -> None:
        label_widget = Label(parent, text=label)
        label_widget.grid(row=row, column=0, sticky="w", pady=3)
        entry_widget = Entry(parent, textvariable=variable, width=30)
        entry_widget.grid(row=row, column=1, sticky="ew", pady=3)
        if helper:
            ToolTip(label_widget, helper)
            ToolTip(entry_widget, helper)

    def add_labeled_spinbox(
        self,
        parent: Frame,
        label: str,
        variable: IntVar | DoubleVar,
        row: int,
        from_: float,
        to: float,
        increment: float,
        helper: str | None = None,
    ) -> None:
        label_widget = Label(parent, text=label)
        label_widget.grid(row=row, column=0, sticky="w", pady=3)
        spinbox = ttk.Spinbox(
            parent,
            textvariable=variable,
            from_=from_,
            to=to,
            increment=increment,
            width=12,
        )
        spinbox.grid(row=row, column=1, sticky="w", pady=3)
        if helper:
            ToolTip(label_widget, helper)
            ToolTip(spinbox, helper)

    def on_all_themes_changed(self) -> None:
        state = "disabled" if self.all_themes.get() else "readonly"
        self.theme_combo.configure(state=state)
        self.update_command_preview()

    def on_resolution_preset_changed(self, _event=None) -> None:
        size = RESOLUTION_PRESETS.get(self.resolution_preset.get())
        if size is None:
            size = (DEFAULT_WIDTH, DEFAULT_HEIGHT)

        width, height = size
        self.updating_size_from_preset = True
        try:
            self.width.set(width)
            self.height.set(height)
        finally:
            self.updating_size_from_preset = False
        self.update_command_preview()

    def on_custom_size_changed(self) -> None:
        if self.updating_size_from_preset:
            return
        if self.resolution_preset.get() != "Custom":
            self.resolution_preset.set("Custom")

    def build_command(self) -> list[str]:
        command = [
            sys.executable,
            "-u",
            str(GENERATOR_SCRIPT),
            "--city",
            self.city.get().strip(),
            "--country",
            self.country.get().strip(),
            "--distance",
            str(self.distance.get()),
            "--width",
            str(self.width.get()),
            "--height",
            str(self.height.get()),
            "--format",
            self.output_format.get(),
        ]

        if self.all_themes.get():
            command.append("--all-themes")
        else:
            command.extend(["--theme", self.theme.get()])

        optional_text_values = [
            ("--latitude", self.latitude.get()),
            ("--longitude", self.longitude.get()),
            ("--country-label", self.country_label.get()),
            ("--display-city", self.display_city.get()),
            ("--display-country", self.display_country.get()),
            ("--font-family", self.font_family.get()),
        ]
        for flag, value in optional_text_values:
            value = value.strip()
            if value:
                command.extend([flag, value])

        if self.hide_text.get():
            command.append("--hide-text")
        if self.transparent_background.get():
            command.append("--transparent-background")

        return command

    def validate_inputs(self) -> bool:
        if not self.city.get().strip() or not self.country.get().strip():
            messagebox.showerror("Missing Location", "City and country are required.")
            return False

        has_lat = bool(self.latitude.get().strip())
        has_lon = bool(self.longitude.get().strip())
        if has_lat != has_lon:
            messagebox.showerror(
                "Coordinates Incomplete",
                "Use both latitude and longitude overrides, or leave both blank.",
            )
            return False

        if not self.all_themes.get() and not self.theme.get():
            messagebox.showerror("Missing Theme", "Choose a theme or enable all themes.")
            return False

        return True

    def start_generation(self) -> None:
        if self.process is not None:
            return
        if not self.validate_inputs():
            return

        command = self.build_command()
        self.clear_log()
        self.append_log("Running:\n" + subprocess.list2cmdline(command) + "\n\n")
        self.status.set("Generating poster...")
        self.generate_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.progress.start(12)

        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        try:
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTHONUTF8"] = "1"
            self.process = subprocess.Popen(
                command,
                cwd=APP_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                encoding="utf-8",
                errors="replace",
                creationflags=creationflags,
                env=env,
            )
        except OSError as exc:
            self.process = None
            self.finish_generation(False, f"Could not start generator: {exc}")
            return

        threading.Thread(target=self.read_process_output, daemon=True).start()
        threading.Thread(target=self.wait_for_process, daemon=True).start()

    def read_process_output(self) -> None:
        if self.process is None or self.process.stdout is None:
            return
        while True:
            chunk = self.process.stdout.read(1)
            if not chunk:
                break
            self.log_queue.put(("log", chunk))

    def wait_for_process(self) -> None:
        if self.process is None:
            return
        return_code = self.process.wait()
        self.log_queue.put(("done", return_code))

    def cancel_generation(self) -> None:
        if self.process is None:
            return
        self.append_log("\nCancelling generation...\n")
        self.process.terminate()
        self.status.set("Cancelling...")

    def finish_generation(self, success: bool, message: str) -> None:
        self.progress.stop()
        self.generate_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")
        self.process = None
        self.status.set(message)
        self.append_log("\n" + message + "\n")
        if success:
            self.open_folder_button_prompt()

    def open_folder_button_prompt(self) -> None:
        if messagebox.askyesno("Poster Generation Complete", "Open the posters folder now?"):
            self.open_posters_folder()

    def process_log_queue(self) -> None:
        while True:
            try:
                kind, payload = self.log_queue.get_nowait()
            except queue.Empty:
                break

            if kind == "log":
                self.append_log(str(payload))
            elif kind == "done":
                return_code = int(payload) if payload is not None else 1
                if return_code == 0:
                    self.finish_generation(True, "Poster generation complete.")
                else:
                    self.finish_generation(False, f"Poster generation failed with exit code {return_code}.")

        self.root.after(100, self.process_log_queue)

    def append_log(self, text: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert(END, text)
        self.log_text.see(END)
        self.log_text.configure(state="disabled")

    def clear_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", END)
        self.log_text.configure(state="disabled")

    def update_command_preview(self) -> None:
        try:
            command = subprocess.list2cmdline(self.build_command())
        except Exception:
            command = ""
        self.command_preview.configure(state="normal")
        self.command_preview.delete("1.0", END)
        self.command_preview.insert("1.0", command)
        self.command_preview.configure(state="disabled")

    def open_posters_folder(self) -> None:
        POSTERS_DIR.mkdir(exist_ok=True)
        if os.name == "nt":
            os.startfile(POSTERS_DIR)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(POSTERS_DIR)])
        else:
            subprocess.Popen(["xdg-open", str(POSTERS_DIR)])

def main() -> None:
    root = Tk()
    app = PosterGeneratorGui(root)
    root.protocol("WM_DELETE_WINDOW", lambda: on_close(root, app))
    root.mainloop()


def on_close(root: Tk, app: PosterGeneratorGui) -> None:
    if app.process is not None:
        if not messagebox.askyesno("Generation Running", "Cancel generation and close?"):
            return
        app.process.terminate()
    root.destroy()


if __name__ == "__main__":
    main()
