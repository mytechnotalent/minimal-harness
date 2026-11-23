# Free Release Pipeline

SavrenAI ships through GitHub Releases at zero cost: public-repository
GitHub Actions runners build both platforms on every `v*` tag and attach
the archives to a release. No signing certificates are involved, so the
operating systems show their standard warnings for unverified software.

## Building a release

```bash
git tag v0.1.0
git push origin v0.1.0
```

The workflow builds `SavrenAI-macos.zip` and `SavrenAI-windows.zip` and
attaches them to the release at
https://github.com/mytechnotalent/SavrenAI/releases. Locally,
`python scripts/build_release.py` reproduces the current platform's
archive (ad-hoc signed on macOS).

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

## What changes when you pay later

- macOS: a $99/year Apple Developer Program membership enables Developer
  ID signing and notarization, which removes the Gatekeeper warning
  entirely.
- Windows: an OV or EV code-signing certificate removes the SmartScreen
  warning and builds download reputation over time.

Neither changes the build pipeline; the same workflow gains two signing
steps. Nothing in this directory requires payment today.
