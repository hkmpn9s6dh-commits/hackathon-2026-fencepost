# SPEC · 《Fencepost》（赛道 V · Cortensor Hackathon #5）

> 闸 A 的交付物。过了闸 A，范围只删不加。

## 0. 官方评分表（逐字，来自 `docs.cortensor.network/.../hackathon-5`）

| 权重 | 条目 |
|---|---|
| **25%** | Working functionality and useful outcome |
| **20%** | Meaningful OpenMinion SDK usage |
| **20%** | Reproducibility and demo quality |
| **25%** | **Building-block findings and improvement feedback** |
| **10%** | Relevance to Cortensor builder workflows |

Bonus：「For bug-fix bonus consideration: 1. Report an original, reproducible bug… 2. Wait for the Cortensor or OpenMinion team to acknowledge… 3. Make a substantive fix attempt and submit it as a PR… **A bug report without a substantive fix PR does not qualify for this bonus.**」

硬性交付清单：「A public source repository and README with setup and run instructions／A short explanation of the OpenMinion SDK workflow／One working example and a **1–5 minute demo video**／A **Building Blocks Tested** note／A **What We Learned** note」

## 1. 演示脚本（先写脚本，再写验收条件）

片子 2 分 30 秒，全片只有一台笔记本、一个终端、一份报告。

| 时间 | 画面 | 要说的一句 |
|---|---|---|
| 0:00–0:06 | 黑场，一行白字 | 一个仓库对外的承诺，和它实际的行为，中间会裂开。 |
| 0:06–0:14 | 终端 | `fencepost audit .` —— 没有 GPU，没有 API key，本机 4B 模型。 |
| 0:14–0:34 | 提案：模型读 README | 模型提出 6 条承诺。它只被允许**引用**，不被允许**作证**。 |
| 0:34–0:56 | 逐字核对：3 条被拒 | 这 3 条的引文在原文里找不到。它们进账本，但不进结论。 |
| 0:56–1:16 | 四个检测器配对 | 承诺 ↔ 实现，两边都必须有 `文件:行`。 |
| 1:16–1:40 | 审查 + 反方读者 | 第二个 agent 只有一个任务：把每一条推翻。推不翻的才算数。 |
| 1:40–2:05 | 审计单（浏览器） | 每一行两个出处。缩到 600px 也读得出来。 |
| 2:05–2:20 | 终端 `exit 1` | 放进 CI，一句话。 |
| 2:20–2:30 | 尾卡 | 仓库地址 + 一行「模型不许作证」。 |

**不做**：不配音效、不做转场、不拍摄真人。全片画面就是真实的 stdout 与报告页。

## 2. 黄金路径（一个评委照做就能复现的那条路）

```
git clone <repo> && cd fencepost
python3.11 -m venv .venv && . .venv/bin/activate && pip install -e .
# 任选其一：
#   A. 有 key：openminion setup --provider openai --model gpt-4.1-mini --no-chat
#   B. 无 key：llama-server -m qwen3-4b-q4.gguf --port 8080 --jinja  +  custom-openai-compatible
fencepost audit fixtures/multi --yes
# → 4 条漂移、3 条高；report.html 打开即审计单
```

## 3. 可判定的验收条件（每条都有命令）

| # | 判据 | 命令与期望 |
|---|---|---|
| AC-1 | 装得上 | `pip install -e .` 后 `fencepost --version` 打印 `fencepost 0.1.0` |
| AC-2 | 无模型也能干真活 | `fencepost audit fixtures/multi --no-model --yes` 退出码 **1**；ledger 里 `severity=high` 恰为 **3** 条 |
| AC-3 | 干净仓库不误报 | `fencepost audit fixtures/clean --no-model --yes` 退出码 **0**，drift **0**；ledger 仍有 findings（说明它真的检查过） |
| AC-4 | 引文闸是硬的 | `pytest tests/test_quote_gate.py -q` 全过：编造的引文、不含取值的引文、过短的引文、超长的引文，四条全部被拒 |
| AC-5 | 每条发现都有真实出处 | `pytest tests/test_detectors.py::test_every_finding_carries_a_real_quote` 通过：每条 `claim.quote` 都是目标文件里的逐字子串，`line` 由该子串算出 |
| AC-6 | 模型路径真跑通了 | `fencepost audit fixtures/multi --yes` 后 ledger 里 `run.mode == "model"`、`run.run_id` 非空、`run.model_calls > 0` |
| AC-7 | 被拒引文写进账本 | `len(ledger.dropped_quotes) == ledger.run.claims_dropped`，且每条带 `reason` |
| AC-8 | 反方读者真的在反 | 模型模式下 `report.md` 里「被驳回」小节存在（可为 0 条，但小节必须由真实 rebuttal 结果决定） |
| AC-9 | 报告是审计单不是日志 | `report.html` 含「逐字核对拒绝」，且至少一行带 `README.md:<行号>` 与 `pyproject.toml:<行号>` |
| AC-10 | 能当 CI 门 | 同一次审计：`--fail-on high` → 1；`--fail-on none` → 0 |
| AC-11 | 不导入被审项目 | 审计 `openminion` 源码前后，其 `__pycache__` 数量不变（静态分析，不执行目标代码） |
| AC-12 | 只照 README 能从零跑通 | 全新 clone → 按 README 三段命令 → AC-2 与 AC-6 都成立（闸 C 举证） |
| AC-13 | 测试全绿 | `pytest -q` 全过 |
| AC-14 | 审自己也诚实 | `fencepost audit . --no-model` 的每一条发现都能在报告里被逐字核对；若有高严重度条目，必须写清是误报还是真事 |

## 4. 闸 D 的过线判据（预先登记）

赛题没有往届得奖作，用**同场公开作品**替代尺子：`api.github.com/search/repositories?q=openminion+hackathon` 返回 20 个 2026-11 的提交仓库，同媒介（README + 演示视频）、同评委、同赛题。取其中 5 件，与本作混编、随机字母命名，交两位未参与的评委各自排名；**每一位都把本作排在至少 3 件之上**才算过。

## 5. 不做什么

- 不加第五类检测器（四类已经够证明机制）
- 不做 Web UI（报告是静态页，够读就行）
- 不接 Portal / Gemma4
- 不写"AI 总结"式的浮夸 README 段落：README 里出现的每个数字都要能在仓库里指到出处
