# monarch_demon.py

A lightweight macOS background daemon that turns the APH Monarch into a multi-line (8 rows by 32 cells) tactile coding terminal and 8-dot computer braille keyboard while keeping VoiceOver active for speech.

## Why This Exists

Out of the box, macOS VoiceOver restricts the Monarch to a single 32-cell line and introduces noticeable input lag over USB due to raw touch packet congestion. `monarch_demon.py` bypasses Apple's single-line braille driver by reading the focused text window through the macOS Accessibility API (`pyobjc`) and communicating directly with the Monarch's multi-line HID reports over shared USB access.

## Features

- **Universal Application Tracking:** Automatically follows focus across macOS editors such as TextMate, TextEdit, and Notes as you switch files or windows with `Command-Tab` or `Command-Grave`.
- **32-Cell Line Wrapping:** Soft-wraps lines longer than 32 characters across consecutive rows so long lines of code never clip at the right margin.
- **Stationary 8-Line Viewport:** Keeps the 8-line braille window steady while a Dots 7+8 cursor indicator moves across rows 1 through 8, scrolling only when your caret crosses the top or bottom boundary.
- **Single-Press Cursor Routing:** Hold a finger on any braille cell and press the round center button between the Perkins keys once to jump the system caret directly to that character.
- **8-Dot Computer Braille Input and Output:** Uses the standard North American Apple/Windows 8-dot Computer Braille Code table (with Dot 7 for uppercase letters and shifted symbols such as `@`, `[`, `]`, `\`, `^`, and `_`), plus standalone Dot 7 for Backspace and standalone Dot 8 for Return.
- **Hardware Navigation:** Maps the right directional cross pad to Up, Down, Left, and Right arrow keys with key-repeat, and maps the Pan Left and Pan Right keys to 8-line page scrolling.

## Requirements and Installation

This daemon requires macOS, Python 3, and `hidapi` along with the `pyobjc` Cocoa and ApplicationServices bindings.

```bash
python3 -m pip install hidapi pyobjc-framework-Cocoa pyobjc-framework-ApplicationServices