# Compatibility

What this project reads and writes, what it deliberately does not do, and the
caveats that matter in practice.

## Supported engines and formats

| Engine       | Encrypted image | Plain image | Encrypted audio (Ogg) | Plain audio | Encrypted audio (M4A) | Plain audio |
| ------------ | --------------- | ----------- | --------------------- | ----------- | --------------------- | ----------- |
| RPG Maker MV | `.rpgmvp`       | `.png`      | `.rpgmvo`             | `.ogg`      | `.rpgmvm`             | `.m4a`      |
| RPG Maker MZ | `.png_`         | `.png`      | `.ogg_`               | `.ogg`      | `.m4a_`               | `.m4a`      |

MV and MZ use the **same** cipher and the same 16-byte header; only the file
extensions differ. The engine therefore only selects the encrypted extension used
for output names (`--rpg-maker MV|MZ` on the CLI, the **Encrypt for MV** /
**Encrypt for MZ** buttons in the GUI) — it never changes the cryptography.
`guess_version_for_extension()` additionally infers the engine from an encrypted
extension (a trailing `_` means MZ).

| Operation          | Accepted extensions                                 | Needs a key |
| ------------------ | --------------------------------------------------- | ----------- |
| `decrypt`          | `.rpgmvp` `.rpgmvm` `.rpgmvo` `.png_` `.ogg_` `.m4a_` | yes         |
| `encrypt`          | `.png` `.ogg` `.m4a`                                | yes         |
| `restore` (no key) | `.rpgmvp` `.png_`                                   | **no**      |

Files with any other extension are skipped with a reason, never silently
processed and never a hard failure.

## Supported inputs

* Single files, and directories that are walked recursively (or with
  `recursive=False` / `--no-recursive`, or the GUI's **Include sub-folders**
  checkbox, for one level).
* Mixed lists of files and directories; one bad file never aborts a batch — every
  input produces exactly one `FileOutcome`.
* Paths with spaces and non-ASCII characters.
* ZIP archives **at the library level**: `api.read_input_bytes()` reads the first
  matching member of a `.zip`, `api.iter_zip_members()` yields all of them, and
  `api.make_zip()` / `api.write_zip()` bundle results. See the interface notes
  below for what the CLI and GUI expose.

Directories named `node_modules`, `.git`, `.svn`, `__macosx`, `save` and `saves`
are never walked into.

## Key detection

`detect_key()` tries these sources, in this order (see `DETECT_STRATEGIES` in
[`rpgmv_decrypter/key_detect.py`](../rpgmv_decrypter/key_detect.py)):

| # | Strategy            | Source                                                            |
| - | ------------------- | ----------------------------------------------------------------- |
| 1 | `encrypted-image`   | key recovered from the header block of a `.rpgmvp` / `.png_` file |
| 2 | `json`              | `"encryptionKey"` in a plain `System.json`                        |
| 3 | `lzstring`          | `"encryptionKey"` in an LZ-String Base64 compressed `System.json` |
| 4 | `rpg-core`          | `this._encryptionKey = "..."` in `rpg_core.js`                    |
| 5 | `rpg-core-lzstring` | the same scan over an LZ-String compressed `rpg_core.js`          |

For a **directory** the search starts at `System.json`
(`www/data/System.json` for MV, `data/System.json` for MZ), then `rpg_core.js`
(`www/js/rpg_core.js`, `js/rpg_core.js`), then any encrypted image found
recursively.

### Not supported: an indirectly assigned key

If `rpg_core.js` does not contain the key as a literal string, no static tool can
read it. The detector recognises the pattern and keeps it deliberately
unresolved:

```js
// rpg_core.js
this._encryptionKey = someVariable;          // -> not found
this._encryptionKey = decrypt("...");        // -> not found
```

In that case `DetectResult.found` is `False`, `DetectResult.key` is `None`, and
`DetectResult.detail` says that the key "is not stored as a plain string (it is
assigned indirectly or obfuscated), so it cannot be read statically". Nothing is
guessed and no bogus key is returned.

#### Alternative: read the key out of the running game

