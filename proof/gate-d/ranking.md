# 闸 D · 盲排（同一场比赛的公开提交当尺子）

**为什么这个尺子是对的**：Cortensor Hackathon #5 有 20+ 个同场公开提交，同一批评委、同一份评分表、同一种交付形态（README + 演示视频）。前六场卡在「尺子画幅/媒介不对等」，这一场是第一次完全对齐——比的是**同一件事**：一份 README 能不能让人在 120 行内知道你在做什么、信不信。

## 尺子怎么取的

`api.github.com/search/repositories?q=openminion+hackathon` 里 2026-11 之后创建的仓库，取 6 个（A 之外 5 个）作为匿名对手，各自截 README **前 120 行**，隐去作者，字母随机。评委只允许读这六个文件，不许 ls / grep / 联网。

- 我方：A（`README.md` 前 120 行，抽取脚本见本轮 `proof/gate-d/A.md` 头部）
- 对手：B Veritas / C TokenGuard Minion / D Cortensor Sentinel / E RulesMinion / F PreJudge

## 第 1 轮（快照是旧的）

当时 A 的快照取自 05:13 那版 README——**顶部还没有真实运行输出**。

| 名次 | 作品 | 评委理由（原文摘） |
|---|---|---|
| 1 | F PreJudge | 标题直接对准读者自身的处境……这类可信度只有真跑过才写得出来 |
| **2** | **A Fencepost** | 写作是全组最好的（"A fence is only as good as its posts"）……但**没有一段真实运行输出** |
| 3 | C TokenGuard | 一段真实终端输出胜过其余任何一段文字 |
| 4 | E RulesMinion | |
| 5 | B Veritas | |
| 6 | D Sentinel | |

第 1 轮不过线。**唯一被点名的问题**：缺一段可核对的真实运行。这与该轮 C 拿分的点正好是同一件事 → 改法明确。

## 第 2 轮（改完 README 之后，两位新评委）

改法（只改 README，不改工具）：
1. 第 16–33 行插入**一次真实运行的完整输出**（`fencepost audit fixtures/multi --no-model --yes`，4 drift / high 3 / 三份产物路径 / 退出码可接 CI），并在下面写明「接上模型是同一次审计 + 逐字核对 + 反方读者」。
2. 顺手修掉自审发现的一处**真实文档错**：`export OPENAI_COMPATIBLE_API_KEY=... # or OPENAI_API_KEY for the openai preset` ——本仓库代码从不读那个名字（读它的是 SDK 的 openai preset）。工具报得对，改的是文档。

| 名次 | 评委丙 | 评委丁 |
|---|---|---|
| 1 | **A**（第一句就说成读者自己的痛，紧接真实输出，既秒懂又难造假） | **A**（唯一一份读完就能用的；输入/输出/使用时机在前 40 行内全部闭合） |
| 2 | C | F |
| 3 | F | C |
| 4 | E | E |
| 5 | B | B |
| 6 | D | D |

**结论：2/2 第一 → 过线。**

两位评委各自点名「A 的第一段最强 / 最像现在就能用」；两人对最好钩子的判断不完全一致（丙认为 A 胜在紧跟真实输出，丁认为 F 的标题钩子更强但缺真实数字），这正好支持本轮改法：**钩子 + 紧接证据**，两者都要。

## 第 3 轮没有做（记录在案）

第 2 轮已经是 2/2 第一，按「两轮就停」的规则停手，不再为了排名继续改。

## 这条尺子的局限（写清楚，不假装）

- README 第一眼只覆盖评分表 20% 的「Reproducibility and demo quality」的一部分与「Relevance」；25% 的 `Building Blocks Tested` 在 `docs/05-FINDINGS.md`，不在这六个文件里。
- 两位评委是同机同族的模型，不是真评委；它们的价值在于**给出可执行的批评**，不在于预测名次。
