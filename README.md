# 宁波诺丁汉大学计算机系飞跃手册

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
