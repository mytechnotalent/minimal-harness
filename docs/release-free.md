# Free Release Pipeline

SavrenAI ships through GitHub Releases at zero cost: public-repository
GitHub Actions runners build all three platforms on every `v*` tag and
attach the archives to a release. No signing certificates are involved, so
the operating systems show their standard warnings for unverified software.

## Artifacts

Every release carries three archives:

- `SavrenAI-windows.zip` - Windows executable folder
- `SavrenAI-linux.zip` - Linux executable folder
- `SavrenAI-macos-<arch>.zip` - macOS app bundle (arm64 on Apple Silicon)

Each archive includes `.env.example` next to the executable. Rename it to
`.env` and fill in the provider settings before the first launch; the app
reads it from its own directory, so no terminal or environment editing is
needed.

## Building a release

```bash
git tag v0.1.0
git push origin v0.1.0
```

The workflow builds all three archives and attaches them to the release at
https://github.com/mytechnotalent/SavrenAI/releases. Locally,
`python scripts/build_release.py` reproduces the current platform's
archive.

## macOS: opening an unverified app

Gatekeeper shows "SavrenAI cannot be opened because it is from an
unidentified developer" because the app is unsigned. Two ways past it:

1. Right-click (or Control-click) the app in Finder, choose Open, then
   Open again in the dialog.
2. Or, once extracted: `xattr -cr /Applications/SavrenAI.app`

These steps are required once per downloaded version until the app is
signed with an Apple Developer certificate.

## Windows: opening an unverified app

SmartScreen shows "Windows protected your PC". Click "More info", then
"Run anyway". If Defender quarantines the archive or executable, restore
it from Windows Security history and report the false positive at
https://www.microsoft.com/en-us/wdsi/filesubmission. The one-directory
PyInstaller layout without UPX is used deliberately because it triggers
far fewer antivirus heuristics than single-file compressed builds.

## Linux

Extract the archive and run `./SavrenAI`. A Wayland or X11 session is
required for the desktop UI. The build targets `ubuntu-latest`; other
distributions usually work when the matching Qt system libraries are
present.

## What changes when you pay later

- macOS: a $99/year Apple Developer Program membership enables Developer
  ID signing and notarization, which removes the Gatekeeper warning
  entirely.
- Windows: an OV or EV code-signing certificate removes the SmartScreen
  warning and builds download reputation over time.

Neither changes the build pipeline; the same workflow gains two signing
steps. Nothing in this directory requires payment today.
