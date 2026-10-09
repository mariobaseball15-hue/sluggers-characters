"""Messages in dt_na.dat dir 121's encoding (the game's text tables): encode_message / decode_message. Their own module
so code outside the stadium builder (the CPU levels menu, the bench) uses them without importing new_stadium, which
pulls in the stadium modules (the Characters Beta ships none of them)."""
import struct

MSG_LINE = 20                       # stock explanation lines are 20 characters at most


def encode_message(text, width=MSG_LINE):
    """A message in dir 121's encoding: UTF-16BE with printable ASCII as fullwidth forms (U+FF01..FF5E),
    space 0x0020, Latin-1 letters as themselves (the French / Spanish tables' accents), line break 0x000D,
    ending 0x0000. A line over `width` is split at the space that best
    balances it (then wrapped at `width` if still too long)."""
    import textwrap
    lines = []
    for line in text.split("\n"):
        if len(line) > width and " " in line:
            cut = min((i for i, c in enumerate(line) if c == " "), key=lambda i: max(i, len(line) - i - 1))
            parts = [line[:cut], line[cut + 1:]]
            lines += parts if max(map(len, parts)) <= width else textwrap.wrap(line, width)
        else:
            lines.append(line)
    out = bytearray()
    for n, line in enumerate(lines):
        if n:
            out += b"\x00\x0d"
        for ch in line:
            assert ch == " " or "!" <= ch <= "~" or 0xA0 <= ord(ch) <= 0xFF, f"message character {ch!r}"
            out += struct.pack(">H", ord(ch) + 0xFEE0 if "!" <= ch <= "~" else ord(ch))
    return bytes(out) + b"\0\0"


def decode_message(data):
    """encode_message's inverse (other codes shown as <XXXX>), up to the first 0x0000."""
    out = []
    for i in range(0, len(data) - 1, 2):
        v = struct.unpack_from(">H", data, i)[0]
        if v == 0:
            break
        out.append(chr(v - 0xFEE0) if 0xFF01 <= v <= 0xFF5E else " " if v == 0x20 else "\n" if v == 0x0D
                   else chr(v) if 0xA0 <= v <= 0xFF else f"<{v:04X}>")
    return "".join(out)
