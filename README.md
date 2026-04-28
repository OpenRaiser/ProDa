<div align="center">

<img src="https://github.com/user-attachments/assets/7f579d02-acc3-492e-9b24-ad508eb8cfa2" alt="ProDA Logo" width="320" />

**面向垂直领域的 AI 数据构建与模型迭代工作台**  
**从原始文档到 Benchmark / SFT / 微调 / 评测 / 诊断补数据，一站式闭环完成。**

<br />

<p align="center">
  <img src="https://img.shields.io/badge/status-active%20development-2ea44f?style=for-the-badge" alt="Project Status">
  <img src="https://img.shields.io/badge/python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/node.js-16+-339933?style=for-the-badge&logo=node.js&logoColor=white" alt="Node.js">
  <img src="https://img.shields.io/badge/react-18+-61DAFB?style=for-the-badge&logo=react&logoColor=black" alt="React">
  <img src="https://img.shields.io/badge/fastapi-backend-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/license-MIT-blue?style=for-the-badge" alt="License">
</p>

<br />

**快速开始** · **效果展示** · **工作流** · **核心能力** · **模型微调** · **OpenCompass 评测** · **诊断迭代**

<br />

🌐 中文 · [English](./README_en.md)

</div>

---

> ProDa 不是一个“数据生成脚本集合”，而是一个真正面向模型迭代的 **VSCode 风格 Web IDE**。  
> 集成文档解析、知识抽取、Benchmark 构建、SFT 数据生成、LLaMA-Factory 微调、OpenCompass 评测、错误诊断与二轮数据补强串成一个可追溯的项目工作流。

```text
Document
   ↓
Knowledge Core
   ↓
Benchmark / SFT Data
   ↓
Fine-Tuning
   ↓
OpenCompass Evaluation
   ↓
Diagnosis + Supplement Data
   ↓
Second-Round Iteration
```

---

## 📖 目录

