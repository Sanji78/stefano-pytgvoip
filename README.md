# pytgvoip
 
[![Read the Docs](https://img.shields.io/readthedocs/pytgvoip.svg)](https://pytgvoip.rtfd.io) [![PyPI](https://img.shields.io/pypi/v/pytgvoip.svg?style=flat)](https://pypi.org/project/pytgvoip/) [![AppVeyor (windows wheels)](https://img.shields.io/appveyor/ci/bakatrouble/pylibtgvoip.svg?label=windows%20wheels%20build&style=flat)](https://ci.appveyor.com/project/bakatrouble/pylibtgvoip) ![LGPLv3+](https://img.shields.io/pypi/l/pytgvoip.svg?style=flat)
 
**Telegram VoIP Library for Python**

[Community](https://t.me/pytgvoip) | [Documentation](https://pytgvoip.rtfd.io)

**PytgVoIP** is a [Telegram](https://telegram.org/) VoIP library written in Python and C++.

It uses [libtgvoip](https://github.com/grishka/libtgvoip) (a library used in official clients) 
for voice encoding and transmission, and [pybind11](https://github.com/pybind/pybind11) for simple 
generation of Python extension written in C++.

It is targeted to MTProto client library developers, detailed usage guide is available [here](https://pytgvoip.readthedocs.io/en/latest/guides/usage.html).

An example of usage with [Pyrogram](https://github.com/Sanji78/stefano-pyrogram) is available [here](https://github.com/Sanji78/stefano-pytgvoip-pyrogram) ([`pytgvoip_pyrogram` in PyPI](https://pypi.org/project/pytgvoip_pyrogram/)), could be used as reference.

## Features
* Python callbacks for sending and receiving audio stream frames allow flexible control
* Pre-built Windows wheels in PyPI

## Requirements
* Python 3.5 or higher

Linux, MacOS: (use binary wheels from PyPI for Windows)
* [libtgvoip](https://pytgvoip.readthedocs.io/en/latest/guides/libtgvoip.html)
* CMake, C++11-compatible compiler, Python headers

## Installing
```pip3 install pytgvoip```

Install [`pytgvoip_pyrogram`](https://github.com/Sanji78/stefano-pytgvoip-pyrogram) to use this module with Pyrogram.


## Encoding audio streams
Streams consumed by `libtgvoip` should be encoded in 16-bit signed PCM audio.
```bash
$ ffmpeg -i input.mp3 -f s16le -ac 1 -ar 48000 -acodec pcm_s16le input.raw  # encode
$ ffmpeg -f s16le -ac 1 -ar 48000 -acodec pcm_s16le -i output.raw output.mp3  # decode
```

---

## ❤️ Donate
If this project helps you, consider buying me a coffee:  
**[PayPal](https://www.paypal.me/elenacapasso80)**.

..and yes... 😊 the paypal account is correct. Thank you so much!

---

## 📜 License
[MIT](LICENSE.md)
