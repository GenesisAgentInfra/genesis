# Third-party notices

Original Genesis source uses Apache-2.0. Third-party code keeps its own license;
Apache-2.0 does not relicense it. The lockfiles (`uv.lock`,
`viewer/package-lock.json`) record exact versions and the full dependency tree.

This file ships in the `genesis-ci` wheel, beside `LICENSE` and `NOTICE`.
`packages/genesis_ci/THIRD_PARTY_NOTICES.md` is that copy; `scripts/check_packages.py`
fails when it differs from this file.

The wheels bundle no Python packages. typer, libcst, pydantic and their dependencies
are installed separately under their own licenses.

## What the viewer page contains

`genesis map render` writes `view.html` (or `view.share.html` with `--share`) from
one page built from `viewer/`. The built file,
`packages/genesis_ci/src/genesis_ci/assets/viewer/index.html`, ships in the
`genesis-ci` wheel. It contains code from these packages, which `viewer/src` imports:

| Package | License |
| --- | --- |
| react, react-dom | MIT |
| @xyflow/react | MIT |
| @base-ui/react | MIT |
| commit-graph | MIT (see below) |
| clsx | MIT |
| tailwind-merge | MIT |
| tailwindcss | MIT |
| tw-animate-css | MIT |
| class-variance-authority | Apache-2.0 |
| lucide-react | ISC |
| motion | MIT |

Through them, the page also contains:

- scheduler, use-sync-external-store, @xyflow/system, zustand, classcat,
  @base-ui/utils, @floating-ui/react-dom, @floating-ui/dom, @floating-ui/core,
  @floating-ui/utils, framer-motion, motion-dom and motion-utils (MIT);
- d3-zoom, d3-drag, d3-selection, d3-transition, d3-interpolate, d3-color,
  d3-dispatch and d3-timer (ISC);
- d3-ease (BSD-3-Clause).

commit-graph is published as one prebuilt file that already contains code from
react-tooltip, reactjs-popup, react-infinite-scroller, classnames, prop-types,
@floating-ui/dom and react-icons (all MIT). From react-icons it carries three icons:
Plus and Minus from Feather (MIT) and Pencil Fill from Remix Icon (Apache-2.0, as
react-icons lists it). commit-graph's `package.json` and README say MIT; the `LICENSE`
file in the package is the Apache License 2.0 text with no copyright line filled in.
Both licenses' texts are in this file and in `LICENSE`.

Other material in the page:

