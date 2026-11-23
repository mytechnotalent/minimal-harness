# Free Release Pipeline

SavrenAI ships through GitHub Releases at zero cost: public-repository
GitHub Actions runners build the Windows app on every `v*` tag and attach
the archive to a release. No signing certificates are involved, so Windows
shows its standard warning for unverified software.

## Building a release

```bash
git tag v0.1.0
git push origin v0.1.0
```

The workflow builds `SavrenAI-windows.zip` and attaches it to the release at
https://github.com/mytechnotalent/SavrenAI/releases. Locally,
`python scripts/build_release.py` reproduces the archive on Windows.

## Windows: opening an unverified app

SmartScreen shows "Windows protected your PC". Click "More info", then
"Run anyway". If Defender quarantines the archive or executable, restore
it from Windows Security history and report the false positive at
https://www.microsoft.com/en-us/wdsi/filesubmission. The one-directory
PyInstaller layout without UPX is used deliberately because it triggers
far fewer antivirus heuristics than single-file compressed builds.

## What changes when you pay later

An OV or EV code-signing certificate removes the SmartScreen warning and
builds download reputation over time. It does not change the build
pipeline; the same workflow gains one signing step. Nothing in this
directory requires payment today.
