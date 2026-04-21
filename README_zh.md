## ProDA

ProDA 是一个面向垂直领域数据构建与模型迭代的 Streamlit WebUI 工作台，目标是把原本分散在脚本中的完整流程统一到一个可视化项目系统中：

- 从原始文档中提取知识核心
- 基于知识核心生成 Benchmark 数据
- 生成 FineTune / SFT 数据
- 调用 LLaMA-Factory 进行模型微调
- 使用 OpenCompass 评测本地模型与 API 模型
- 生成诊断报告与诊断补数据
- 支持二轮微调与结果回看

这套界面化流程重点面向“文档 -> Benchmark / SFT -> 微调 -> 评测 -> 诊断 -> 迭代”的闭环，而不是单点工具。

---

## 目录

- [项目定位](#项目定位)
- [核心能力](#核心能力)
- [工作流总览](#工作流总览)
- [快速开始](#快速开始)
- [运行要求](#运行要求)
- [使用说明](#使用说明)
- [目录结构](#目录结构)
- [项目产物说明](#项目产物说明)
- [常见问题](#常见问题)
- [当前状态与后续计划](#当前状态与后续计划)

---

## 项目定位

ProDA 主要解决以下问题：

1. 原始领域文档难以直接转为可训练、可评测的数据。
2. Benchmark 构建、SFT 数据生成、模型微调、评测与诊断原本由多套脚本串联，维护成本高。
3. 微调后的效果迭代依赖人工观察，缺少基于错误样本的闭环诊断。

因此，ProDA 将这些步骤收敛到一个按项目管理的 WebUI 中，让每个项目都拥有自己的：

- 文档输入
- 知识核心
- Benchmark 数据
- FineTune 数据
- 训练历史
- OpenCompass 评测历史
- 诊断报告与补数据

---

## 核心能力

### 1. 项目制工作台

- 支持创建、切换、重命名、删除项目
- 每个项目拥有独立状态与产物目录
- 自动管理当前项目上下文

### 2. 文档到知识核心

Step1 支持读取：

- `pdf`
- `txt`
- `md`
- `docx`

并在配置好 LLM API 后完成三层知识抽取：

- `L3 reasoning chains`
- `L2 statements`
- `L1 concepts`

同时支持：

- JSON 字段选择
- 文本分块
- 自动 / 合并 / 逐块处理模式
- 并发提取
- 表格编辑与导出

### 3. Benchmark 数据生成

Step2 基于 L3 reasoning chains 生成高质量选择题 Benchmark，支持：

- 每条链目标题数配置
- 并发生成
- 重试
- 中断
- 结果预览与导出

### 4. FineTune 数据生成

Step3 基于 L1/L2 知识核心生成 SFT 数据，支持：

- QA / 单选 / 多选 / 判断题比例控制
- L2 窗口采样
- L1 Top-N 约束
- 并发生成
- 中断与历史回看

### 5. 诊断报告与补数据

Step3 的“诊断报告生成”子页面支持：

- 选择某次 OpenCompass 评测结果
- 选择某个本地模型
- 基于错误样本调用 LLM 生成诊断报告
- 输出结构化 JSON 诊断文件
- 统计准确率、错误类型分布、主题分布
- 生成诊断补数据
- 将补数据与原始数据合并，形成二轮训练集

### 6. 模型微调

Step5 对接 LLaMA-Factory，支持：

- 选择历史生成的数据集进行训练
- 自动转为 ShareGPT 格式并预览
- 基础模型选择
- 训练参数配置
- 保存数据到项目目录
- 生成配置文件
- 启动训练并查看滚动日志
- 记录训练历史与训练产物目录

### 7. OpenCompass 评测

Step6 对接 OpenCompass，支持：

- 使用项目内 Benchmark 直接评测
- 支持本地模型评测
- 支持 API 模型评测
- 自动识别 LoRA / PEFT 路径
- 自动识别二轮训练模型
- 实时日志展示
- 评测历史管理
- 排行榜、对比表、题目级测试面板

### 8. 结果中心

Step7 用于统一查看：

- Benchmark 数量
- FineTune 数据数量
- OpenCompass 评测次数
- OpenCompass 历史结果
- 结果详情与导出

---

## 工作流总览

ProDA 当前的主流程建议如下：

1. 创建项目
2. 在右上角配置并选择可用的 LLM API
3. Step1 上传原始文档，抽取 L1/L2/L3 知识核心
4. Step2 生成 Benchmark 数据
5. Step3 生成 FineTune 数据
6. Step5 选择数据集并进行模型微调
7. Step6 使用 OpenCompass 评测本地模型或 API 模型
8. Step3 诊断子页面基于评测结果生成诊断报告与补数据
9. Step5 使用合并后的二轮数据再次微调
10. Step6 / Step7 对比前后效果

---

## 快速开始

### 1. 准备 Python 环境

建议使用 Python 3.10：

```bash
conda create -n proda310 python=3.10 -y
conda activate proda310
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 准备外部仓库

ProDA 本身是工作台，但训练与评测依赖两个外部项目：

- `LLaMA-Factory`
- `OpenCompass`

请确保你本地已经准备好它们的代码仓库，并且路径可访问。  
ProDA 会优先自动探测默认路径，也允许在运行过程中基于当前环境自动发现。

### 4. 启动 WebUI

推荐入口：

```bash
streamlit run ui/streamlit_app.py
```

兼容入口：

```bash
python app.py
```

注意：`app.py` 只用于提示真实入口，主页面已经迁移到 `ui/streamlit_app.py`。

---

## 运行要求

### 必需

- Python `3.10`
- 可访问的 LLM API（至少用于知识抽取 / 数据生成 / 诊断）

### 训练相关

若你需要 Step5 本地微调，建议准备：

- CUDA 环境
- PyTorch GPU 版本
- 可用 GPU
- 本地 `LLaMA-Factory` 仓库

### 评测相关

若你需要 Step6 本地 OpenCompass 评测，建议准备：

- 本地 `OpenCompass` 仓库
- 与 OpenCompass 兼容的 Python 依赖
- 本地模型目录或 API 模型配置

---

## 使用说明

### 1. 进入项目中心

启动后进入项目主页，可以：

- 创建项目
- 切换项目
- 删除项目
- 进入当前项目

### 2. 配置 LLM

在顶部栏配置可用模型：

- OpenAI 兼容接口
- DeepSeek 兼容接口
- Anthropic 接口

配置完成后，页面右上角的模型下拉会只显示可用配置。

### 3. Step1 文档处理

上传文档后可以：

- 对 JSON 选择字段
- 配置 chunk 大小和 overlap
- 选择 `auto / merge / per_chunk`
- 触发知识核心抽取

抽取完成后可查看并编辑：

- L1
- L2
- L3

### 4. Step2 Benchmark 生成

输入为 Step1 的 L3 chains。  
你可以设置：

- 每条链题数
- 并发数
- 温度
- 重试次数

生成结果会缓存到当前项目。

### 5. Step3 FineTune 数据生成

该页面分为两个模式：

- 原始数据生成与训练准备
- 诊断报告生成

原始数据生成支持多题型配比与采样控制。  
诊断模式支持从 OpenCompass 错误样本中生成报告与补数据。

### 6. Step5 模型微调设置

你可以：

- 从历史数据集中选择一个训练集
- 预览 ShareGPT 格式
- 选择基础模型
- 调整训练参数
- 保存数据与配置
- 启动训练

### 7. Step6 OpenCompass 评测

你可以：

- 使用当前项目的 Benchmark
- 或手动指定 Benchmark JSON
- 配置本地模型 / API 模型
- 添加 LoRA / PEFT 路径
- 一键加入最近训练模型
- 启动评测并查看日志和可视化

### 8. Step7 结果导出

用于集中查看项目产物和 OpenCompass 历史评测结果，不再重复承载评测配置逻辑。

---

## 目录结构

一个精简的目录结构如下：

```text
ProDA/
├── app.py
├── requirements.txt
├── proda/
│   ├── extractor.py
│   ├── benchmark_generator.py
│   ├── finetune_generator.py
│   ├── diagnosis.py
│   ├── diagnosis_supplement.py
│   └── evaluator.py
├── ui/
│   ├── streamlit_app.py
│   ├── components/
│   ├── locales/
│   ├── pages/
│   │   ├── 1_Data_Processing.py
│   │   ├── 2_Benchmark_Generation.py
│   │   ├── 3_Finetune_Generation.py
│   │   ├── 5_Fine_Tuning.py
│   │   ├── 7_OpenCompass_Evaluation.py
│   │   └── 8_Results.py
│   └── utils/
└── .proda_projects/
```

---

## 项目产物说明

每个项目的主要产物保存在：

```text
.proda_projects/<project_id>/
```

常见子目录包括：

- `state.json`：项目状态
- `evaluations/opencompass/`：OpenCompass 输入、运行配置、结果、历史
- `finetune_exports/`：ShareGPT 数据、dataset_info、训练配置、日志、训练历史
- `model_outputs/`：训练输出模型
- `diagnosis/`：诊断报告、补数据、历史
- `workflow/`：二轮微调流程状态

---

## 常见问题

### 1. 为什么启动后页面空白或打不开？

请优先确认：

- 是否使用 `streamlit run ui/streamlit_app.py`
- 端口是否可访问
- 当前集群 / 节点是否允许对外映射

### 2. 为什么知识抽取按钮不可用？

通常是因为：

- 尚未上传文件
- 没有在顶部选择可用模型
- API Key / Base URL 未配置完整

### 3. 为什么 Step5 找不到训练数据？

Step5 只会从当前项目的可训练数据集中选择数据。  
请先在 Step3 生成并保存 / 合并数据。

### 4. 为什么 OpenCompass 评测失败？

请检查：

- OpenCompass 仓库路径是否正确
- `run.py` 是否存在
- 本地模型路径 / LoRA 路径是否正确
- 运行环境是否能访问相关依赖

### 5. 为什么训练 / 评测日志很慢？

在集群环境中这是正常现象，尤其是：

- 首次加载模型
- 首次构建 tokenizer cache
- 多 GPU / DeepSpeed 初始化

---

## 当前状态与后续计划

当前版本已经覆盖：

- 文档处理
- 知识核心抽取
- Benchmark 生成
- FineTune 数据生成
- 本地训练
- OpenCompass 评测
- 诊断报告
- 诊断补数据
- 二轮训练闭环

后续仍可继续增强的方向包括：

- 更完整的数据集管理页
- 更丰富的诊断报告可视化
- 更细粒度的训练配置模板
- 更稳定的集群部署说明
- Docker / Conda 环境文件

---
