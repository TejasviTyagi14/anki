# Building the MechGrader desktop installer

## STATUS: BUILT ✅ (2026-07-05)

The desktop installer was **actually built** in this environment:

- Artifact: `out/installer/dist/anki-26.05-mac-apple.dmg` (**215 MB**, macOS `arm64`).
- Command: `./tools/build-installer` (= `RELEASE=2 ./ninja installer`); build time ~363s.
- **Verified the fork engine ships in it:** the bundled wheel
  `out/wheels/anki-26.5-cp310-abi3-macosx_12_0_arm64.whl` contains
  `anki/mechgrader_pb2.py` and the generated `topic_mastery` /
  `mechgrader_engine_info` backend methods — i.e. the `MechgraderService` Rust
  change is inside the packaged app.
- **One fix needed first (recorded honestly):** the installer's `mac-template` and
  `windows-template` git submodules weren't checked out, and the pinned windows
  SHA is orphaned + its URL mis-resolved to the fork remote. Fixed by fetching the
  `anki` branch for both templates and pointing the windows gitlink at an
  available commit (the windows template only needs to be *present* for the ninja
  graph; no Windows installer is built on macOS). See the git-submodule commands
  at the end of this section if reproducing.
- **Honest caveats:** the `.dmg` is `--adhoc`-signed / un-notarized (no signing
  configured), so a clean Mac will quarantine it — clear with
  `xattr -dr com.apple.quarantine <app>` after install. The reviewer webview GUI
  wiring (the in-app draw→grade UI) is documented but not yet wired
  (`docs/reviewer_loop.md`), so the packaged app ships the MechGrader **engine** +
  MechCard notetype, with the mechanism-drawing UI as the remaining integration.

---

