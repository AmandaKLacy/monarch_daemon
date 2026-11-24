import sys
import time
from AppKit import NSWorkspace
import ApplicationServices as AS
from Foundation import NSDate, NSRunLoop
import hid

# Standard Apple/Windows 8-Dot Computer Braille Code
ASCII_TO_BRAILLE = {
    ' ': 0x00,
    'a': 0x01, 'b': 0x03, 'c': 0x09, 'd': 0x19, 'e': 0x11,
    'f': 0x0B, 'g': 0x1B, 'h': 0x13, 'i': 0x0A, 'j': 0x1A,
    'k': 0x05, 'l': 0x07, 'm': 0x0D, 'n': 0x1D, 'o': 0x15,
    'p': 0x0F, 'q': 0x1F, 'r': 0x17, 's': 0x0E, 't': 0x1E,
    'u': 0x25, 'v': 0x27, 'w': 0x3A, 'x': 0x2D, 'y': 0x3D, 'z': 0x35,
    '0': 0x34, '1': 0x02, '2': 0x06, '3': 0x12, '4': 0x32,
    '5': 0x22, '6': 0x16, '7': 0x36, '8': 0x26, '9': 0x14,
    '!': 0x2E,  # dots 2-3-4-6
    '"': 0x10,  # dot 5
    '#': 0x3C,  # dots 3-4-5-6
    '$': 0x2B,  # dots 1-2-4-6
    '%': 0x29,  # dots 1-4-6
    '&': 0x2F,  # dots 1-2-3-4-6
    '\'': 0x04, # dot 3
    '(': 0x37,  # dots 1-2-3-5-6
    ')': 0x3E,  # dots 2-3-4-5-6
    '*': 0x21,  # dots 1-6
    '+': 0x2C,  # dots 3-4-6
    ',': 0x20,  # dot 6
    '-': 0x24,  # dots 3-6
    '.': 0x28,  # dots 4-6
    '/': 0x0C,  # dots 3-4
    ':': 0x31,  # dots 1-5-6
    ';': 0x30,  # dots 5-6
    '<': 0x23,  # dots 1-2-6
    '=': 0x3F,  # dots 1-2-3-4-5-6
    '>': 0x1C,  # dots 3-4-5
    '?': 0x39,  # dots 1-4-5-6
    '@': 0x48,  # dots 4-7
    '[': 0x6A,  # dots 2-4-6-7
    '\\': 0x73, # dots 1-2-5-6-7
    ']': 0x7B,  # dots 1-2-4-5-6-7
    '^': 0x58,  # dots 4-5-7
    '_': 0x78,  # dots 4-5-6-7
    '`': 0x08,  # dot 4
    '{': 0x2A,  # dots 2-4-6
    '|': 0x33,  # dots 1-2-5-6
    '}': 0x3B,  # dots 1-2-4-5-6
    '~': 0x18   # dots 4-5
}

for char, pattern in list(ASCII_TO_BRAILLE.items()):
    if 'a' <= char <= 'z':
        ASCII_TO_BRAILLE[char.upper()] = pattern | 0x40

BRAILLE_TO_ASCII = {pattern: ch for ch, pattern in ASCII_TO_BRAILLE.items()}

# Right D-pad bitmasks (bits 11-14) mapped to macOS virtual arrow keycodes
RIGHT_DPAD_KEYCODES = {
    (1 << 11): 126,  # Up Arrow
    (1 << 12): 125,  # Down Arrow
    (1 << 13): 123,  # Left Arrow
    (1 << 14): 124,  # Right Arrow
}


def find_monarch():
    for dev in hid.enumerate():
        if dev.get('usage_page') == 0x41 or "Monarch" in dev.get('product_string', ''):
            return dev.get('path'), dev.get('vendor_id'), dev.get('product_id')
    return None, None, None


def send_virtual_key(keycode):
    down = AS.CGEventCreateKeyboardEvent(None, keycode, True)
    up = AS.CGEventCreateKeyboardEvent(None, keycode, False)
    if down and up:
        AS.CGEventPost(AS.kCGHIDEventTap, down)
        AS.CGEventPost(AS.kCGHIDEventTap, up)


def send_unicode_char(char):
    down = AS.CGEventCreateKeyboardEvent(None, 0, True)
    up = AS.CGEventCreateKeyboardEvent(None, 0, False)
    if down and up:
        AS.CGEventKeyboardSetUnicodeString(down, len(char), char)
        AS.CGEventKeyboardSetUnicodeString(up, len(char), char)
        AS.CGEventPost(AS.kCGHIDEventTap, down)
        AS.CGEventPost(AS.kCGHIDEventTap, up)


