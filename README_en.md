<div align="center">

<img src="https://github.com/user-attachments/assets/7f579d02-acc3-492e-9b24-ad508eb8cfa2" alt="ProDa Logo" width="320" />

**An AI data-construction and model-iteration workbench for vertical domains**  
**From raw documents to Benchmark / SFT / fine-tuning / evaluation / diagnostic data augmentation, all in one loop.**

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

**Quick Start** · **Showcase** · **Workflow** · **Core Features** · **Fine-Tuning** · **OpenCompass Evaluation** · **Diagnostic Iteration**

<br />

[中文](./README.md) · 🌐 English

</div>

---

> ProDa is not just a collection of data-generation scripts. It is a **VSCode-style Web IDE** built for iterative model improvement.  
> It integrates document parsing, knowledge extraction, Benchmark construction, SFT data generation, LLaMA-Factory fine-tuning, OpenCompass evaluation, error diagnosis, and second-round data augmentation into one traceable project workflow.

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

## 📖 Table of Contents

- [🚀 Why ProDa](#-why-ProDa)
- [🖼️ Showcase](#️-showcase-placeholders-for-now)
- [✨ What You Get](#-what-you-get)
- [📦 Quick Start](#-quick-start-5-minute-setup)
- [🔬 Recommended Workflow](#-recommended-workflow)
- [🏗️ Project Structure](#️-project-structure-simplified)
- [📂 Artifact Layout](#-artifact-layout)
- [❓ FAQ](#-faq)
- [🧭 Current Status](#-current-status)
- [🎯 Roadmap](#-roadmap)
- [🙏 Acknowledgements](#-acknowledgements)
- [⭐ Star History](#-star-history)
- [🤝 Contributing](#-contributing)
- [📝 Citation](#-citation)
- [📄 License](#-license)

---

## 🚀 Why ProDa

You may have run into these problems:

- You have many domain documents, but they are hard to turn into reliable training data.
- Benchmark generation, SFT data construction, training, and evaluation are scattered across scripts.
- After fine-tuning, a single score does not tell you what the model got wrong or how to improve it.

**ProDa turns the whole process into a visual, project-based, traceable loop.**

| Traditional workflow | ProDa |
| --- | --- |
| Multiple scripts glued together manually | One project workbench for the full pipeline |
| Data, training logs, and eval outputs scattered around | All states and artifacts are automatically archived per project |
| Only aggregate scores after evaluation | Sample-level results, error annotations, and diagnostic reports |
| Second-round iteration depends on manual intuition | Error-driven supplement data and merged training sets |
| Trained artifacts are hard to verify immediately | Chat directly with a model / checkpoint using streaming output |

---

## ✨ What You Get

| Module | What you can do | Output |
| --- | --- | --- |
| Document Processing | Upload domain documents and extract knowledge cores | `L1 / L2 / L3` knowledge structures |
| Benchmark | Generate evaluable questions from reasoning chains | MCQ Benchmark |
| SFT Data | Generate training data with configurable question-type ratios | FineTune / ShareGPT data |
| Fine-Tuning | Train models through LLaMA-Factory | Checkpoints / LoRA artifacts |
| Model Chat | Chat with historical models or checkpoints | Streaming replies and parameter validation |
| OpenCompass | Evaluate local/API models | Leaderboard, comparison charts, sample details |
| Diagnostic Supplement | Analyze error samples and generate targeted data | Diagnostic reports and second-round training sets |

---

### 🗂️ 1) Project-Based Workspace

- Create, switch, and delete projects
- Automatically archive project states and artifacts
- Review historical training and evaluation runs

### 📄 2) Document-to-Knowledge-Core Extraction (Step1)

- Supports `pdf` / `txt` / `md` / `docx`
- Extracts three-level knowledge representation: `L1 concepts` / `L2 statements` / `L3 reasoning chains`
- Supports chunking, parallel extraction, editable tables, and export

### 🧪 3) Benchmark Generation (Step2)

- Automatically generates multiple-choice Benchmark data from L3 reasoning chains
- Supports concurrency, retries, cancellation, resume, preview, and editing

### 🧬 4) FineTune Data Generation (Step3)

- Controls QA / single-choice / multiple-choice / true-false ratios
- Supports sampling windows, constraints, and history review

### 🩺 5) Diagnostic Reports + Supplement Data (Step3 Subflow)

- Generates structured diagnostic reports from OpenCompass error samples
- Produces targeted supplement data based on issue types
- Merges supplement data with original data for second-round training

### 🔥 6) Local Fine-Tuning (Step5)

- Integrates with LLaMA-Factory
- Visual training-parameter configuration
- Live logs and Loss / LR curves
- Training history and output directory management
- Streaming chat verification for trained models / checkpoints

### 📊 7) OpenCompass Evaluation (Step6)

- Supports both local models and API models
- Auto-detects LoRA / PEFT paths
- Result views: Leaderboard / Comparison / Samples
- Sample-level error annotation connected to diagnosis

### 🧭 8) Result Center (Step7)

- Unified view of key project artifacts and activity timeline
- Easier export and review

---

## 🖼️ Showcase

<table>
  <tr>
    <td align="center" width="50%">
      <strong>🖥️ IDE Overview</strong><br />
      <img src="https://github.com/user-attachments/assets/57e7c482-abb5-495c-b3f1-7921788424bc" alt="ProDa IDE Overview" width="100%" height="280" />
    </td>
    <td align="center" width="50%">
      <strong>📚 Document Extraction and Knowledge Core</strong><br />
      <img src="https://github.com/user-attachments/assets/64ce9df4-be31-4906-87f1-a4020239914b" alt="Document Extraction and Knowledge Core" width="100%" height="280" />
    </td>
  </tr>
  <tr>
    <td align="center" width="50%">
      <strong>📈 Fine-Tuning and Training Curves</strong><br />
      <img src="https://github.com/user-attachments/assets/35c3222e-cab9-4622-9558-42d695a6a124" alt="Fine-Tuning and Training Curves" width="100%" height="280" />
    </td>
    <td align="center" width="50%">
      <strong>🏆 OpenCompass Result Dashboard</strong><br />
      <img src="https://github.com/user-attachments/assets/82bda5cd-5eb8-4481-913b-0a5fa6f7163f" alt="OpenCompass Result Dashboard" width="100%" height="280" />
    </td>
  </tr>
  <tr>
    <td align="center" colspan="2">
      <strong>💬 Model Chat Verification</strong><br />
      <img src="https://github.com/user-attachments/assets/64c167ba-c94a-4dc6-896b-fdd2a4ca13ba" alt="FineTuning Chat" width="80%" height="280" />
    </td>
  </tr>
</table>

---

## 📦 Quick Start (5-minute setup)

### 1. Create the environment and install dependencies

```bash
conda create -n ProDa python=3.10 -y
conda activate ProDa
pip install -r requirements.txt
```

### 2. Prepare external repositories

ProDa depends on the following external projects:

- `LLaMA-Factory` for training
- `OpenCompass` for evaluation

Place `LlamaFactory`, `opencompass`, and `Model` directly under the `ProDA/` root:

```text
ProDA/
├── backend/
├── frontend/
├── proda/
├── LlamaFactory/              # training repo
├── opencompass/               # evaluation repo
├── Model/                     # put all downloaded local models here
│   ├── Qwen3-8B/
│   └── ...
└── ...
```

Then install LlamaFactory / OpenCompass dependencies in the same runtime environment.

> Recommendation: in Step5, set `model_root` to `ProDA/Model` so model discovery works out of the box.

### 2.0 Install LlamaFactory / OpenCompass dependencies (required)

The commands below assume you are at `ProDA/` root and `proda` env is already activated.

#### LlamaFactory (from source)

```bash
cd LlamaFactory
pip install -e .
pip install -r requirements/metrics.txt
cd ..
```

#### OpenCompass (recommended: from source)

```bash
cd opencompass
pip install -e .
# Optional: full dataset support
# pip install -e ".[full]"
# Optional: API evaluation extras
# pip install -e ".[api]"
cd ..
```

> Note: You can install OpenCompass via `pip install -U opencompass`, but source install is recommended here so the project patch script works consistently.

### 2.1 Required OpenCompass patch (multi-choice postprocess)

ProDa Step6 configs enable:

- `eval_cfg.pred_postprocessor = parse_multi_choice_answer` (see `proda/evaluator.py`)

To make this work on a clean upstream OpenCompass checkout, run exactly one command at `ProDA/` root:

```bash
bash scripts/patch_opencompass_postprocess.sh
```

This script applies the SAME local logic used in your current setup to `ProDA/opencompass`:

- inject/register `parse_multi_choice_answer` into `opencompass/utils/text_postprocessors.py`
- inject robust postprocessor load/reload fallback into `opencompass/tasks/openicl_eval.py`
- inject the same prompt-extraction logic for compact details output
- run import + registry checks automatically after patching

> If your OpenCompass is not at the default location, pass a path:
> `bash scripts/patch_opencompass_postprocess.sh /path/to/opencompass`

If the script fails, your OpenCompass version is likely too different from the expected anchors; switch to the matching baseline and retry.

### 3. Launch the backend

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8002 --reload --reload-dir backend --reload-dir ProDa
```

### 4. Launch the frontend

```bash
cd frontend
yarn install
yarn dev --host 0.0.0.0 --port 8503
```

### 5. Open the IDE

Open `http://localhost:8503` in your browser.

For remote servers, set up port forwarding first:

```bash
ssh -L 8503:localhost:8503 -L 8002:localhost:8002 <your-server>
```

---

## 🔬 Recommended Workflow

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

1. Create a project
2. Configure and select an LLM API
3. Step1: extract the knowledge core
4. Step2: generate Benchmark data
5. Step3: generate FineTune data
6. Step5: run fine-tuning
7. Step6: run evaluation
8. Step3: diagnose errors and generate supplement data
9. Step5: run second-round fine-tuning
10. Step6 / Step7: compare iteration gains

---

## 🏗️ Project Structure (simplified)

```text
ProDa/
├── backend/                 # FastAPI backend
├── frontend/                # React + Vite frontend IDE
├── ProDa/                   # Core pipeline logic
├── ui/                      # Legacy Streamlit UI kept for compatibility
├── requirements.txt
├── README.md
└── README_zh.md
```

---

## 📂 Artifact Layout

Each project's artifacts are stored under:

```text
.ProDa_projects/<project_id>/
```

Common subdirectories:

- `state.json`: project state
- `finetune_exports/`: training configs, logs, and training history
- `model_outputs/`: trained model artifacts
- `evaluations/opencompass/`: evaluation inputs, results, and history
- `diagnosis/`: diagnostic reports, supplement data, and history
- `workflow/`: second-round workflow state

---

## ❓ FAQ

### The page does not open. What should I check?

Make sure both frontend and backend are running, and that port forwarding includes both frontend and backend ports.

If you are running in a cluster terminal environment, request a compute node and run `hostname` to get the HTTP host. Then update the API `target` in `frontend/vite.config.ts`.

### Step5 does not show any trainable dataset.

Generate and save data in Step3 first, or finish supplement-data merging.

### OpenCompass evaluation fails.

Check all of the following:

- OpenCompass path, base model path, and LoRA path
- whether OpenCompass and ProDa run in the same Python environment
- whether OpenCompass completed the 3-step `parse_multi_choice_answer` patch (see 2.1 above)
- whether Step5 `model_root` points to `ProDA/Model` (to avoid model discovery misses)

### Training / evaluation logs look slow.

This is normal in cluster environments, especially during first model load, tokenizer cache building, or multi-GPU initialization.

---

## 🧭 Current Status

The current version already covers the main loop from data construction to evaluation and diagnostic iteration:

- Document processing and knowledge extraction
- Benchmark generation with resume support
- FineTune data generation
- Local fine-tuning
- OpenCompass evaluation
- Diagnostic reports and supplement data
- Second-round training iteration
- Streaming chat verification for fine-tuned models

---

## 🙏 Acknowledgements

ProDa is built on top of these excellent projects and ecosystems:

- [LLaMA-Factory](https://github.com/hiyouga/LLaMA-Factory) — efficient fine-tuning framework
- [OpenCompass](https://github.com/open-compass/opencompass) — large-model evaluation system
- [FastAPI](https://fastapi.tiangolo.com/) — backend API service
- [React](https://react.dev/) / [Vite](https://vitejs.dev/) — frontend interaction and tooling
- VSCode / Cursor — key inspirations for the IDE-style experience

Thanks also to everyone who provides feedback from real-world domain workflows.  
ProDa is not intended to be a toy demo; it aims to move closer to a practical workbench for domain model iteration.

---

## ⭐ Star History

If this project helps you, please consider giving it a Star.  

<p align="center">
  <picture>
    <source
      media="(prefers-color-scheme: dark)"
      srcset="https://api.star-history.com/svg?repos=https://github.com/OpenRaiser/ProDa-dev&type=Date&theme=dark"
    />
    <source
      media="(prefers-color-scheme: light)"
      srcset="https://api.star-history.com/svg?repos=https://github.com/OpenRaiser/ProDa-dev&type=Date"
    />
    <img
      alt="Star History Chart"
      src="https://api.star-history.com/svg?repos=https://github.com/OpenRaiser/ProDa-dev&type=Date"
    />
  </picture>
</p>

---

## 🤝 Contributing

Issues and PRs are welcome.

Good contribution directions include:

- More real-world domain data workflows
- Better OpenCompass sample-level visualizations
- Stronger diagnostic reports and supplement strategies
- Better cluster deployment documentation
- Docker / Conda environment files
- README screenshots, demos, and tutorials

If you have a real-world scenario in education, healthcare, finance, industry, or other vertical domains, feedback is especially welcome.

---

## 📝 Citation

TBD

---

## 📄 License

MIT

<div align="center">

**ProDa is intended for education, research, and technical exchange.**

If you find this project interesting, feel free to Star / Fork / try the full loop.

</div>