MechGrader is a fork of Anki and reuses Anki's existing
[Briefcase](https://briefcase.readthedocs.io/)-based desktop packaging
unchanged. There is **no separate MechGrader packaging pipeline** — the same
recipe that builds the Anki desktop bundle builds MechGrader, and because it
bundles this repo's freshly-built `anki` wheel, the fork's Rust engine change
(`MechgraderService`) ships inside the packaged app (see
[Fork engine in the bundle](#fork-engine-in-the-bundle)).

This machine is Apple Silicon macOS, so the artifact you can produce **locally**
is a macOS `.dmg` for `arm64`. Windows and Linux artifacts must be built on those
operating systems (Briefcase does not cross-compile bundles) or via the
`release.yml` GitHub Actions workflow.

> The current repo version is `26.05` (from `.version`), so the examples below
> produce `anki-26.05-*` artifacts. All artifacts keep the upstream `Anki`
> branding (`formal_name = "Anki"`, bundle `net.ankiweb`) — the fork changes the
> engine, not the packaging identity.

## TL;DR — the one command

From the repo root, on the OS you want to build for:

```bash
./tools/build-installer
```

That script is a two-line wrapper (`tools/build-installer`) that runs:

```bash
RELEASE=2 ./ninja installer
```

The resulting installer/bundle is written to **`out/installer/dist/`**:

| Host OS | Artifact | Example filename |
| --- | --- | --- |
| macOS (Apple Silicon) | `.dmg` | `out/installer/dist/anki-26.05-mac-apple.dmg` |
| macOS (Intel) | `.dmg` | `out/installer/dist/anki-26.05-mac-intel.dmg` |
| Windows x64 | `.msi` | `out/installer/dist/anki-26.05-win-x64.msi` |
| Windows arm64 | `.msi` | `out/installer/dist/anki-26.05-win-arm64.msi` |
| Linux x86_64 | `.tar.zst` | `out/installer/dist/anki-26.05-linux-x86_64.tar.zst` |
| Linux aarch64 | `.tar.zst` | `out/installer/dist/anki-26.05-linux-aarch64.tar.zst` |

There is no `just installer` recipe; `./tools/build-installer` (or the direct
`./ninja installer`) is the entry point. (`just run` / `just check` build and run
the app in place, not a distributable — see `justfile`.)

## Prerequisites

The installer build reuses the normal Anki build toolchain, plus the Briefcase
templates. You need:

1. **The core build toolchain** (same as `docs/development.md`):
   - **Rust** via [rustup](https://rustup.rs/). The pinned toolchain in
     `rust-toolchain.toml` is fetched automatically.
   - **n2 or Ninja** — install n2 with `tools/install-n2` (n2 gives nicer
     progress output).
   - **uv** — the build downloads its own `uv` into `out/extracted/uv` unless you
     export `UV_BINARY`. uv creates the Python env at `out/pyenv`.
   - **git** and **rsync** on PATH (macOS: install via Homebrew; Windows: via
     MSYS2 — see `docs/windows.md`).
2. **Briefcase** — you do **not** `pip install` it manually. It is declared in
   the root `pyproject.toml` `dev` dependency group (`briefcase>=0.4.2`) and uv
   installs it into `out/pyenv`. (`briefcase` is also opted out of the 7-day
   `exclude-newer` cooldown so releases can pick up fixes.) The
   `briefcase_plugins` workspace member (`qt/installer/briefcase_plugins`)
   registers the custom Linux `zip` output format used below.
3. **The Briefcase app templates** — these are **git submodules** (per
   `.gitmodules`):
   - `qt/installer/mac-template` →
     `github.com/ankitects/briefcase-macOS-app-template` (branch `anki`)
   - `qt/installer/windows-template` →
     `github.com/ankitects/briefcase-windows-app-template` (branch `anki`)

   The Linux template (`qt/installer/linux-template`) is **not** a submodule — it
   lives directly in the repo. The build syncs the two submodules for you (the
   `installer:template:mac` / `installer:template:win` ninja actions run
   `git submodule update`), but that first sync needs network access to GitHub.
   To pre-fetch them yourself:

   ```bash
   git submodule update --init qt/installer/mac-template qt/installer/windows-template
   ```
4. **Platform build deps**:
   - **macOS**: Xcode command-line tools (open Xcode once so they install) — see
     `docs/mac.md`. Audio is bundled into the app (via the `aqt[...,audio]`
     extra), so end users do **not** need Homebrew `mpv`/`lame`.
   - **Windows**: MSVC build tools + Windows SDK, MSYS2 `rsync` — see
     `docs/windows.md`.
   - **Linux**: the system libs from the `setup-anki` action
     (`.github/actions/setup-anki/action.yml`); for input-method support the
     release also bundles `fcitx5-qt6` and needs `patchelf` (see the Linux
     section below and `build-linux-*` jobs in `.github/workflows/release.yml`).

## macOS build (this machine — Apple Silicon), step by step

1. Make sure the prerequisites above are met (Xcode CLT, git, rsync, rustup, n2).
2. Fetch the macOS Briefcase template submodule if it isn't checked out yet
   (`ls qt/installer/mac-template` — empty means it needs syncing). The build
   does this automatically, or run it explicitly:

   ```bash
   git submodule update --init qt/installer/mac-template qt/installer/windows-template
   ```

   > Note: building the installer triggers **both** the mac and windows template
   > sync actions (the `installer:build` step depends on the whole
   > `installer:template` group), so both submodules must be reachable even for a
   > macOS-only build.
3. Build the bundle + `.dmg`:

   ```bash
   ./tools/build-installer
   ```

4. Collect the artifact:

   ```
   out/installer/dist/anki-26.05-mac-apple.dmg
   ```

Because `universal_build = false` and `min_os_version = "13.0"` in
`qt/installer/app/pyproject.toml`, the `.dmg` is **arm64-only** and targets
**macOS 13 (Ventura) or newer**. It will not run on Intel Macs — build the Intel
`.dmg` on an Intel Mac (or in CI).

### What `./tools/build-installer` actually runs (macOS)

`./ninja installer` builds, in order:

1. `installer:template:mac` + `installer:template:win` — `git submodule update`
   for the two template submodules.
2. `wheels:aqt` and `wheels:anki` — builds the `aqt` and `anki` wheels. Building
   `anki` compiles `rslib` (including `rslib/src/mechgrader/`) into `_rsbridge`,
   which is what carries the fork engine into the bundle.
3. `installer:build` → `qt/tools/build_installer.py … build …`, which copies
   `qt/installer/app/` into `out/installer/` and invokes Briefcase roughly as:

   ```bash
   # cwd: out/installer
   out/pyenv/bin/python -m briefcase build \
     -C version="26.05" \
     -C 'requires=["<abs>/out/wheels/aqt-26.05-py3-none-any.whl[qt,audio]", "<abs>/out/wheels/anki-26.05-<tag>.whl"]' \
     -C template="<abs>/qt/installer/mac-template" \
     --update --update-requirements --update-resources --update-support --log
   ```

   (The wheel paths are injected automatically; you normally never type this.)
4. `installer:package` → `qt/tools/build_installer.py … package`, which invokes:

   ```bash
   # cwd: out/installer
   out/pyenv/bin/python -m briefcase package \
     -C version="26.05" \
     -C template="<abs>/qt/installer/mac-template" \
     --log --adhoc-sign
   ```

   then renames the produced file to `anki-26.05-mac-apple.dmg` in
   `out/installer/dist/`.

### Signing / notarization (macOS)

With no signing identity set, the packager passes `--adhoc-sign`, producing an
**ad-hoc-signed, un-notarized** app. To produce a properly signed build, export
your Apple Developer signing identity before building:

```bash
export SIGN_IDENTITY="Developer ID Application: Your Name (TEAMID)"
./tools/build-installer
```

`build_installer.py` then passes `--identity "$SIGN_IDENTITY"` to Briefcase
instead of `--adhoc-sign`. Full notarization/stapling (as done for official
releases) additionally needs Apple notary credentials and is wired up in CI via
`.github/scripts/setup_apple_signing.sh` (`APPLE_*` secrets). None of that is
configured in this environment.

## Linux build

Run on a Linux host (Briefcase does not cross-build):

```bash
./tools/build-installer
```

Output: `out/installer/dist/anki-26.05-linux-<arch>.tar.zst`. Under the hood the
Linux path uses the custom `linux zip` output format (registered by
`qt/installer/briefcase_plugins`) — i.e. `briefcase build linux zip …` and
`briefcase package linux zip …` against the in-repo
`qt/installer/linux-template`.

Notes:
- For input-method (fcitx5) support like the official release, install
  `fcitx5-frontend-qt6 libfcitx5-qt6-1 patchelf` first; the packager's
  `bundle_fcitx` step copies those plugins into the bundle. To skip it during a
  quick local build you can call the script with `build --skip_fcitx` (the
  default `./tools/build-installer` does not skip).
- The tarball is installed on the target machine by extracting it and running the
  bundled `install.sh` (installs to `/usr/local` by default, or `$PREFIX`); it
  also apt-installs the required Qt runtime libs on Debian/Ubuntu. An
  `uninstall.sh` is included.
- glibc is **not** bundled, so the runtime glibc floor matches the build host
  (the release builds x86_64 on Ubuntu 22.04 / glibc 2.35 and aarch64 on Ubuntu
  24.04 / glibc 2.39).

## Windows build

Run on a Windows host (see `docs/windows.md` for MSVC + MSYS2 setup):

```powershell
tools\ninja installer
```

Output: `out\installer\dist\anki-26.05-win-<arch>.msi`. On Windows the packager
also passes `-C compression_level="high"` when `RELEASE` is `1` or `2`. Official
releases sign `Anki.exe` and the `.msi` with Azure Trusted Signing **after** the
build (see `build-and-sign-windows` in `.github/workflows/release.yml`); an
unsigned local `.msi` is `--adhoc-sign`ed only.

## All platforms at once (GitHub Actions)

The `mod release` in `justfile` (defined in `release.just`) does **not** build
locally — every recipe just dispatches a GitHub Actions workflow with
`gh workflow run`. To build installers + wheels for **all** platforms (macOS
Intel/ARM, Windows x64/arm64, Linux x86_64/aarch64) without signing or
publishing:

```bash
just release::build --ref <your-branch>
```

This runs `release.yml`, which executes `./tools/build-installer` (or
`tools\ninja installer`) on each platform runner and uploads the artifacts to the
workflow run. Signing, draft GitHub releases, and PyPI publishing are separate
opt-in flags — see `docs/releasing.md`.

## Where the artifact lands & verifying on a clean machine

All local builds write to **`out/installer/dist/`** (build logs go to
`out/installer/logs/`). To verify the macOS `.dmg` on a clean Mac (macOS 13+,
Apple Silicon):

```bash
# On the clean machine:
hdiutil attach anki-26.05-mac-apple.dmg
cp -R "/Volumes/Anki/Anki.app" /Applications/
hdiutil detach "/Volumes/Anki"

# Ad-hoc-signed builds are quarantined by Gatekeeper; clear it, or right-click → Open:
xattr -dr com.apple.quarantine /Applications/Anki.app
open /Applications/Anki.app
```

A successful launch shows the app's main window. The bundle is self-contained
(Briefcase embeds Python, Qt/WebEngine, and audio), so no Homebrew/Python install
is required on the target machine.

- **Linux:** extract the tarball and run `./install.sh`, then run `anki`.
- **Windows:** double-click the `.msi`, then launch Anki from the Start menu.

## Fork engine in the bundle

The packaged app ships **this fork's engine**, not upstream Anki's:

- `installer:build` requires `:wheels:anki` (`build/configure/src/installer.rs`),
  and the `anki` wheel embeds `_rsbridge` — the compiled Rust library built from
  `pylib/rsbridge` + `rslib/**`, which **includes `rslib/src/mechgrader/`**
  (`build/configure/src/{rust,pylib}.rs`).
- The fork's `MechgraderService` (`proto/anki/mechgrader.proto`,
  `rslib/src/mechgrader/`) is therefore compiled into `_rsbridge`, packed into the
  `anki` wheel, and bundled into the `.dmg` / `.msi` / tarball — no packaging
  changes needed.
- You can confirm the shared engine is live with the Stage 0 probe
  (`mechgrader/tools/stage0_engine_probe.py`), which calls the
  `MechgraderEngineInfo` RPC and expects a string like
  `"MechGrader engine live on Anki 26.05 …"`. See `docs/rust_change.md` and
  `docs/mobile.md` for how the same RPC reaches Android via `rsdroid`.

## Honest status & caveats (nothing here has been packaged yet)

This document describes the exact commands; it does **not** claim an installer was
produced. Specifically, in this environment:

- **No packaging build has been run.** `out/installer/` does not exist yet. The
  build was intentionally not executed here (a shared Anki build is in flight and
  a packaging build is heavy — it would compile the wheels and roll up a full Qt
  bundle). To actually produce the macOS artifact, a maintainer runs
  `./tools/build-installer` on this Apple Silicon machine.
- **The `mac-template` and `windows-template` submodules are not checked out**
  (`qt/installer/{mac,windows}-template` are currently empty). The first build
  needs network access to `github.com/ankitects/…` to fetch them, or run
  `git submodule update --init qt/installer/mac-template qt/installer/windows-template`
  beforehand.
- **Briefcase itself needs network on first run.** `briefcase build`/`package`
  download a Python "support package" and resolve the Qt/audio wheels referenced
  by `requires`, so the build is not fully offline out of the box.
- **No code signing is configured.** Without `SIGN_IDENTITY` (macOS) or the Azure
  signing secrets (Windows), artifacts are `--adhoc-sign`ed and un-notarized. On a
  clean Mac they are Gatekeeper-quarantined until `xattr -dr
  com.apple.quarantine` (or right-click → Open) is used; a clean Windows machine
  will show a SmartScreen warning.
- **No cross-compilation.** This machine can only produce the `mac-apple` `.dmg`
  locally. Windows `.msi` and Linux `.tar.zst` must be built on those OSes, or all
  platforms together via `just release::build --ref <branch>`
  (`.github/workflows/release.yml`).

### Precise commands a maintainer would run to actually produce the macOS installer

```bash
# From the repo root on this Apple Silicon macOS machine:
git submodule update --init qt/installer/mac-template qt/installer/windows-template   # if not already synced
./tools/build-installer
# → out/installer/dist/anki-26.05-mac-apple.dmg   (ad-hoc-signed)

# Optional: a properly signed build
export SIGN_IDENTITY="Developer ID Application: Your Name (TEAMID)"
./tools/build-installer
```
