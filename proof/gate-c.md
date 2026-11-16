# 闸 B / C · 证据

**被测提交**：`2038de8`（本文件与截帧是它之后的文档提交，不含代码改动）
**机器**：Windows 11 10.0.26100 · Python 3.12.14 · 12 线程 CPU · 无 GPU · 无任何 API key

## 1. 本机

```
$ bash scripts/verify.sh
fencepost verify · 2026-11-15T23:59:13Z
interpreter: Python 3.12.14
  PASS  AC-1 installed: fencepost 0.1.0
  PASS  AC-13 tests: 42 passed
  PASS  fixture clean: exit 0, drift 0 (high 0)
  PASS  fixture python-floor: exit 1, drift 1 (high 1)
  PASS  fixture missing-dep: exit 1, drift 2 (high 1)
  PASS  fixture phantom-command: exit 1, drift 1 (high 1)
  PASS  fixture ghost-env: exit 1, drift 1 (high 1)
  PASS  fixture multi: exit 1, drift 4 (high 3)
  PASS  AC-10 --fail-on high -> 1
  PASS  AC-10 --fail-on none -> 0
  PASS  AC-5 every finding quote is verbatim and line-accurate
  PASS  AC-9 report.html carries citations and the refusal section
  INFO  AC-14 self audit: 0 0
verify: all checks passed
```

## 2. 全新 clone（公开仓库 → 空目录 → 一条命令）

```
$ git clone https://github.com/hkmpn9s6dh-commits/hackathon-2026-fencepost _clone-fp
$ cd _clone-fp && bash scripts/verify.sh
  PASS × 12（同上）；INFO AC-14 self audit: 0 0
verify: all checks passed        # 1m48s，含建 venv 与装依赖
```

## 3. 全新 clone + 真实模型（赛规要的 “real model-backed run”）

模型：`llama.cpp b12425` + `Qwen_Qwen3-4B-Instruct-2507-Q4_K_M.gguf`，CPU，端点 `http://127.0.0.1:8080/v1`。

```
$ .venv/Scripts/openminion.exe setup --provider custom-openai-compatible \
    --api-format openai-compatible --base-url http://127.0.0.1:8080/v1 --model qwen3-4b --no-chat
Configuration saved at ...\.om\.openminion\agents.json (provider: Custom OpenAI-compatible endpoint)

$ FENCEPOST_MODEL=1 bash scripts/verify.sh
  PASS × 12
  INFO  AC-14 self audit: 0 0
model path (this takes minutes on CPU)
  PASS  AC-6 model path: mode=model calls=1 run_id=0b5c33ea6eec4ac2812d93167037f7d1
verify: all checks passed
```

## 4. 自审从 3 条到 0 条的过程

| 轮 | 自审结果 | 处理 |
|---|---|---|
| 1 | 3 high（README:62 env_var、docs/01:62 python_requires、docs/01:65 env_var） | 读代码：两条是规则抽取把「说明书里的样本」当承诺、把 `YOUR_API_KEY` 占位符当凭据 → 改工具（`tests/test_extract_specimens.py` 6 项新测试 + clean 夹具加一张参考表当回归护栏） |
| 2 | 1 high（README:79） | 这条是真错：README 的 install 注释里写了 SDK 自己的 key 名，本仓库代码从不读 → 改文档 |
| 3 | **0** | `INFO AC-14 self audit: 0 0` |

写进 `docs/05-FINDINGS.md` §5，因为「一个审计工具在自己身上永远报 0」和「报过 3 条改到 0」不是同一件事。

## 5. 演示片的可核对性

- 129 秒的终端内容来自 `video/model-run.log`（真实运行记录，工具自报 87.6 s / shell `real 1m42.4s`）。
- 右下角秒表按 `87.6 / 56` 折算，终点正好落在 01:27，底栏写明 `played at 1.6×`——第一版是动画时钟（同一帧里 00:44 与 87.6 s 并存），已改。
- 音轨为纯合成（`video/make_audio.py`），`loudnorm` 后实测 mean −12.9 dB / max −1.4 dB。
