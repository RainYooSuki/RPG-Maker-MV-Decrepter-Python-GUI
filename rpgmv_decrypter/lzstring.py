"""LZ-String decompression.

RPG Maker MV/MZ projects that hide their encryption key sometimes ship
``System.json`` as an LZ-String compressed Base64 blob instead of plain JSON.
This is a direct port of ``LZString._decompress`` from pieroxy's lz-string 1.4.4
(the library the reference decrypter bundles), covering the flavours the
reference implementation can encounter:

* :func:`decompress_from_base64` - ``LZString.decompressFromBase64``
* :func:`decompress_from_encoded_uri_component` - ``decompressFromEncodedURIComponent``
* :func:`decompress_from_uint8_array` - ``LZString.decompressFromUint8Array``
  (UCS-2 big endian, 2 bytes per character)

Only decompression is implemented; the decrypter never needs to compress.

Details of the original that are reproduced deliberately, because getting any of
them wrong silently corrupts or truncates the output:

* The initial selector is **2 bits**, not 8.  It picks the first code's kind
  (0 = 8-bit character, 1 = 16-bit character, 2 = empty result) and is compared
  numerically against ``0``/``1``/``2``.
* Bits are read **least-significant bit of the value first**: ``power`` starts
  at 1, doubles each step and stops at ``2 ** count``.  The matching encoder
  writes each bit with ``data_val = (data_val << 1) | bit``, which places the
  stream's first bit in bit 0.  Reading most-significant first reverses bytes.
* Codes 0 and 1 store a *new literal* at ``dictionary[dictSize]`` and then set
  ``c = dictSize - 1`` - i.e. ``c`` becomes the **index** of the entry just
  added, which then resolves through ``dictionary[c]`` to the literal character.
* A truncated stream yields ``""`` - the reference checks ``data.index > length``
  twice, at the top of the loop and before each character read, and returns an
  empty string rather than a partial result.
* The reference's ``switch`` over the selector has **no default**.  A selector
  of 3 therefore leaves the first character ``undefined``; the main loop then
  fails its dictionary lookup.  JS quietly compares ``undefined`` against the
  numeric ``dictSize`` and returns ``null``, so the same input yields ``None``
  here.  (For two selector-3 payloads the real library even throws a TypeError;
  returning ``None`` is the safe equivalent for a corrupt stream.)
"""

from __future__ import annotations

from typing import Callable, Final

__all__ = [
    "KEY_STR_BASE64",
    "KEY_STR_URI_SAFE",
    "decompress_from_base64",
    "decompress_from_encoded_uri_component",
    "decompress_from_uint8_array",
]

#: ``keyStrBase64`` in lz-string (note the trailing ``=``).
KEY_STR_BASE64: Final[str] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="
#: ``keyStrUriSafe`` in lz-string.
KEY_STR_URI_SAFE: Final[str] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+-$"

#: ``baseReverseDic``; a character outside the alphabet maps to ``None``,
#: matching JS where the reverse lookup is ``undefined``.
BASE64_LOOKUP: Final[dict[str, int]] = {
    character: index for index, character in enumerate(KEY_STR_BASE64)
}
URI_SAFE_LOOKUP: Final[dict[str, int]] = {
    character: index for index, character in enumerate(KEY_STR_URI_SAFE)
}

_SURROGATE_HIGH_MIN = 0xD800
_SURROGATE_HIGH_MAX = 0xDBFF


