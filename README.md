# 宁波诺丁汉大学计算机系飞跃手册

## Get Started

### Setup Environment

Create a new conda environment or proceed with your existing Python interpreter:

```bash
conda create -n feiyue-docs python=3.11
conda activate feiyue-docs
```

Install required dependencies:

```bash
python3 -m pip install -r requirements.txt
```

### Build

Build Feiyue Docs using the following command:

```bash
python3 feiyue/maker.py --api-key <seatable-api-token>
```

- `seatable-api-token` is used for [authenticating SeaTable API requests](https://api.seatable.com/reference/authentication); contact Feiyue Team to obtain one.