The reference project ships a small browser snippet for exactly this case:
[`readKeyFromGame.js`](https://github.com/Petschko/RPG-Maker-MV-Decrypter/blob/master/readKeyFromGame.js)
(also present in the local copy of the reference project if you have it).

1. Open the game's `www/js/rpg_core.js` (MV) or `js/rpg_core.js` (MZ) and paste
   the whole content of `readKeyFromGame.js` at the **very end** of the file.
2. Start the game. The snippet overrides `Decrypter.decryptArrayBuffer`, verifies
   the fake header of the first encrypted resource it is asked to load, calls the
   core's `readEncryptionkey()` and shows the key in a `window.prompt` dialog.
3. Copy the key and feed it to this tool (CLI `--key`, GUI key field).
4. **Remove the snippet again** — the file's own comment asks for that, and the
   overridden function makes the game fail to load its resources afterwards.

Notes: the snippet refuses to run when the fake header check fails
(`throw new Error("Header is wrong")`), so for a game with custom header values
you must copy those values into `rpg_core.js`'s `Decrypter.SIGNATURE` / `VER` /
`REMAIN` first. The key it prints is the concatenation of the first
`Decrypter._headerlength` two-character chunks of `Decrypter._encryptionKey`,
i.e. the 32 hex digits of a standard RPG Maker key. This Python project does not
implement or test that snippet; it is the original author's tool.

## Known caveats

| Caveat | Detail |
| ------ | ------ |
| Only the first 16 bytes are encrypted | The rest of the file is copied verbatim, so the format hides almost nothing. This is RPG Maker's format, not a design decision of this tool. |
| Decryption is fully reversible | `decrypt(encrypt(plain)) == plain` and `encrypt(decrypt(encrypted)) == encrypted`, byte for byte. You can edit a decrypted asset and re-encrypt it to get a file the game accepts — see [HEADER.md](HEADER.md). |
| A standard PNG restore is byte-exact | The first 16 bytes of every conformant PNG are the same constant, and `restore_png_header_bytes()` writes exactly that constant back, so the original bytes are reconstructed exactly. |
| A non-standard restore loses 16 bytes | If the file's first 16 bytes are not the standard PNG header, `restore` overwrites them and they cannot be recovered without the key. Hence "restore", not "decrypt". |
| `restore` does not verify the fake header | It works on any non-empty input (a file shorter than 32 bytes yields the bare PNG header) and a wrong input produces a wrong output rather than an error. |
| Audio cannot be restored without a key | Only PNG images start with a fixed 16-byte constant, so the no-key trick is impossible for `.rpgmvo`/`.rpgmvm`/`.ogg_`/`.m4a_`. |
| Only 16 bytes of the key are used | Keys shorter than `header_len` are rejected (`InvalidKeyError`); extra key bytes beyond `header_len` are ignored, so any key with the same first 16 bytes works. |
| Odd-length hex keys are rejected | The library raises `InvalidKeyError` on construction ("must have an even number of hex characters"); the CLI and GUI report the same thing before calling it. |
| `header_len` above 16 is zero-padded | The fake header is `signature + version + remain` parsed two digits at a time; bytes past the 32 hex digits (16 bytes) are zero, matching the reference where `parseInt("0x")` is `NaN` → `0`. Such a header is meaningless for a real game, and the key must be at least `header_len` bytes long. `restore_png_*` handles at most 16 header bytes, so it is byte-exact only for `header_len <= 16` (verified for 8, 12 and 16). |
| A header mismatch is not proof of corruption | RPG Maker games may use custom header values. Turn the header check off (`ignore_fake_header=True`, `--ignore-fake-header`, or clear the GUI's **Verify fake header** checkbox) and retry — after making sure the file really is encrypted. |
| LZ-String is decompression only | `rpgmv_decrypter.lzstring` ports `_decompress` (Base64, URI-component and byte flavours). The tools never need to compress, so no compressor is implemented. |
| Lone UTF-16 surrogates are rejected | A crafted LZ-String payload can decompress to unpaired surrogate code units. JavaScript strings hold those happily; Python strings cannot round-trip them, so `decompress_from_base64` raises `UnicodeDecodeError` instead of returning a string that would break JSON parsing and printing. Real `System.json` payloads contain valid UTF-8/UTF-16 text, so this only affects malicious or corrupt input. |
| A wrong key is not detected by `decrypt` | The fake header does not depend on the key, so decryption never fails on a wrong key: only the first 16 plaintext bytes come out wrong, everything from byte 16 on is always correct. If a decrypted image does not open, suspect the key. |
| Key detection trusts the file extension | The `encrypted-image` strategy XORs the second header block with the standard PNG header. Point it at a plain file that merely ends in `.rpgmvp`/`.png_` and you get a meaningless key back instead of "not found". Check with `info` that the file really is encrypted. |

## Not implemented (out of scope)

* RPG Maker XP / VX / VX Ace formats (`Data/*.rxdata`, RGSSAD archives) — this
  tool only handles the MV/MZ resource encryption.
* Unpacking or patching game executables (`.exe`), and any kind of DRM removal.
* Brute-forcing keys. Keys longer than 16 bytes cannot be recovered in full from
  an encrypted image (only the first 16 bytes are); use `System.json` or
  `rpg_core.js` for those.
* Re-compressing files into LZ-String.
* Any network access: the CLI, the library and the desktop GUI never use the
  network. The GUI is a local Qt window — no server, no port, no analytics.

## Interface notes

* **CLI** — see the "Command line" section of the [README](../README.md). The CLI
  walks directories and accepts the extensions listed above. A `.zip` passed as an
  explicit path is reported as **SKIPPED** (unsupported extension) and does not
  fail the run; `--zip PATH` only *writes* an archive.
* **GUI** — see the "Desktop GUI (PySide6)" section of the [README](../README.md).
  It is a local PySide6 window: no server, no address to open, no network access.
* **Library** — `Decrypter.decrypt_stream()` / `encrypt_stream()` avoid holding a
  whole audio file in memory; the batch API (`decrypt_paths`, `encrypt_paths`,
  `restore_png_paths`) processes one file at a time.

## Verified environment

Everything in this repository was verified with the bundled virtual environment:
**Python 3.12.9** on Windows, with `pyside6-essentials` 6.11.2 (the desktop GUI,
imported as `PySide6`) and `pytest` 9.1.1 (the test suite) installed. The
`rpgmv_decrypter` package itself imports only the Python standard library, so the
CLI and the library run anywhere Python 3.10+ is available.
