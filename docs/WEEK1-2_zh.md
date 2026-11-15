# 第 1–2 周操作指南：采集层 + Bronze 层

每一步都有一个 ✅ 检查点，通过了再往下走。

---

## 第 1 步：准备账号（今天就做）

1. **AEMET API key**：打开 https://opendata.aemet.es/centrodedescargas/altaUsuario ，填邮箱，邮件里会收到 key。
2. **Databricks Free Edition**：注册后进入 workspace。
3. **GitHub**：新建一个公开仓库 `spain-energy-data-platform`，先不要勾选自动生成 README。

✅ 检查点：手上有 AEMET key，能登进 Databricks。

---

## 第 2 步：本地环境

```bash
cd spain-energy-data-platform
python -m venv .venv
source .venv/bin/activate          # Windows 用 .venv\Scripts\activate
pip install -e ".[dev,databricks]"
cp .env.example .env               # 然后用编辑器打开 .env，填入 AEMET_API_KEY
pytest -q                          # 应该看到 13 passed
```

然后推到 GitHub：

```bash
git init && git add . && git commit -m "Initial ingestion package and Bronze notebook"
git branch -M main
git remote add origin https://github.com/ningtia/spain-energy-data-platform.git
git push -u origin main
```

✅ 检查点：GitHub 的 Actions 页面里 CI 变成绿色。

> 推之前跑一下 `git status`，确认 `.env` **没有**出现在列表里。

---

## 第 3 步：验证真实接口（最重要的一步）

代码里的 REE 接口名是按公开文档写的，**一定要先用一天的数据试一遍**：

```bash
energy-ingest -v ree --dataset market_prices --start 2025-01-01 --end 2025-01-01
energy-ingest -v ree --dataset demand        --start 2025-01-01 --end 2025-01-31
energy-ingest -v ree --dataset generation_mix --start 2025-01-01 --end 2025-01-31
energy-ingest -v aemet --station 3195        --start 2025-01-01 --end 2025-01-31
```

打开 `data/landing/` 下生成的 JSON 文件看一下：

- **REE**：`payload.included` 里每一项是一个指标（比如现货价格、PVPC），`attributes.values` 是时间序列。记下每个指标的 `title`，第 3 周写 Silver 要用。
- **AEMET**：每一行是一天，字段有 `fecha`、`tmed`（平均温度）、`tmin`、`tmax`、`prec`。注意数字是逗号小数（"8,4"）。

**如果 REE 报错**（比如 widget 不存在或者日期范围太长）：
- 在浏览器里直接打开这个地址看返回什么：
  `https://apidatos.ree.es/en/datos/mercados/precios-mercados-tiempo-real?start_date=2025-01-01T00:00&end_date=2025-01-01T23:59&time_trunc=hour`
- 改 `src/energy_platform/config.py` 里的 `widget` 名或者 `chunk_days`，不用动别的代码。

✅ 检查点：四条命令都成功，JSON 里有数据。

---

## 第 4 步：回填历史数据

```bash
energy-ingest ree   --start 2018-01-01 --end 2026-11-14
energy-ingest aemet --start 2018-01-01 --end 2026-11-14
```

- REE 价格按 7 天一段请求，8 年大约 450 次请求，几分钟到十几分钟。
- AEMET 有限流，代码每次请求间隔 1.5 秒，5 个站点 × 约 105 段，大约 15–20 分钟。中途断了**直接重跑同一条命令**就行，文件名是固定的，不会产生重复（这就是“幂等”，面试可以讲）。

✅ 检查点：`data/landing/ree/` 和 `data/landing/aemet/` 下都有完整年份的文件夹。

---

## 第 5 步：建 Databricks 结构

1. 在 Databricks 左侧 **Workspace → Import**，导入 `databricks/notebooks/` 里的两个文件。
2. 打开 `00_setup.sql`，连接 Serverless，点 **Run all**。
   - 如果 `CREATE CATALOG` 报权限错误：把文件里的 `energy` 全部换成 `workspace`，`.env` 里的 `DATABRICKS_VOLUME_PATH` 也改成 `/Volumes/workspace/raw/landing`。
3. 在左侧 **Catalog** 里应该能看到 `raw / bronze / silver / gold` 四个 schema。

✅ 检查点：Catalog 里能看到 `raw.landing` 这个 volume。

---

## 第 6 步：上传 + 跑 Bronze

1. 生成 token：右上角头像 → **Settings → Developer → Access tokens → Generate**。填进 `.env` 的 `DATABRICKS_TOKEN`，`DATABRICKS_HOST` 填浏览器地址栏里 workspace 的网址。
2. 上传：
   ```bash
   energy-ingest upload
   ```
3. 在 Databricks 打开 `01_bronze_ingest.py`，**Run all**。最后一个单元格会显示每个数据集的文件数和日期范围。
4. **再跑一次**这个 notebook，行数应该不变（Auto Loader 只处理新文件）。

✅ 检查点：`bronze.ree_raw` 和 `bronze.aemet_raw` 两张表有数据，重跑不增加行数。

---

## 第 7 步：收尾

- 更新 README 里的 Status 和 Roadmap 打勾。
- 在 Databricks 里对 Bronze 结果截一张图，放进 `docs/img/`，在 README 里引用。
- commit + push。

---

## 这两周要搞懂的概念（面试会问）

| 概念 | 一句话解释 | 在项目里的位置 |
|---|---|---|
| 幂等（idempotent） | 同一个操作跑多少次，结果都一样 | `landing.py` 的固定文件名 |
| 重试 + 指数退避 | 失败后等 2s、4s、8s 再试 | `http.py` |
| Landing / Bronze | 原始数据原样保存，不做解析 | `01_bronze_ingest.py` |
| Auto Loader + checkpoint | 记住哪些文件已经处理过，只读新文件 | `cloudFiles` + `checkpointLocation` |
| `availableNow` 触发 | 用流处理的方式做批处理：处理完现有文件就停 | `01_bronze_ingest.py` |
| 回看窗口 | 每天重拉最近 7 天，因为数据会被修正、AEMET 有延迟 | `cli.py` 的 `daily` |
| 密钥管理 | key 放 `.env`，不进 Git，也不写进数据文件 | `.gitignore`、`test_aemet.py` |

---

## 遇到问题时

把**完整的报错信息**和**运行的命令**发给我。第 3 周我们写 Silver：解析 JSON、处理时区和夏令时、去重、算人口加权温度。
