# SeaTable to 飞跃手册 PDF Pipeline

该项目从 SeaTable 获取学生申请数据，自动完成数据关联、清洗和排版，为每名学生生成一份个人 PDF，同时生成用于汇总全部学生 PDF 的 `main.tex`。


## 项目结构


- `.env`：保存本地 API Token。
- `config.json`：Pipeline 配置。
- `pipeline.py`：核心程序。
- `run.ps1`：PowerShell 启动脚本。
- `.venv`：Python 虚拟环境。
- `generated/individual/`：个人 PDF。
- `generated/assets/`：从 SeaTable 下载的富文本图片。
- `generated/manifest.json`：学生和 PDF 对照表。
- `generated/quality_report.json`：数据质量报告。
- `generated/main.tex`：飞跃手册总册 TeX。
- `generated/main.pdf`：XeLaTeX 编译后的最终总册。



## 运行

在项目目录创建 `.env`：

```dotenv
SEATABLE_API_TOKEN=你的只读_API_Token
```

在 `config.json`中配置参数，如  "term": "2026 Fall" 

然后在 PowerShell 中运行：

```powershell
cd "项目目录"
.\run.ps1
```


运行后在 `generated/` 下生成：

- `individual/name.pdf`：按 SeaTable 的 `name` 字段命名，每名学生一份 PDF；
- `manifest.json`：学生、地区、学校、项目和 PDF 路径，供总册自动分区；
- `main.tex`：沿用指定飞跃手册模板；每个地区标题下先插入“学校 × 届别”的 Offer 数量统计表（Admit + Chosen），再按“学校 → 项目 → 学生”填充个人 PDF；
- `quality_report.json`：缺失值、关联异常、图片错误及总页数；
- `assets/`：从 SeaTable 富文本下载的图片。
