# Third-Party Notices

## Portable distribution inventory

The application's own source remains Apache-2.0. Bundled dependencies retain
their own terms; this document does not relicense them. The portable build keeps
upstream LICENSE / LICENCE / COPYING / NOTICE / COPYRIGHT files byte-for-byte:

- `third-party-notices/notice-inventory.json`: installed Python runtime closure,
  PyInstaller bootloader notice, Python interpreter, Node and application.
- `openclaw/notice-inventory.json`: published npm dependency notices, kept at
  their original package-relative paths even when `.md`/`.txt` assets are slimmed.

Both inventories bind relative paths, byte counts and SHA-256; package
verification rejects missing, changed, duplicate or escaping records. These are
notice-preservation checks, not a complete license-compliance certification or
a substitute for any required source/offer and redistribution review.

### PyQt distribution decision remains open

The installed PyQt6 6.10.2 wheel declares `GPL-3.0-only`; the PyQt6-Qt6 wheel
declares LGPL v3. Riverbank describes GPL and commercial PyQt licensing in its
[official introduction](https://www.riverbankcomputing.com/software/pyqt) and
[commercial-license FAQ](https://riverbankcomputing.com/commercial/license-faq).
No commercial entitlement has been assumed or acquired. Before publishing a
binary, the maintainer must settle the GPL-compatible distribution or commercial
licensing route and review the corresponding obligations. Development/testing
continues; the repository license and GUI toolkit are not changed implicitly.

## ECGFounder

The optional ECGFounder waveform sidecar interoperates with the ECGFounder
model and model architecture published by PKUDigitalHealth. The model weights
are not included in the DICOM Overlay Agent desktop bundle and must be obtained
separately from the upstream project.

Source: https://github.com/PKUDigitalHealth/ECGFounder

MIT License

Copyright (c) 2025 PKUDigitalHealth

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