def _decompress(
    length: int,
    reset_value: int,
    get_next_value: Callable[[int], int | None],
) -> str | None:
    """Port of ``LZString._decompress``.

    :param length: number of values :paramref:`get_next_value` can supply
    :param reset_value: initial bit mask; ``32`` for the 5/6-bit text alphabets,
        ``256`` for byte streams
    :param get_next_value: ``get_next_value(index) -> int | None``; ``None``
        stands in for JS ``undefined`` (a character outside the alphabet)
    :returns: the decompressed text, ``""`` for a truncated stream, or ``None``
        when the stream references an undefined dictionary entry
    """
    if length == 0:
        return ""

    # JS uses a sparse array where 0/1/2 temporarily hold the numbers 0/1/2.
    dictionary: dict[int, str] = {index: str(index) for index in range(3)}

    enlarge_in = 4
    dict_size = 4
    num_bits = 3
    last_bits = 0

    data: dict[str, int | None] = {
        "val": get_next_value(0),
        "position": reset_value,
        "index": 1,
    }
    result: list[str] = []
    entry = ""
    w = ""

    def read_bits(count: int) -> int:
        """Read ``count`` bits, filling the value from bit 0 upwards.

        Returns the value; callers that also need an 8/16-bit character read the
        wider value and then use ``last_bits``, mirroring the reference's reuse
        of a single ``bits`` variable.
        """
        nonlocal last_bits
        bits = 0
        power = 1
        max_power = 1 << count
        while power != max_power:
            value = data["val"]
            position = int(data["position"] or 0)
            resb = None if value is None else value & position
            data["position"] = position >> 1
            if data["position"] == 0:
                data["position"] = reset_value
                data["val"] = get_next_value(int(data["index"] or 0))
                data["index"] = int(data["index"] or 0) + 1
            if resb:
                bits |= power
            power <<= 1
        last_bits = bits
        return bits

    def to_character(code_unit: int) -> str:
        """``String.fromCharCode`` - one UTF-16 code unit, halves kept apart."""
        return chr(code_unit & 0xFFFF)

    def build_output() -> str:
        """``result.join('')`` with UTF-16 surrogate pairs recombined.

        JS strings hold lone surrogates happily and pair them up only when
        characters are combined; Python strings cannot round-trip an unpaired
        surrogate, so the pairing happens here instead.
        """
        text = "".join(result)
        if not any(
            _SURROGATE_HIGH_MIN <= ord(character) <= _SURROGATE_HIGH_MAX
            for character in text
        ):
            return text
        return text.encode("utf-16", "surrogatepass").decode("utf-16")

    def add_dictionary_entry(value: str) -> None:
        nonlocal dict_size
        dictionary[dict_size] = value
        dict_size += 1

    # --- initial selector (2 bits) ------------------------------------
    # The reference's switch has no default: selector 3 leaves `c` undefined,
    # which is modelled here as an empty first character plus an unknown code.
    selector = read_bits(2)
    if selector == 0:
        read_bits(8)
        character = to_character(last_bits)
    elif selector == 1:
        read_bits(16)
        character = to_character(last_bits)
    elif selector == 2:
        return ""
    else:
        character = ""

    dictionary[3] = character
    w = character
    result.append(character)

    # --- main loop ----------------------------------------------------
    while True:
        # Bounds guard: the reference returns "" for a truncated stream.
        if int(data["index"] or 0) > length:
            return ""

        c: int | None = read_bits(num_bits)

        if c == 0:
            read_bits(8)
            add_dictionary_entry(to_character(last_bits))
            c = dict_size - 1
            enlarge_in -= 1
        elif c == 1:
            read_bits(16)
            add_dictionary_entry(to_character(last_bits))
            c = dict_size - 1
            enlarge_in -= 1
        elif c == 2:
            return build_output()
        elif c == 3:
            # Code 3 is reserved; the reference has no case for it either.
            pass
        elif c is None:
            return None

        if enlarge_in == 0:
            enlarge_in = 1 << num_bits
            num_bits += 1

        # `if (dictionary[c])` - JS treats a falsy entry as "not found".  The
        # seeded "0"/"1"/"2" placeholders are truthy strings, so this only ever
        # diverges for a genuinely missing entry, which falls through.
        if dictionary.get(c):
            entry = dictionary[c]
        elif c == dict_size:
            entry = w + w[0] if w else ""
        else:
            return None

        result.append(entry)

        # Add w + entry[0] to the dictionary.
        add_dictionary_entry(w + (entry[0] if entry else ""))
        enlarge_in -= 1

        w = entry

        if enlarge_in == 0:
            enlarge_in = 1 << num_bits
            num_bits += 1


# ----------------------------------------------------------------------
# public flavours
# ----------------------------------------------------------------------
def decompress_from_base64(compressed: str | None) -> str | None:
    """``LZString.decompressFromBase64``.

    Note the reference's slightly surprising empty handling: ``None`` maps to
    ``""`` while an empty string maps to ``None``.  Reproduced as-is.
    """
    if compressed is None:
        return ""
    if compressed == "":
        return None

    def get_next_value(index: int) -> int | None:
        if index >= len(compressed):
            return None
        return BASE64_LOOKUP.get(compressed[index])

    return _decompress(len(compressed), 32, get_next_value)


def decompress_from_encoded_uri_component(compressed: str | None) -> str | None:
    """``LZString.decompressFromEncodedURIComponent``."""
    if compressed is None:
        return ""
    if compressed == "":
        return None
    # The reference only swaps spaces for "+"; it does not call
    # decodeURIComponent here, so neither do we.
    decoded = compressed.replace(" ", "+")

    def get_next_value(index: int) -> int | None:
        if index >= len(decoded):
            return None
        return URI_SAFE_LOOKUP.get(decoded[index])

    return _decompress(len(decoded), 32, get_next_value)


def decompress_from_uint8_array(compressed: bytes | bytearray | None) -> str | None:
    """``LZString.decompressFromUint8Array``.

    The reference converts every **two** bytes into one UCS-2 code unit
    (``big[i*2]*256 + big[i*2+1]``), joins those units into a string and then
    calls ``LZString.decompress`` on it.  That is why the bit mask here is
    ``32768`` (the 15-bit alphabet of :func:`LZString.decompress`) and not the
    ``32`` used by the Base64/URI flavours.
    """
    if compressed is None:
        return ""
    raw = bytes(compressed)
    if not raw:
        return None
    units = len(raw) // 2

    def get_next_value(index: int) -> int | None:
        if index >= units:
            return None
        return raw[index * 2] * 256 + raw[index * 2 + 1]

    return _decompress(units, 32768, get_next_value)
