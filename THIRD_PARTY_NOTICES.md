# Third-party notices

Stutterbox source is released under the MIT License in `LICENSE`. The Windows
package also redistributes the components below. Versions describe the v0.2.0
release build.

| Component | Version | License | Purpose |
| --- | --- | --- | --- |
| Python | 3.12.11 | PSF License | Embedded Python runtime |
| PySide6, PySide6 Addons, PySide6 Essentials, Shiboken6 | 6.11.1 | LGPL-3.0-only, with GPL and commercial alternatives offered upstream | Qt application framework and Python bindings |
| mss | 10.2.0 | MIT | Screen capture |
| NumPy | 2.4.6 | BSD-3-Clause and bundled component licenses | Frame arrays and image operations |
| Pillow | 12.2.0 | MIT-CMU | PNG encoding and decoding |
| PyInstaller | 6.21.0 | GPL-2.0-or-later with the PyInstaller bootloader exception | Windows packaging bootloader |
| OpenSSL | 3.0.16 | Apache-2.0 | TLS support included with the frozen runtime |

The Windows package uses the community Qt for Python distribution under
LGPL-3.0. Qt and PySide shared libraries remain separate under
`Stutterbox/_internal/PySide6`, allowing replacement with interface-compatible
builds. Stutterbox does not modify those libraries. Qt for Python source and
licensing information are available from:

- https://code.qt.io/cgit/pyside/pyside-setup.git/
- https://doc.qt.io/qtforpython-6/
- https://doc.qt.io/qtforpython-6/licenses.html

The Windows ZIP includes full license texts under `Stutterbox/LICENSES`. NumPy
also retains its component notices under
`Stutterbox/_internal/numpy-2.4.6.dist-info/licenses`.

Microsoft Visual C++ runtime files supplied with Python and Qt are also present
in the Windows package. Their redistribution remains subject to Microsoft's
applicable runtime terms.
