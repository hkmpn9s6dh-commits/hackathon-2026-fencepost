# 03 · 演示视频

**成品**：`submission/fencepost-demo.mp4` · 2 分 29 秒 · 1280×720 · H.264 + AAC · 5.0 MB
**要求**：赛规要 1–5 分钟、且「shows a real model-backed run」。这一版的每一行字都来自真实运行的记录，不是排版出来的假终端。

## 六个镜头，各答一个问题

| # | 时间 | 画面 | 回答什么 |
|---|---|---|---|
| 1 | 0:00–0:12 | 标题：`a model may propose — it may never testify` | 这是什么，主张是什么 |
| 2 | 0:12–0:39 | 规则模式真实输出：4 drift / high 3 / 三份产物 | 它到底输出什么（不需要模型就能跑） |
| 3 | 0:39–1:35 | **同一个审计接上模型**的完整输出，右下角秒表按真实 87.6 秒折算（1.6× 播放） | 「real model-backed run」——真实耗时、真实 4B 模型 |
| 4 | 1:35–1:55 | `report.html` 逐行下滚 | 每一根桩子都带两处 `file:line` |
| 5 | 1:55–2:14 | 退出码阶梯：`--fail-on high` → 1，`--fail-on none` → 0 | 能当 CI 门用 |
| 6 | 2:14–2:29 | 四段式收尾：propose / verify / attack / ledger | 记一句话就走 |

## 素材从哪来（不许编）

- 镜头 2、5：`fencepost audit fixtures/multi --no-model` 的真实 stdout（本机执行的原文）。
- 镜头 3：`video/model-run.log`——本机 `llama.cpp b12425` + `Qwen3-4B-Instruct-2507-Q4_K_M`（CPU，12 线程）跑 `fencepost audit fixtures/multi --yes` 的完整记录，工具自报 87.6 s，shell `real 1m42.4s`。**两个数不一样，视频里分开写**：终端印 87.6 s，底栏写「87.6 s of real time, played at 1.6×」。
- 镜头 4：`out-multi-model/report.html`（同一次模型运行的产物），用 iframe 真实滚动。
- 音轨：`video/make_audio.py` 纯合成（55 Hz 基频 + 四次谐波 + 呼吸包络 + 每行一个 45 ms 的 1740/2610 Hz 提示音），无采样、无版权问题；`ffmpeg loudnorm` 到 I≈−16 LUFS、TP −1.5 dB（实测 mean −12.9 dB / max −1.4 dB）。

## 怎么重做

```bash
cd cortensor
py -3 video/build_demo.py          # 从 model-run.log 生成 demo.html（它会重算秒表倍速）
cd video && py -3 -m http.server 8099 --bind 127.0.0.1 &
node record.mjs                    # Chromium 录 1280×720/25fps → raw/*.webm，同时导出 events.json
py -3 make_audio.py                # events.json → bed.wav
ffmpeg -y -i raw/*.webm -i bed.wav -c:v libx264 -preset medium -crf 20 \
  -pix_fmt yuv420p -r 25 -c:a aac -b:a 128k -ar 48000 \
  -af "loudnorm=I=-16:TP=-1.5:LRA=11" -shortest \
  ../fencepost/submission/fencepost-demo.mp4
```

## 踩过的坑（写下来免得再踩）

1. **秒表不能按动画走**。第一版底栏写「real elapsed time」，右下角秒表却是动画时钟（播到 44 s 时终端已经印着 87.6 s）——同一帧里两个自相矛盾的数字，正是这个项目最不能犯的错。现在秒表按 `toolSeconds / 56` 折算，终点正好落在 87.6 s，并在底栏标出「played at 1.6×」。
2. **音轨要跟着 `events.json` 重建**。改了节奏不重建音轨，提示音会跟文字错位（前几场短片栽过一次）。
3. 中间产物**不要**加 `-movflags +faststart`（这台机器末尾重写 moov 会把 mp4 写坏，抽帧为 0）。
4. 录屏用 `recordVideo`，别用截屏拼帧：Playwright 的合成器在 25 fps 下更稳，滚动也不抖。