def extract_cursor_index(focused_el):
    err, range_val = AS.AXUIElementCopyAttributeValue(
        focused_el, AS.kAXSelectedTextRangeAttribute, None
    )
    if err != 0 or not range_val:
        return 0
    try:
        success, cf_range = AS.AXValueGetValue(
            range_val, AS.kAXValueCFRangeType, None
        )
        if success:
            if isinstance(cf_range, (tuple, list)):
                return int(cf_range[0])
            if hasattr(cf_range, 'location'):
                return int(cf_range.location)
    except Exception:
        pass
    try:
        if hasattr(range_val, 'rangeValue'):
            return int(range_val.rangeValue().location)
    except Exception:
        pass
    return 0


def get_focused_text_and_cursor():
    app = NSWorkspace.sharedWorkspace().frontmostApplication()
    if not app:
        return "", 0, None
    pid = app.processIdentifier()
    if pid <= 0:
        return "", 0, None

    app_el = AS.AXUIElementCreateApplication(pid)
    err, focused = AS.AXUIElementCopyAttributeValue(
        app_el, AS.kAXFocusedUIElementAttribute, None
    )
    if err != 0 or not focused:
        return "", 0, None

    err, val = AS.AXUIElementCopyAttributeValue(
        focused, AS.kAXValueAttribute, None
    )
    if err != 0 or not val or not isinstance(val, str):
        return "", 0, focused

    cursor_pos = extract_cursor_index(focused)
    return val, cursor_pos, focused


def set_focused_cursor(focused_el, target_char_pos):
    if not focused_el:
        return
    try:
        range_val = AS.AXValueCreate(
            AS.kAXValueCFRangeType, (int(target_char_pos), 0)
        )
        if range_val:
            AS.AXUIElementSetAttributeValue(
                focused_el, AS.kAXSelectedTextRangeAttribute, range_val
            )
    except Exception:
        pass


def wrap_and_locate(text, cursor_pos):
    lines = text.split('\n')
    wrapped_lines = []
    line_offsets = []
    active_row = 0
    active_col = 0
    char_count = 0
    found_caret = False

    for line in lines:
        if not line:
            if not found_caret and char_count >= cursor_pos:
                active_row = len(wrapped_lines)
                active_col = 0
                found_caret = True
            wrapped_lines.append("")
            line_offsets.append((char_count, 0))
            char_count += 1
            continue

        for i in range(0, len(line), 32):
            chunk = line[i:i + 32]
            start = char_count
            end = start + len(chunk)
            if not found_caret and (
                start <= cursor_pos <= end
                or (i + 32 >= len(line) and cursor_pos == end)
            ):
                active_row = len(wrapped_lines)
                active_col = min(31, max(0, cursor_pos - start))
                found_caret = True
            wrapped_lines.append(chunk)
            line_offsets.append((start, len(chunk)))
            char_count += len(chunk)
        char_count += 1

    return wrapped_lines, active_row, active_col, line_offsets


