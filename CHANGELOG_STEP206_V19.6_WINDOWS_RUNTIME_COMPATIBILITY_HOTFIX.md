# Step206 V19.6 Windows Runtime Compatibility Hotfix

## Failure fixed

The verified offline installation completed dependency resolution and `pip check`, but the final scientific import gate failed while importing `ont_fast5_api`:

`ModuleNotFoundError: No module named 'pkg_resources'`

`ont-fast5-api 4.1.3` imports `pkg_resources` at runtime to locate its bundled VBZ HDF5 plugin. The previously bundled `setuptools 83.0.0` no longer contains that module.

## Changes

- Replaced the bundled `setuptools 83.0.0` wheel with `setuptools 80.9.0`, which retains the required compatibility module.
- Updated the hashed Windows offline lock, wheelhouse SHA-256 manifest, and wheelhouse metadata.
- Added a fail-closed Step206 runtime compatibility verifier covering `pkg_resources`, all V19.6 scientific adapters, `ont_fast5_api`, and FAST5 VBZ plugin registration.
- Wired the verifier into environment reuse, post-install qualification, `RUN_BOTH_WINDOWS.bat`, install/run verification, and the online fallback bootstrap.
- Hardened the wheelhouse gate so a future incompatible `setuptools 83.x` wheel cannot pass release verification.
- Added regression tests for the installer, launcher, lock, wheel metadata, and wheel contents.

## User workflow

Extract all five matching hotfixed ZIP parts into one new empty folder, run `INSTALL_WINDOWS.bat`, and then run `RUN_BOTH_WINDOWS.bat` or the installed BioIntel AI shortcut.
