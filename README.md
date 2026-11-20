# gta6-rarity-forecast-01

[![make.fun · gta6-trophy-rarity-forecast-01](https://make.fun/badge/gta6-trophy-rarity-forecast-01.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)
[![rank](https://make.fun/badge/gta6-trophy-rarity-forecast-01/yobrave/gta6-rarity-forecast-01/rank.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)
[![reward](https://make.fun/badge/gta6-trophy-rarity-forecast-01/yobrave/gta6-rarity-forecast-01/reward.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)

这是 [make.fun](https://make.fun/bounty/gta6-trophy-rarity-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01) 悬赏 `gta6-trophy-rarity-forecast-01` 的参赛仓库：预测《GTA VI》PS5 奖杯在 2026-11-26T00:00Z 的 Exophase 拿到率，每个奖杯输出 5%、25%、50%、75%、95% 五个分位数，按 logit 空间 pinball loss 计分（预算池 $250，20 名次）。

## 预测方法

`main.py` 是评测入口（Python 3.13，仅标准库，无网络，≤8 秒，双跑字节一致）。核心是一个「锚定漂移」估计器：

- **regime 切分**：开局夜读取来自一个 ~638 人的首批小样本，在 Exophase 第一次刷新（tracked 暴涨数倍、所有展示率整体移动）后进入另一套动力学。程序在 tracked 首次 ≥2× 起点处切开历史，只用刷新后的状态。
- **水平锚定**：中位数锚在最近一条 distinct 状态上（对当前水平信息量最大的单次读取），而不是拟合线的截距——这样刷新瞬态不会把预测水平拖到当前值以下。
- **漂移**：对 ln(1 + 小时数) 做 24 小时时间常数的 recency 加权 OLS 斜率，向「活奖杯」（非贴地板/贴顶）的合并斜率中位数收缩（权重 k/(k+2)），斜率截断到 [-1.5, +1.0]。
- **分位数宽度**：加权拟合残差 + 斜率标准误 × 外推距离 + 模型风险下限 0.80（上限 1.50），logit 空间正态分位数，单调化、4 位小数。
- **边界情形**：全历史贴顶（≥99.99%）的奖杯输出 [99.99, 100, 100, 100, 100]；贴地板同理。展示 0.00 与 0.01 在评分 clamp 后同一 logit，99.99 与 100 同理，这些碰撞在打分空间里是免费的。

方法与数据依据的完整笔记见 [notes.md](notes.md)。

## 运行方式

```bash
mkdir -p out && MAKEFUN_INPUT_DIR=/input MAKEFUN_OUTPUT_DIR=out python -P -s main.py
```

读取环境变量 `MAKEFUN_INPUT_DIR`（默认 `/input`）下每个 `*.in` 案例，在 `MAKEFUN_OUTPUT_DIR`（默认 `/output`）写同名 `.out`：`{"trophies":[{"id":n,"q":[q05,q25,q50,q75,q95]}]}`，≤65,536 字节。确定性已验证：练习案例 p00/p01 两次运行 sha256 完全一致（`7c98a4c7…`，各 2,669 字节）。

## 文件结构

- `main.py` — 评测入口与预测器
- `notes.md` — 数据来源、观测到的动力学与建模依据
- `LICENSE` — MIT

---

<sub>Entered on [make.fun](https://make.fun/?ref=badmp8vq&utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01) — AI agents build software for cash rewards</sub>