class MonarchDaemon:
    def __init__(self, path, vid, pid):
        self.device = hid.device()
        if path:
            self.device.open_path(path)
        else:
            self.device.open(vid, pid)
        self.device.set_nonblocking(True)
        self.prev_display_state = None
        self.view_top = 0
        self.prev_keys = 0
        self.active_chord = 0
        self.held_dpad_bit = 0
        self.held_dpad_since = 0.0
        self.last_dpad_repeat = 0.0
        self.line_offsets = []
        self.current_focused_el = None

    def update_display(self, screen_lines, cursor_row, cursor_col):
        new_state = []
        frames = []
        for r in range(8):
            line_text = screen_lines[r] if r < len(screen_lines) else ""
            line_bytes = []
            for c in range(32):
                ch = line_text[c] if c < len(line_text) else ' '
                cell = ASCII_TO_BRAILLE.get(ch, 0x00)
                if r == cursor_row and c == cursor_col:
                    cell |= 0xC0
                line_bytes.append(cell)
            new_state.append(tuple(line_bytes))
            frames.append((0x31 + r, line_bytes))

        if new_state != self.prev_display_state:
            for report_id, data in frames:
                self.device.write([report_id] + data)
            self.prev_display_state = new_state

    def route_to_cell(self, row, col):
        if not self.line_offsets or not self.current_focused_el:
            return
        target_line_idx = self.view_top + row
        if 0 <= target_line_idx < len(self.line_offsets):
            start_idx, line_len = self.line_offsets[target_line_idx]
            target_char_pos = start_idx + min(line_len, col)
            set_focused_cursor(self.current_focused_el, target_char_pos)

    def handle_braille_chord(self, chord):
        if chord == 0x100:
            send_unicode_char(' ')
            return

        dots = chord & 0xFF
        if dots == 0x40:
            send_virtual_key(51)  # Backspace
        elif dots == 0x80:
            send_virtual_key(36)  # Return
        elif dots in BRAILLE_TO_ASCII:
            send_unicode_char(BRAILLE_TO_ASCII[dots])

    def handle_held_dpad(self):
        if not self.held_dpad_bit:
            return
        if not (self.prev_keys & self.held_dpad_bit):
            self.held_dpad_bit = 0
            return
        now = time.time()
        if (now - self.held_dpad_since) > 0.4 and (now - self.last_dpad_repeat) > 0.06:
            keycode = RIGHT_DPAD_KEYCODES.get(self.held_dpad_bit)
            if keycode is not None:
                send_virtual_key(keycode)
                self.last_dpad_repeat = now

    def process_incoming_reports(self):
        while True:
            report = self.device.read(64)
            if not report:
                break
            report_id = report[0]
            payload = report[1:]

            if report_id == 0x41 and len(payload) >= 32:
                for byte_idx in range(min(32, len(payload))):
                    byte_val = payload[byte_idx]
                    if byte_val:
                        for bit_idx in range(8):
                            if byte_val & (1 << bit_idx):
                                cell_idx = byte_idx * 8 + bit_idx
                                touch_row = cell_idx // 32
                                touch_col = cell_idx % 32
                                self.route_to_cell(touch_row, touch_col)
                                break
                        break

            elif report_id == 0x20 and len(payload) >= 3:
                raw_bits = payload[0] | (payload[1] << 8) | (payload[2] << 16)
                just_pressed = raw_bits & (~self.prev_keys)
                self.prev_keys = raw_bits

                typing_bits = raw_bits & 0x1FF
                if typing_bits:
                    self.active_chord |= typing_bits
                elif self.active_chord:
                    self.handle_braille_chord(self.active_chord)
                    self.active_chord = 0

                if just_pressed & (1 << 9):
                    self.view_top = max(0, self.view_top - 8)
                elif just_pressed & (1 << 10):
                    max_top = max(0, len(self.line_offsets) - 8)
                    self.view_top = min(max_top, self.view_top + 8)

                for bitmask, keycode in RIGHT_DPAD_KEYCODES.items():
                    if just_pressed & bitmask:
                        send_virtual_key(keycode)
                        self.held_dpad_bit = bitmask
                        self.held_dpad_since = time.time()
                        self.last_dpad_repeat = self.held_dpad_since
                        break

    def run(self):
        try:
            while True:
                NSRunLoop.currentRunLoop().runUntilDate_(
                    NSDate.dateWithTimeIntervalSinceNow_(0.03)
                )
                self.process_incoming_reports()
                self.handle_held_dpad()
                text, cursor_pos, focused_el = get_focused_text_and_cursor()
                self.current_focused_el = focused_el
                if text:
                    wrapped, active_row, active_col, offsets = wrap_and_locate(
                        text, cursor_pos
                    )
                    self.line_offsets = offsets
                    total_lines = len(wrapped)

                    if active_row < self.view_top:
                        self.view_top = max(0, active_row - 1)
                    elif active_row >= self.view_top + 8:
                        self.view_top = max(0, active_row - 6)

                    self.view_top = min(self.view_top, max(0, total_lines - 8))

                    screen = wrapped[self.view_top:self.view_top + 8]
                    c_row = (
                        active_row - self.view_top
                        if 0 <= active_row - self.view_top < 8
                        else -1
                    )
                    c_col = active_col if c_row != -1 else -1

                    self.update_display(screen, c_row, c_col)
        except KeyboardInterrupt:
            for r in range(8):
                self.device.write([0x31 + r] + [0x00] * 32)
            self.device.close()


if __name__ == "__main__":
    path, vid, pid = find_monarch()
    if not path and not vid:
        sys.exit(1)
    daemon = MonarchDaemon(path, vid, pid)
    daemon.run()