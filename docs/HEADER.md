# The RPG Maker MV/MZ encrypted file format

This is the technical reference for the on-disk format that `rpgmv_decrypter`
reads and writes. Everything on this page was derived from the Python source in
[`rpgmv_decrypter/decrypter.py`](../rpgmv_decrypter/decrypter.py) and reproduced
with real bytes (see [Reproducing the examples](#reproducing-the-examples)).

## 1. File layout

An encrypted resource file consists of three consecutive regions:

| Offset (bytes)      | Length         | Content                                                        |
| ------------------- | -------------- | -------------------------------------------------------------- |
| `0`                 | `header_len`   | **Fake header** — stored in the clear, identical for every file |
| `header_len`        | `header_len`   | `plaintext[0:header_len]` XOR `key[0:header_len]`                |
| `2 * header_len`    | rest of file   | `plaintext[header_len:]`, copied **byte for byte, untouched**    |

With the default `header_len = 16` this means: 16 bytes of fake header, then
16 encrypted bytes, then the rest of the original file as-is. The encrypted file
is therefore exactly `header_len` (16) bytes larger than the plain file.

```text
plain.png            [        16 plaintext bytes        ][ rest of the PNG ... ]
                     \_______________/                    \________________/
                              | XOR key                            | copied
                              v                                    v
encrypted.rpgmvp     [ fake header 16 ][ 16 xor-ed bytes ][ rest of the PNG ... ]
```

Only the **first** `header_len` bytes are modified. A 5 MiB audio file has
exactly 16 bytes of ciphertext in it.

## 2. The fake header

The fake header is built from three hex strings that are concatenated and then
parsed two characters (= one byte) at a time. The defaults come from the RPG
Maker core script (`Decrypter.SIGNATURE`, `Decrypter.VER`, `Decrypter.REMAIN`)
and are the constants `DEFAULT_SIGNATURE`, `DEFAULT_VERSION` and `DEFAULT_REMAIN`
in the library.

| Field       | Default value        | Hex chars | Bytes | Meaning                                |
| ----------- | -------------------- | --------- | ----- | -------------------------------------- |
| `SIGNATURE` | `5250474d56000000`   | 16        | 8     | ASCII `RPGMV` followed by 3 NUL bytes  |
| `VER`       | `000301`             | 6         | 3     | Format version `00 03 01`              |
| `REMAIN`    | `0000000000`         | 10        | 5     | Reserved, all zero                     |
| **total**   |                      | **32**    | **16**| `header_len`                           |

Concatenated: `5250474d560000000003010000000000`, which is the byte sequence

```text
52 50 47 4d 56 00 00 00 00 03 01 00 00 00 00 00
 R  P  G  M  V
```

The header is written **unencrypted**, which is why the tool can check whether a
file really is an RPG Maker encrypted file: `Decrypter.verify_fake_header()`
compares the first `header_len` bytes against the expected sequence.

## 3. The cipher

The encryption is a plain XOR of the first `header_len` plaintext bytes with the
first `header_len` bytes of the key. There is no block chaining, no key
schedule, no IV, and no encryption of the remainder.

```python
ciphertext[i] = plaintext[i] ^ key[i]          for 0 <= i < header_len
ciphertext[i] = plaintext[i]                   for i >= header_len
```

Encryption prepends the fake header; decryption drops it first and then XORs the
following block. Because XOR is an involution, the same operation both encrypts
and decrypts that block.

### Byte-level example

Key: `1234567890abcdef1234567890abcdef` (32 hex chars = 16 bytes).
Plaintext: a valid 2×2 RGB PNG, 74 bytes.

First 48 bytes of the plain file:

```text
0000  89 50 4e 47 0d 0a 1a 0a 00 00 00 0d 49 48 44 52   .PNG........IHDR
0010  00 00 00 02 00 00 00 02 08 02 00 00 00 fd d4 9a   ................
0020  73 00 00 00 11 49 44 41 54 78 da 63 f8 cf c0 00   s....IDATx.c....
```

First 48 bytes of the encrypted file (90 bytes = 74 + 16):

```text
0000  52 50 47 4d 56 00 00 00 00 03 01 00 00 00 00 00   RPGMV...........   <- fake header
0010  9b 64 18 3f 9d a1 d7 e5 12 34 56 75 d9 e3 89 bd   .d.?.....4Vu....   <- plain[0:16] ^ key
0020  00 00 00 02 00 00 00 02 08 02 00 00 00 fd d4 9a   ................   <- plain[16:] verbatim
```

Checking the second block by hand: `89 ^ 12 = 9b`, `50 ^ 34 = 64`,
`4e ^ 56 = 18`, `47 ^ 78 = 3f`, … and indeed
`9b64183f9da1d7e512345675d9e389bd` XOR `89504e470d0a1a0a0000000d49484452` =
`1234567890abcdef1234567890abcdef`, the key.

## 4. Recovering the key from an encrypted image

`Decrypter.get_key_from_png()` (the reference's `Decrypter.getKeyFromPNG`) uses
the fact that the first 16 bytes of *every* standard PNG are a well-known
constant (`NORMAL_PNG_HEADER`, `89504e470d0a1a0a0000000d49484452`) and that the
second header block is `plain[0:16] ^ key`:

```text
key = normal_png_header XOR encrypted[header_len : 2*header_len]
```

With the example file:

```text
9b 64 18 3f 9d a1 d7 e5 12 34 56 75 d9 e3 89 bd   encrypted[16:32]
89 50 4e 47 0d 0a 1a 0a 00 00 00 0d 49 48 44 52   normal PNG header
--------------------------------------------------   XOR
12 34 56 78 90 ab cd ef 12 34 56 78 90 ab cd ef   recovered key
```

Recovering a key this way needs nothing but the first 32 bytes of any encrypted
image of the project — no `System.json`, no `rpg_core.js`, no game files.

Caveats:

* At most the first 16 bytes of the key can be recovered (32 hex digits) — the
  real PNG header is only 16 bytes long. That is the whole key for the 16-byte
  keys RPG Maker generates; with a larger `header_len` only that prefix comes
  back.
* The file must actually be an encrypted **image**. The trick cannot work for
  `.rpgmvo`/`.rpgmvm`/`.ogg_`/`.m4a_` audio, because an OGG or M4A file does not
  start with a fixed 16-byte constant — for audio you need the key from another
  source (`System.json`, `rpg_core.js` or an encrypted image of the same project).

## 5. Restoring a PNG without the key

`Decrypter.restore_png_header_bytes()` needs no key. It drops the fake header
*and* the XOR-ed block and puts the standard PNG header back:

```text
restored = normal_png_header + encrypted[2*header_len:]      # header_len <= 16
```

Because the first 16 bytes of a conformant PNG *are* the standard PNG header
(PNG signature + the `IHDR` chunk length `00 00 00 0d` + the chunk type `IHDR`),
the original bytes are reconstructed exactly and the result is a valid, viewable
PNG. Nothing is lost in that case.

**Caveat:** the function always overwrites the first 16 bytes with the standard
PNG header. If the original file's first 16 bytes were something else (a
non-PNG payload, or a PNG that does not start with a standard `IHDR` chunk),
those 16 original bytes are unrecoverable without the key and the restored file
is *not* byte-identical to the original. The library docs and the CLI/GUI call
this operation "restore", not "decrypt", for exactly that reason.

`restore_png_header_bytes()` does **not** verify the fake header and does not
require a key. It works on any non-empty input: shorter inputs (fewer than
`2 * header_len` bytes) simply yield the standard PNG header alone, with nothing
appended.

## 6. Custom header values

Some games change the header values. The three hex strings and the header length
are constructor parameters of `Decrypter`, so both the check and the file layout
follow them:

```python
from rpgmv_decrypter import Decrypter

decrypter = Decrypter(
    "1234567890abcdef1234567890abcdef",
    header_len=16,                # Decrypter._headerlength
    signature="5250474d56000000", # Decrypter.SIGNATURE
    version="000301",             # Decrypter.VER
    remain="0000000000",          # Decrypter.REMAIN
)
```

Where to find the values in a game (search for `function Decrypter()`):

| Engine | File                      |
| ------ | ------------------------- |
| MV     | `www/js/rpg_core.js`      |
| MZ     | `js/rpg_core.js`          |

Constraints enforced by the code:

| Parameter       | Valid range / rule                                                            |
| --------------- | ----------------------------------------------------------------------------- |
| `header_len`    | positive integer. Bytes past the 32 hex digits of `signature` + `version` + `remain` (16 bytes with the defaults) are **zero** — the fake header is padded, exactly like the reference's `parseInt("0x")` → `NaN` → `0`. The key must be at least `header_len` bytes long, otherwise en-/decryption raises `InvalidKeyError`. `restore_png_*` handles at most 16 header bytes, so it is byte-exact only for `header_len <= 16`. |
| `signature`, `version`, `remain` | non-empty hex strings, no `0x` prefix. Only non-hex characters are rejected (on construction, with `ValueError`). An odd number of digits is accepted but desynchronises the two-character parsing of the concatenated string, so the resulting header differs from the intended one. |
| encryption key  | hex string; non-hex characters **or an odd number of digits** raise `InvalidKeyError` on construction. A key with fewer than `header_len` bytes raises `InvalidKeyError` as soon as it is used. Extra bytes beyond `header_len` are ignored. |

## 7. Reproducing the examples

The numbers on this page were produced by encrypting a generated 2×2 RGB PNG
with the key `1234567890abcdef1234567890abcdef`. The same result can be obtained
with the library alone:

```python
from rpgmv_decrypter import Decrypter

key = "1234567890abcdef1234567890abcdef"
plain = open("demo.png", "rb").read()

encrypted = Decrypter(key).encrypt_bytes(plain)
assert encrypted[:16].hex() == "5250474d560000000003010000000000"
assert encrypted[16:32] == bytes(a ^ b for a, b in zip(plain[:16], bytes.fromhex(key)))
assert encrypted[32:] == plain[16:]
assert Decrypter.get_key_from_png(encrypted) == key
assert Decrypter(None).restore_png_header_bytes(encrypted) == plain  # for a standard PNG
```

## See also

* [COMPATIBILITY.md](COMPATIBILITY.md) — what is supported, what is not, and the
  known caveats.
* [`INTERFACE.md`](../INTERFACE.md) — the frozen Python API contract.
* [`rpgmv_decrypter/decrypter.py`](../rpgmv_decrypter/decrypter.py) — the
  implementation, with the reference-implementation names in its docstrings.
