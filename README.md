# 诺丁汉大学计算机系飞跃手册

The project builds the UoN Feiyue Docs site, empowering current and future Computer Science students with a more convenient way to access the docs and prepare for their Master/PhD applications. The site is built using [Materials for MkDocs](https://squidfunk.github.io/mkdocs-material/), with all application data stored in an online database, [SeaTable](https://cloud.seatable.io/dtable/external-links/custom/UNNC-feiyue/).

## Statements

### Disclaimer

- This document is the result of a voluntary effort by a group of graduating students from the School of Computer Science at the University of Nottingham Ningbo China (UNNC). All views regarding graduate program applications expressed herein are solely those of the individual contributors and do not represent any political position, nor the views of the Feiyue Team, the School, or the University. Readers are advised to engage with this material critically.
- To protect privacy to the greatest extent possible, contributors were permitted to anonymize or selectively disclose certain information. However, the Feiyue Team cannot fully guarantee the security of all personal data or prevent its misuse for commercial or other purposes.

### Copyright Notice

Copyright &copy; 2025 UNNC Feiyue Team. All rights reserved.

No organization or individual may edit, modify, reproduce, or distribute this document, in whole or in part, through any means or channels without prior permission of the Feiyue Team. Commercial use of this document is strictly prohibited.

The design of this site and its underlying database was inspired by the [THU-feiyue](https://github.com/THU-feiyue) and [Open CS Application](https://opencs.app). All application-related content, including data, personal experiences, and sharing, was independently authored and contributed by participating students.

## Get Started

Install required dependencies:

```bash
python3 -m pip install -r requirements.txt
```

Build using the following command:

```bash
python3 feiyue/maker.py --api-key <seatable-api-token> [--source <cloud|cache>]
```

- `api-key` is used for [authenticating SeaTable API requests](https://api.seatable.com/reference/authentication); contact Feiyue Team for one.
- `source` is set to `cache` by default, which means it will use cached database from the last build without the need to fetch from SeaTable again. For official deployment builds, set it to `cloud` manually. 

The `feiyue/maker.py` script will generate all required files to serve the MkDocs site under `output/` of your current working directory. To test and preview the docs, use the following command:

```bash
cd output
mkdocs serve
```

Some useful tutorials and resources:

- MkDocs: [Getting Started](https://squidfunk.github.io/mkdocs-material/getting-started/) and [Setup](https://squidfunk.github.io/mkdocs-material/setup/)
- SeaTable: [API Introduction](https://api.seatable.com/reference/introduction)