- [🚀 为什么你会想试试 ProDa](#-为什么你会想试试-proda)
- [🖼️ 效果展示](#️-效果展示占位待你补图)
- [✨ 你会得到什么](#-你会得到什么)
- [📦 快速开始](#-快速开始5-分钟起步)
- [🔬 工作流建议](#-工作流建议)
- [🏗️ 项目结构](#️-项目结构简版)
- [📂 产物落盘位置](#-产物落盘位置)
- [❓ 常见问题](#-常见问题)
- [🧭 当前状态](#-当前状态)
- [🙏 致谢](#-致谢)
- [⭐ Star History](#-star-history)
- [🤝 贡献与交流](#-贡献与交流)
- [📝 引用](#-引用)
- [📄 License](#-license)

---

## 🚀 为什么你会想试试 ProDa

你可能经历过这些痛点：

- 原始领域文档很多，但很难稳定转成可训练数据
- Benchmark 构建、SFT 生成、训练、评测分散在多套脚本里
- 微调后只看一个总分，不知道模型到底错在哪、怎么修

**ProDA 的目标就是：把这一切收敛到一个可视化、项目化、可追溯的闭环。**

| 传统方式 | ProDA |
| --- | --- |
| 多个脚本手动串联 | 一个项目工作台贯穿全流程 |
| 数据、训练、评测产物分散 | 每个项目自动归档所有状态和产物 |
| 微调评测后只看总分 | 支持样本级结果、错误标注和诊断报告 |
| 二轮迭代依赖人工经验 | 基于错因生成补数据并合并训练集 |
| 训练产物难以即时验证 | 可直接选择模型 / checkpoint 流式对话 |

---

## ✨ 你会得到什么

| 模块 | 你可以做什么 | 产物 |
| --- | --- | --- |
| 文档处理 | 上传领域文档并抽取知识核心 | `L1 / L2 / L3` 知识结构 |
| Benchmark | 从推理链生成可评测题目 | MCQ Benchmark |
| SFT 数据 | 按题型比例生成训练数据 | FineTune / ShareGPT 数据 |
| 模型微调 | 调用 LLaMA-Factory 训练模型 | Checkpoint / LoRA 产物 |
| 模型对话 | 选择历史模型或 checkpoint 直接试聊 | 流式回答与参数验证 |
| OpenCompass | 评测本地模型/API模型 | 排行榜、对比图、样本明细 |
| 诊断补数据 | 分析错误样本并生成补强数据 | 诊断报告、二轮训练集 |

---

### 🗂️ 1) 项目制工作空间（每个项目独立隔离）

- 项目创建 / 切换 / 删除
- 项目状态和产物自动归档
- 历史训练与评测可回看

### 📄 2) 文档到知识核心（Step1）

- 支持 `pdf` / `txt` / `md` / `docx`
- 抽取三层知识表示：`L1 concepts` / `L2 statements` / `L3 reasoning chains`
- 支持分块策略、并发提取、结果编辑导出

### 🧪 3) Benchmark 生成（Step2）

- 基于 L3 链路自动生成选择题 Benchmark
- 支持并发、重试、中断、续跑、结果预览与编辑

### 🧬 4) FineTune 数据生成（Step3）

- QA / 单选 / 多选 / 判断题比例控制
- 支持采样窗口、约束参数、历史回看

### 🩺 5) 诊断报告 + 补数据（Step3 子流程）

- 从 OpenCompass 错误样本生成结构化诊断报告
- 按错因生成诊断补数据
- 与原始数据合并形成二轮训练集

### 🔥 6) 本地微调（Step5）

- 对接 LLaMA-Factory
- 训练参数可视化配置
- 实时日志 / Loss & LR 曲线
- 训练历史与输出目录管理
- 直接对已训练模型/Checkpoint进行流式对话验证

### 📊 7) OpenCompass 评测（Step6）

- 支持本地模型和 API 模型
- 支持 LoRA / PEFT 自动识别
- 结果看板：Leaderboard / Comparison / Samples
- 样本级错误标注与诊断联动

### 🧭 8) 结果中心（Step7）

- 统一查看项目关键产物与活动时间线
- 导出与复盘更直接

---

## 🖼️ 效果展示

<p align="center">
  <strong>🎬 项目讲解视频（点击播放）</strong><br />
  <!-- 将下面链接替换为你的实际视频地址 -->
  <video src="https://github.com/user-attachments/assets/e4bda307-a898-4843-abe6-7667ae45e790" controls width="100%"></video>
</p>

<table>
  <tr>
    <td align="center" width="50%">
      <strong>🖥️ IDE 总览</strong><br />
      <img src="https://github.com/user-attachments/assets/57e7c482-abb5-495c-b3f1-7921788424bc" alt="ProDA IDE 总览" width="100%" height="280" />
    </td>
    <td align="center" width="50%">
      <strong>📚 文档抽取与知识核心</strong><br />
      <img src="https://github.com/user-attachments/assets/64ce9df4-be31-4906-87f1-a4020239914b" alt="文档抽取与知识核心" width="100%" height="280" />
    </td>
  </tr>
  <tr>
    <td align="center" width="50%">
      <strong>📈 微调与训练曲线</strong><br />
      <img src="https://github.com/user-attachments/assets/35c3222e-cab9-4622-9558-42d695a6a124" alt="微调与训练曲线" width="100%" height="280" />
    </td>
    <td align="center" width="50%">
      <strong>🏆 OpenCompass 结果看板</strong><br />
      <img src="https://github.com/user-attachments/assets/82bda5cd-5eb8-4481-913b-0a5fa6f7163f" alt="OpenCompass 结果看板" width="100%" height="280" />
    </td>
  </tr>
  <tr>
    <td align="center" colspan="2">
      <strong>💬 模型对话验证窗口</strong><br />
      <img src="https://github.com/user-attachments/assets/64c167ba-c94a-4dc6-896b-fdd2a4ca13ba" alt="模型对话验证窗口" width="80%" height="280" />
    </td>
  </tr>
</table>

---

## 📦 快速开始（5 分钟起步）

### 1. 创建环境并安装依赖

```bash
conda create -n proda python=3.10 -y
conda activate proda
pip install -r requirements.txt
```

### 2. 准备外部仓库

ProDA 工作台依赖以下外部项目：

- `LLaMA-Factory`（训练）
- `OpenCompass`（评测）

请将 `LlamaFactory`、`opencompass`、`Model` 都放在 `ProDA/` 根目录下：

```text
ProDA/
├── backend/
├── frontend/
├── proda/
├── LlamaFactory/              # 训练仓库
├── opencompass/               # 评测仓库
├── Model/                     # 你下载的本地模型统一放这里
│   ├── Qwen3-8B/
│   └── ...
└── ...
```

然后按 LlamaFactory / OpenCompass 官方文档安装依赖到同一个运行环境中。

> 建议：Step5 页面里将 `model_root` 配置为 `ProDA/Model`，后续训练与评测选模会更直接。

### 2.0 安装 LlamaFactory / OpenCompass 依赖（必做）

以下命令基于你已经在 `ProDA/` 根目录，并且已激活 `proda` 环境：

#### LlamaFactory（from source）

```bash
cd LlamaFactory
pip install -e .
pip install -r requirements/metrics.txt
cd ..
```

#### OpenCompass（推荐 from source）

```bash
cd opencompass
pip install -e .
# 如需更多数据集支持，可选：
# pip install -e ".[full]"
# 如需 API 评测能力，可选：
# pip install -e ".[api]"
cd ..
```

> 说明：你也可以用 `pip install -U opencompass` 安装 pip 版，但为了和本项目补丁脚本保持一致，建议使用 source 方式。

### 2.1 OpenCompass 必改补丁（多选后处理，必须做）

ProDA 的 Step6 配置会默认启用：

- `eval_cfg.pred_postprocessor = parse_multi_choice_answer`（见 `proda/evaluator.py`）

为了确保任何用户下载“纯上游 opencompass”后也能直接跑通，请在 `ProDA/` 根目录执行下面这一条命令：

```bash
bash scripts/patch_opencompass_postprocess.sh
```

该脚本会一次性把 **你当前本地同款逻辑** 打到 `ProDA/opencompass`：

- 在 `opencompass/utils/text_postprocessors.py` 注入并注册 `parse_multi_choice_answer`
- 在 `opencompass/tasks/openicl_eval.py` 注入后处理器强制加载/重载兜底逻辑
- 同步注入你当前本地用于详情压缩的 prompt 提取逻辑（保持与现有行为一致）
- 执行补丁后自动做 import + registry 自检

> 如 opencompass 目录不在默认位置，可传路径：
> `bash scripts/patch_opencompass_postprocess.sh /path/to/opencompass`

若脚本失败，通常是 opencompass 版本与当前补丁锚点差异过大；建议切换到与你当前项目一致的 opencompass 代码后重试。

### 3. 启动后端

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8002 --reload --reload-dir backend --reload-dir proda
```

### 4. 启动前端

```bash
cd frontend
yarn install
yarn dev --host 0.0.0.0 --port 8503
```

### 5. 打开页面

浏览器访问：`http://localhost:8503`

远程服务器建议先做端口转发：

```bash
ssh -L 8503:localhost:8503 -L 8002:localhost:8002 <your-server>
```

---

## 🔬 工作流建议

```text
Create Project
     ↓
Configure LLM API
     ↓
Extract Knowledge Core
     ↓
Generate Benchmark + SFT Data
     ↓
Fine-Tune with LLaMA-Factory
     ↓
Evaluate with OpenCompass
     ↓
Diagnose Errors
     ↓
Generate Supplement Data
     ↓
Second-Round Fine-Tuning
     ↓
Second-Round Evaluate with OpenCompass
```

1. 创建项目
2. 配置并选择 LLM API
3. Step1 抽取知识核心
4. Step2 生成 Benchmark
5. Step3 生成 FineTune 数据
6. Step5 启动微调
7. Step6 执行评测
8. Step3 诊断 + 生成补数据
9. Step5 二轮微调
10. Step6 / Step7 对比迭代收益

---

## 🏗️ 项目结构（简版）

```text
ProDA/
├── backend/                 # FastAPI 后端
├── frontend/                # React + Vite 前端 IDE
├── proda/                   # 核心流水线逻辑
├── ui/                      # 旧版 Streamlit（兼容保留）
├── requirements.txt
├── README.md
└── README_zh.md
```

---

## 📂 产物落盘位置

每个项目产物在：

```text
.proda_projects/<project_id>/
```

常见目录：

- `state.json`：项目状态
- `finetune_exports/`：训练配置、日志、训练历史
- `model_outputs/`：训练产物模型
- `evaluations/opencompass/`：评测输入、结果、历史
- `diagnosis/`：诊断报告、补数据、历史
- `workflow/`：二轮流程状态

---

## ❓ 常见问题

### 页面打不开？

检查前后端是否都启动，以及端口转发是否包含前端端口与后端端口。
若是集群终端环境，在申请计算节点后运行hostname命令获取http地址放进frontend/vite.config.ts的api中的target即可。

### Step5 没有可用训练数据？

先在 Step3 生成并保存数据，或先完成补数据合并。

### OpenCompass 评测失败？

重点检查以下几项：

- OpenCompass 路径、模型路径、LoRA 路径是否正确
- OpenCompass 与 ProDA 是否在同一 Python 环境
- OpenCompass 是否完成了 `parse_multi_choice_answer` 三步补丁（见上方 2.1）
- Step5 的 `model_root` 是否指向 `ProDA/Model`（避免模型扫描不到）

### 日志刷新慢？

在集群环境首次加载模型、构建 tokenizer cache、初始化多卡时是正常现象。

---

## 🧭 当前状态

当前版本已覆盖从数据构建到模型评测与诊断迭代的主闭环，包含：

- 文档处理与知识抽取
- Benchmark 生成（支持续跑）
- FineTune 数据生成
- 本地微调
- OpenCompass 评测
- 诊断报告与补数据
- 二轮训练迭代
- 微调模型流式对话验证

---

## 🙏 致谢

ProDa 的实现离不开这些优秀项目与生态：

- [LLaMA-Factory](https://github.com/hiyouga/LLaMA-Factory) — 高效微调训练框架
- [OpenCompass](https://github.com/open-compass/opencompass) — 大模型评测体系
- [FastAPI](https://fastapi.tiangolo.com/) — 后端 API 服务
- [React](https://react.dev/) / [Vite](https://vitejs.dev/) — 前端交互与工程化
- VSCode / Cursor — ProDa IDE 风格的重要灵感来源

也感谢所有真实业务场景中的反馈者：  
ProDa 的目标不是做一个玩具 Demo，而是持续靠近“能真正支撑领域模型迭代”的工作台。

---

## ⭐ Star History

如果这个项目对你有帮助，欢迎点一个 Star。  

<p align="center">
  <picture>
    <source
      media="(prefers-color-scheme: dark)"
      srcset="https://api.star-history.com/svg?repos=https://github.com/OpenRaiser/ProDa&type=Date&theme=dark"
    />
    <source
      media="(prefers-color-scheme: light)"
      srcset="https://api.star-history.com/svg?repos=https://github.com/OpenRaiser/ProDa&type=Date"
    />
    <img
      alt="Star History Chart"
      src="https://api.star-history.com/svg?repos=https://github.com/OpenRaiser/ProDa&type=Date"
    />
  </picture>
</p>

---

## 🤝 贡献与交流

欢迎提 Issue / PR 一起完善 ProDa。

你可以从这些方向参与：

- 补充更多真实领域数据工作流
- 优化 OpenCompass 样本级可视化
- 增强诊断报告与补数据策略
- 添加更完善的集群部署文档
- 补充 Docker / Conda 环境文件
- 改进 README 截图、Demo 与教程

如果你有真实业务场景（教育、医疗、金融、工业等），非常欢迎反馈，我们会优先补齐高价值能力。

---

## 📝 引用

TBD

---

## 📄 License

MIT

<div align="center">

**ProDa 仅供教育、研究与技术交流使用。**

如果你觉得这个项目有意思，欢迎 Star / Fork / 试跑一遍完整闭环。

</div>

