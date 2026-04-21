# ProDA

ProDA is a Streamlit-based workbench for vertical-domain data construction and model iteration. It turns a previously script-driven pipeline into a project-oriented WebUI that covers the full loop:

- extract knowledge cores from raw documents
- generate benchmark data
- generate FineTune / SFT data
- launch model fine-tuning through LLaMA-Factory
- evaluate local or API models with OpenCompass
- generate diagnosis reports and diagnostic supplements
- support second-round fine-tuning and result review

Rather than being a single-purpose tool, ProDA is designed for the complete workflow of:

`document -> benchmark / SFT -> fine-tuning -> evaluation -> diagnosis -> iteration`

---

## Table of Contents

- [Project Scope](#project-scope)
- [Core Capabilities](#core-capabilities)
- [Workflow Overview](#workflow-overview)
- [Quick Start](#quick-start)
- [Runtime Requirements](#runtime-requirements)
- [How to Use](#how-to-use)
- [Project Structure](#project-structure)
- [Generated Artifacts](#generated-artifacts)
- [FAQ](#faq)
- [Current Status and Next Steps](#current-status-and-next-steps)

---

## Project Scope

ProDA is built to solve three practical problems:

1. raw domain documents are difficult to convert directly into trainable and evaluable datasets
2. benchmark construction, SFT generation, fine-tuning, evaluation, and diagnosis were previously split across multiple scripts
3. post-training iteration often depends on manual inspection instead of structured error-driven refinement

To address this, ProDA organizes the whole process into a project-based WebUI where each project owns its own:

- source documents
- knowledge core
- benchmark data
- fine-tuning data
- training history
- OpenCompass evaluation history
- diagnosis reports and supplement datasets

---

## Core Capabilities

### 1. Project-based workspace

- create, switch, rename, and delete projects
- isolate states and artifacts per project
- automatically keep track of the active project context

### 2. Document-to-knowledge-core pipeline

Step1 supports:

- `pdf`
- `txt`
- `md`
- `docx`

After an LLM API is configured, ProDA extracts a three-level knowledge representation:

- `L3 reasoning chains`
- `L2 statements`
- `L1 concepts`

It also supports:

- JSON field selection
- text chunking
- `auto / merge / per_chunk` processing modes
- parallel extraction
- table-based review and export

### 3. Benchmark generation

Step2 generates multiple-choice benchmark data from L3 reasoning chains, with support for:

- target question count per chain
- parallel generation
- retries
- cancellation
- preview and export

### 4. FineTune data generation

Step3 generates SFT data from the knowledge core and supports:

- QA / single-choice / multiple-choice / true-false ratios
- L2 window sampling
- L1 Top-N constraints
- parallel generation
- interruption and result review

### 5. Diagnosis reports and supplements

The diagnosis mode under Step3 supports:

- choosing a previous OpenCompass evaluation run
- choosing a specific local model
- generating structured diagnosis reports from error samples via LLM
- exporting diagnosis JSON files
- summarizing accuracy, issue distributions, and subject distributions
- generating diagnostic supplement data
- merging supplement data with the original dataset for second-round training

### 6. Model fine-tuning

Step5 integrates with LLaMA-Factory and supports:

- selecting a historical dataset for training
- converting it into ShareGPT format and previewing the result
- selecting the base model
- configuring training parameters
- saving datasets into the project directory
- generating config files
- launching training and viewing live logs
- tracking training history and output model directories

### 7. OpenCompass evaluation

Step6 integrates with OpenCompass and supports:

- evaluating directly on the project benchmark
- evaluating local models
- evaluating API models
- auto-detecting LoRA / PEFT paths
- auto-detecting the latest second-round model
- displaying live logs
- managing evaluation history
- showing leaderboards, comparison tables, and sample-level test panels

### 8. Result center

Step7 provides a unified view of:

- benchmark size
- fine-tuning dataset size
- OpenCompass evaluation count
- historical OpenCompass runs
- run details and downloads

---

## Workflow Overview

The recommended workflow is:

1. create a project
2. configure and select an LLM API from the top-right panel
3. Step1: upload raw documents and extract L1/L2/L3 knowledge cores
4. Step2: generate benchmark data
5. Step3: generate fine-tuning data
6. Step5: select a dataset and run model fine-tuning
7. Step6: evaluate local or API models with OpenCompass
8. Step3 diagnosis mode: generate diagnosis reports and supplement data
9. Step5: fine-tune again using the merged second-round dataset
10. Step6 / Step7: compare before-and-after results

---

## Quick Start

### 1. Create a Python environment

Python 3.10 is recommended:

```bash
conda create -n proda310 python=3.10 -y
conda activate proda310
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Prepare external repositories

ProDA itself is the workbench, but local training and evaluation depend on two external projects:

- `LLaMA-Factory`
- `OpenCompass`

Please make sure those repositories are available on your machine and reachable by path.  
ProDA will try to auto-detect default paths and can also discover them from the current runtime context.

### 4. Launch the WebUI

Recommended entry:

```bash
streamlit run ui/streamlit_app.py
```

Compatibility entry:

```bash
python app.py
```

Note: `app.py` only points users to the real entry. The main application lives in `ui/streamlit_app.py`.

---

## Runtime Requirements

### Required

- Python `3.10`
- at least one reachable LLM API for extraction / generation / diagnosis

### For training

If you want Step5 local fine-tuning, it is recommended to prepare:

- CUDA runtime
- GPU-enabled PyTorch
- available GPU resources
- a local `LLaMA-Factory` repository

### For evaluation

If you want Step6 local OpenCompass evaluation, it is recommended to prepare:

- a local `OpenCompass` repository
- an environment compatible with OpenCompass
- a local model path or API model configuration

---

## How to Use

### 1. Enter the project hub

After launch, the home page lets you:

- create projects
- switch projects
- delete projects
- enter the active project

### 2. Configure LLMs

Use the top bar to configure available models:

- OpenAI-compatible APIs
- DeepSeek-compatible APIs
- Anthropic APIs

After configuration, the model dropdown only shows valid entries.

### 3. Step1 document processing

After uploading documents, you can:

- choose JSON fields
- configure chunk size and overlap
- choose `auto / merge / per_chunk`
- start knowledge-core extraction

You can then inspect and edit:

- L1
- L2
- L3

### 4. Step2 benchmark generation

This step uses L3 chains from Step1.  
You can configure:

- questions per chain
- concurrency
- temperature
- retries

The result is cached inside the current project.

### 5. Step3 fine-tune data generation

This page contains two modes:

- original data generation and training preparation
- diagnosis report generation

The first mode supports fine-grained question-type ratios and sampling control.  
The diagnosis mode generates reports and supplement data from OpenCompass error samples.

### 6. Step5 fine-tuning setup

You can:

- choose a dataset from historical project datasets
- preview the ShareGPT conversion
- select the base model
- tune training parameters
- save data and configs
- launch training

### 7. Step6 OpenCompass evaluation

You can:

- evaluate on the current project benchmark
- or provide a custom benchmark JSON
- configure local and API models
- add LoRA / PEFT paths
- import the latest trained model with one click
- run evaluations and inspect logs / visualizations

### 8. Step7 result export

This page centralizes project artifacts and OpenCompass history, without duplicating evaluation configuration logic.

---

## Project Structure

A simplified structure looks like this:

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

## Generated Artifacts

Per-project artifacts are stored under:

```text
.proda_projects/<project_id>/
```

Common subdirectories include:

- `state.json`: project state
- `evaluations/opencompass/`: OpenCompass inputs, configs, results, history
- `finetune_exports/`: ShareGPT data, dataset info, training configs, logs, training history
- `model_outputs/`: trained model artifacts
- `diagnosis/`: diagnosis reports, supplement datasets, history
- `workflow/`: second-round workflow state

---

## FAQ

### 1. Why does the app not open or show a blank page?

Please check:

- whether you launched with `streamlit run ui/streamlit_app.py`
- whether the selected port is reachable
- whether your cluster / node allows the required forwarding or exposure

### 2. Why is the extraction button disabled?

Usually because:

- no files were uploaded
- no valid model was selected from the top-right menu
- the API key / base URL is incomplete

### 3. Why does Step5 not show my training dataset?

Step5 only lists trainable datasets discovered inside the current project.  
Please generate and save / merge datasets in Step3 first.

### 4. Why does OpenCompass evaluation fail?

Please verify:

- the OpenCompass repository path is correct
- `run.py` exists
- local model and LoRA paths are valid
- the current Python environment can access required dependencies

### 5. Why are training / evaluation logs slow?

This is expected in cluster environments, especially during:

- first model load
- first tokenizer cache build
- multi-GPU / DeepSpeed initialization

---

## Current Status and Next Steps

The current version already covers:

- document processing
- knowledge-core extraction
- benchmark generation
- fine-tuning data generation
- local training
- OpenCompass evaluation
- diagnosis reports
- diagnostic supplements
- second-round training loop

Potential next improvements include:

- a more complete dataset management page
- richer diagnosis-report visualizations
- more training config templates
- more stable cluster deployment guidance
- Docker / Conda environment files

---