- The viewer's Base UI Luma components come from
  [shadcn/ui](https://github.com/shadcn-ui/ui) (MIT).
- The page embeds the [Geist Mono](https://github.com/vercel/geist-font) font under
  the SIL Open Font License 1.1.
- `viewer/src/components/graphical/` is the component runtime exported from
  [Graphical](https://www.graphicalui.com/), and `viewer/graphical/generated/` holds
  the CSS its installer wrote. `lib/dialkit-color.ts` in that folder is adapted from
  [DialKit](https://github.com/joshpuckett/dialkit) 2.0 (MIT). This code is compiled
  into the page.
- The build tools add a few lines of their own runtime code: a module-preload check
  from Vite (`vite`) and a module runtime from Rolldown (`rolldown`), both MIT.
- The GitHub mark, a trademark of GitHub, is the icon of links to GitHub.

Every page built from `viewer/` carries this whole file in a comment at the top of its
head, after which come the shadcn/ui and Geist Mono notices from `viewer/index.html`. So
a `view.html` or `view.share.html` passed on alone still carries its notices. The build
copies this file in and fails when a package whose code ends up in the page is not
named here; after changing this file, run `npm run build` in `viewer/` and commit the
rebuilt page.

## License texts

### MIT License

Applies to the packages named below, each with its copyright notice.

```text
react, react-dom, scheduler, use-sync-external-store:
Copyright (c) Meta Platforms, Inc. and affiliates.

prop-types:
Copyright (c) 2013-present, Facebook, Inc.

@xyflow/react, @xyflow/system:
Copyright (c) 2019-2025 webkid GmbH

zustand:
Copyright (c) 2019 Paul Henschel

classcat:
Copyright © Jorge Bucaran <<https://jorgebucaran.com>>

@base-ui/react, @base-ui/utils:
Copyright (c) 2019 Material-UI SAS

@floating-ui/react-dom, @floating-ui/dom, @floating-ui/core, @floating-ui/utils:
Copyright (c) 2021-present Floating UI contributors

motion, motion-dom, motion-utils:
Copyright (c) 2024 [Motion](https://motion.dev) B.V.

framer-motion:
Copyright (c) 2018 Framer B.V.

react-tooltip:
Copyright (c) 2022 ReactTooltip Team Github

reactjs-popup:
Copyright (c) 2017

react-infinite-scroller:
Copyright (c) 2016 Dan Bovey
Copyright (c) 2013 guillaumervls

classnames:
Copyright (c) 2018 Jed Watson

react-icons:
Copyright 2018 kamijin_fanta <kamijin@live.jp>

Feather icons (in lucide-react and react-icons):
Copyright (c) 2013-present Cole Bemis

clsx:
Copyright (c) Luke Edwards <luke.edwards05@gmail.com> (lukeed.com)

tailwind-merge:
Copyright (c) 2021 Dany Castillo

tailwindcss:
Copyright (c) Tailwind Labs, Inc.

tw-animate-css:
Copyright (c) 2025 Wombosvideo

vite:
Copyright (c) 2019-present, VoidZero Inc. and Vite contributors

rolldown:
Copyright (c) 2024-present VoidZero Inc. & Contributors

DialKit (adapted in viewer/src/components/graphical/lib/dialkit-color.ts):
Copyright (c) 2026 Josh Puckett

shadcn/ui:
Copyright (c) 2023 shadcn
```

```text
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
```

### ISC License

```text
lucide-react:
Copyright (c) 2026 Lucide Icons and Contributors

d3-zoom, d3-drag, d3-selection, d3-transition, d3-interpolate, d3-color,
d3-dispatch, d3-timer:
Copyright 2010-2026 Mike Bostock
```

```text
Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted, provided that the above
copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
```

### BSD-3-Clause

d3-ease:

```text
Copyright 2010-2026 Mike Bostock
Copyright 2001 Robert Penner
All rights reserved.

Redistribution and use in source and binary forms, with or without modification,
are permitted provided that the following conditions are met:

* Redistributions of source code must retain the above copyright notice, this
  list of conditions and the following disclaimer.

* Redistributions in binary form must reproduce the above copyright notice,
  this list of conditions and the following disclaimer in the documentation
  and/or other materials provided with the distribution.

* Neither the name of the author nor the names of contributors may be used to
  endorse or promote products derived from this software without specific prior
  written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```

### Apache License 2.0

Applies to class-variance-authority (Copyright 2022 Joe Bell), the Remix Icon icon and
the `LICENSE` file of commit-graph. The full text is `LICENSE`, beside this file.

### SIL Open Font License 1.1

Geist Mono:

```text
Copyright (c) 2023 Vercel, in collaboration with basement.studio

This Font Software is licensed under the SIL Open Font License, Version 1.1.
This license is copied below, and is also available with a FAQ at:
http://scripts.sil.org/OFL

-----------------------------------------------------------
SIL OPEN FONT LICENSE Version 1.1 - 26 February 2007
-----------------------------------------------------------

PREAMBLE
The goals of the Open Font License (OFL) are to stimulate worldwide
development of collaborative font projects, to support the font creation
efforts of academic and linguistic communities, and to provide a free and
open framework in which fonts may be shared and improved in partnership
with others.

The OFL allows the licensed fonts to be used, studied, modified and
redistributed freely as long as they are not sold by themselves. The
fonts, including any derivative works, can be bundled, embedded,
redistributed and/or sold with any software provided that any reserved
names are not used by derivative works. The fonts and derivatives,
however, cannot be released under any other type of license. The
requirement for fonts to remain under this license does not apply
to any document created using the fonts or their derivatives.

DEFINITIONS
"Font Software" refers to the set of files released by the Copyright
Holder(s) under this license and clearly marked as such. This may
include source files, build scripts and documentation.

"Reserved Font Name" refers to any names specified as such after the
copyright statement(s).

"Original Version" refers to the collection of Font Software components as
distributed by the Copyright Holder(s).

"Modified Version" refers to any derivative made by adding to, deleting,
or substituting -- in part or in whole -- any of the components of the
Original Version, by changing formats or by porting the Font Software to a
new environment.

"Author" refers to any designer, engineer, programmer, technical
writer or other person who contributed to the Font Software.

PERMISSION AND CONDITIONS
Permission is hereby granted, free of charge, to any person obtaining
a copy of the Font Software, to use, study, copy, merge, embed, modify,
redistribute, and sell modified and unmodified copies of the Font
Software, subject to the following conditions:

1) Neither the Font Software nor any of its individual components,
in Original or Modified Versions, may be sold by itself.

2) Original or Modified Versions of the Font Software may be bundled,
redistributed and/or sold with any software, provided that each copy
contains the above copyright notice and this license. These can be
included either as stand-alone text files, human-readable headers or
in the appropriate machine-readable metadata fields within text or
binary files as long as those fields can be easily viewed by the user.

3) No Modified Version of the Font Software may use the Reserved Font
Name(s) unless explicit written permission is granted by the corresponding
Copyright Holder. This restriction only applies to the primary font name as
presented to the users.

4) The name(s) of the Copyright Holder(s) or the Author(s) of the Font
Software shall not be used to promote, endorse or advertise any
Modified Version, except to acknowledge the contribution(s) of the
Copyright Holder(s) and the Author(s) or with their explicit written
permission.

5) The Font Software, modified or unmodified, in part or in whole,
must be distributed entirely under this license, and must not be
distributed under any other license. The requirement for fonts to
remain under this license does not apply to any document created
using the Font Software.

TERMINATION
This license becomes null and void if any of the above conditions are
not met.

DISCLAIMER
THE FONT SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO ANY WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT
OF COPYRIGHT, PATENT, TRADEMARK, OR OTHER RIGHT. IN NO EVENT SHALL THE
COPYRIGHT HOLDER BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
INCLUDING ANY GENERAL, SPECIAL, INDIRECT, INCIDENTAL, OR CONSEQUENTIAL
DAMAGES, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF THE USE OR INABILITY TO USE THE FONT SOFTWARE OR FROM
OTHER DEALINGS IN THE FONT SOFTWARE.
```
