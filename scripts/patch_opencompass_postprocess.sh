#!/usr/bin/env bash
set -euo pipefail

# One-shot patcher for OpenCompass multi-choice postprocessing compatibility.
# It applies the SAME local logic used by current ProDA integration:
# - parse_multi_choice_answer postprocessor in text_postprocessors.py
# - robust postprocessor loading hooks in tasks/openicl_eval.py
# - prompt extraction + compact details output behavior in openicl_eval.py

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PRODA_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
OPENCOMPASS_DIR="${1:-${PRODA_ROOT}/opencompass}"

if [[ ! -d "${OPENCOMPASS_DIR}" ]]; then
  echo "[ERROR] opencompass dir not found: ${OPENCOMPASS_DIR}" >&2
  exit 1
fi

TP_FILE="${OPENCOMPASS_DIR}/opencompass/utils/text_postprocessors.py"
TASK_FILE="${OPENCOMPASS_DIR}/opencompass/tasks/openicl_eval.py"

if [[ ! -f "${TP_FILE}" ]]; then
  echo "[ERROR] missing file: ${TP_FILE}" >&2
  exit 1
fi
if [[ ! -f "${TASK_FILE}" ]]; then
  echo "[ERROR] missing file: ${TASK_FILE}" >&2
  exit 1
fi

python - <<'PY' "${TP_FILE}" "${TASK_FILE}"
from pathlib import Path
import re
import sys

tp_path = Path(sys.argv[1])
task_path = Path(sys.argv[2])

tp = tp_path.read_text(encoding="utf-8")
task = task_path.read_text(encoding="utf-8")

parse_block = r'''

@TEXT_POSTPROCESSORS.register_module('parse_multi_choice_answer')
def parse_multi_choice_answer(text: str) -> str:
    """
    清洗模型输出，提取选项字母。
    处理情况：
    1. remove markdown: **A** -> A
    2. remove punctuation: A. -> A
    3. 优先提取 "Answer:" / "答案：" 后面的内容
    4. 若无答案标签，优先从开头的 "A,B,C\n\n..." 格式提取（首行/首块即答案）
    5. 兜底：从全文提取，取最长匹配（避免误取 "Option A" 中的单个 A）
    6. 去除 <think>...</think> 标签（针对微调模型）
    """
    if not text:
        return ""

    # 0. 预处理：去除 <think>...</think> 标签及其内容
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = text.strip()

    # 1. 预处理：转大写，去除 ** 等 Markdown 加粗符号
    text_upper = text.upper().replace('**', '').replace("'", "").replace('"', "")

    def _extract_choice_sequence(text_segment: str, prefer_first: bool = False) -> list:
        """
        提取选项序列。prefer_first=True 时取第一个匹配（用于开头答案），
        False 时取最后一个匹配（用于文末答案）。
        """
        # 逗号分隔
        pattern = r'(?:^|[^A-Z])([A-D](?:\s*,\s*[A-D]){0,3})(?=[^A-Z]|$)'
        matches = re.findall(pattern, text_segment)
        if matches:
            idx = 0 if prefer_first else -1
            return re.findall(r'[A-D]', matches[idx])
        # 空格分隔
        pattern_ws = r'(?:^|[^A-Z])([A-D](?:\s+[A-D]){0,3})(?=[^A-Z]|$)'
        matches = re.findall(pattern_ws, text_segment)
        if matches:
            idx = 0 if prefer_first else -1
            return re.findall(r'[A-D]', matches[idx])
        return []

    def _get_best_match(text_segment: str) -> list:
        """从含多匹配的文本中，取最长的有效选项序列（避免误取 'Option A' 中的单个 A）。"""
        pattern = r'(?:^|[^A-Z])([A-D](?:\s*,\s*[A-D]){0,3})(?=[^A-Z]|$)'
        matches = re.findall(pattern, text_segment)
        if not matches:
            pattern_ws = r'(?:^|[^A-Z])([A-D](?:\s+[A-D]){0,3})(?=[^A-Z]|$)'
            matches = re.findall(pattern_ws, text_segment)
        if not matches:
            return []
        # 取最长匹配（如 "A,B,C" 优先于 "A"）
        best = max(matches, key=lambda m: len(re.findall(r'[A-D]', m)))
        return re.findall(r'[A-D]', best)

    # 2. 优先尝试 "Answer:" / "答案：" 后面的内容
    answer_label_pattern = re.compile(r'(answer\s*:|答案\s*：)', re.IGNORECASE)
    answer_label_match = answer_label_pattern.search(text)
    if answer_label_match:
        answer_text = text[answer_label_match.end():answer_label_match.end() + 100]
        if '\n' in answer_text:
            answer_text = answer_text.split('\n')[0]
        text_to_parse = answer_text.upper()
        matches = _extract_choice_sequence(text_to_parse, prefer_first=True)
        if matches:
            return ",".join(sorted(list(set(matches))))

    # 3. 无答案标签时，优先从首行/首块提取（格式 "A,B,C\n\nOption A is correct..."）
    first_block = text_upper.split('\n\n')[0].strip()
    if first_block:
        matches = _extract_choice_sequence(first_block, prefer_first=True)
        if matches:
            return ",".join(sorted(list(set(matches))))

    # 4. 再从全文提取，取最长匹配（避免误取 "OPTION A" 中的单个 A）
    matches = _get_best_match(text_upper[:300])
    if matches:
        return ",".join(sorted(list(set(matches))))

    return ""
'''

if "register_module('parse_multi_choice_answer')" not in tp:
    tp = tp.rstrip() + parse_block + "\n"

def replace_once(src: str, old: str, new: str, name: str) -> str:
    if new in src:
        return src
    if old not in src:
        raise RuntimeError(f"[PATCH ERROR] cannot find anchor for {name}")
    return src.replace(old, new, 1)

old_import = """from opencompass.utils import (build_dataset_from_cfg, get_infer_output_path,
                               get_logger)
"""
new_import = """from opencompass.utils import (build_dataset_from_cfg, get_infer_output_path,
                               get_logger)
# 确保后处理器模块被导入，以便注册生效
# 强制导入整个模块以确保所有装饰器执行
import opencompass.utils.text_postprocessors  # noqa: F401
"""
task = replace_once(task, old_import, new_import, "task imports")

old_score = """    def _score(self):
        # Load and preprocess test data
"""
new_score = """    def _score(self):
        # 确保后处理器模块在评估开始时被加载
        import opencompass.utils.text_postprocessors  # noqa: F401
        try:
            from opencompass.utils.text_postprocessors import parse_multi_choice_answer  # noqa: F401
        except ImportError:
            pass
        # Load and preprocess test data
"""
task = replace_once(task, old_score, new_score, "_score pre-import")

old_load_preds = """    def _load_predictions(self):
        \"\"\"Load model predictions from files.\"\"\"
        filename = get_infer_output_path(
            self.model_cfg,
            self.dataset_cfg,
            osp.join(self.work_dir, 'predictions'),
        )
"""
new_load_preds = """    def _load_predictions(self):
        \"\"\"Load model predictions from files.\"\"\"
        # Try to find predictions directory
        # First try in current work_dir
        predictions_dir = osp.join(self.work_dir, 'predictions')
        # If not found, try parent directory (for eval mode when work_dir is in summary)
        if not osp.exists(predictions_dir):
            parent_dir = osp.dirname(self.work_dir)
            parent_predictions_dir = osp.join(parent_dir, 'predictions')
            if osp.exists(parent_predictions_dir):
                predictions_dir = parent_predictions_dir
        
        filename = get_infer_output_path(
            self.model_cfg,
            self.dataset_cfg,
            predictions_dir,
        )
"""
task = replace_once(task, old_load_preds, new_load_preds, "_load_predictions")

old_pred_proc_1 = """            kwargs = copy.deepcopy(self.model_cfg['pred_postprocessor'])
            proc = kwargs.pop('type')
            if isinstance(proc, str):
                proc = TEXT_POSTPROCESSORS.get(proc)
            if pred_list_flag:
                pred_strs = [[proc(s, **kwargs) for s in preds]
                             for preds in pred_strs]
"""
new_pred_proc_1 = """            kwargs = copy.deepcopy(self.model_cfg['pred_postprocessor'])
            proc = kwargs.pop('type')
            if isinstance(proc, str):
                proc_name = proc
                # 确保后处理器模块被加载
                import opencompass.utils.text_postprocessors  # noqa: F401
                try:
                    from opencompass.utils.text_postprocessors import parse_multi_choice_answer  # noqa: F401
                except ImportError:
                    pass
                proc = TEXT_POSTPROCESSORS.get(proc_name)
                if proc is None:
                    import sys
                    if 'opencompass.utils.text_postprocessors' in sys.modules:
                        del sys.modules['opencompass.utils.text_postprocessors']
                    import opencompass.utils.text_postprocessors  # noqa: F401
                    from opencompass.utils.text_postprocessors import parse_multi_choice_answer  # noqa: F401
                    proc = TEXT_POSTPROCESSORS.get(proc_name)
                if proc is None:
                    raise ValueError(
                        f"Postprocessor '{proc_name}' not found in TEXT_POSTPROCESSORS. "
                        f"Available postprocessors: {list(TEXT_POSTPROCESSORS._module_dict.keys())}"
                    )
            if proc is None:
                raise ValueError("Postprocessor is None. Please check the configuration.")
            if pred_list_flag:
                pred_strs = [[proc(s, **kwargs) for s in preds]
                             for preds in pred_strs]
"""
task = replace_once(task, old_pred_proc_1, new_pred_proc_1, "model pred_postprocessor")

old_pred_proc_2 = """            kwargs = copy.deepcopy(self.eval_cfg['pred_postprocessor'])
            proc = kwargs.pop('type')
            if isinstance(proc, str):
                proc = TEXT_POSTPROCESSORS.get(proc)
            if pred_list_flag:
                pred_strs = [[proc(s, **kwargs) for s in preds]
                             for preds in pred_strs]
"""
new_pred_proc_2 = """            kwargs = copy.deepcopy(self.eval_cfg['pred_postprocessor'])
            proc = kwargs.pop('type')
            if isinstance(proc, str):
                proc_name = proc
                # 确保后处理器模块被加载（在子进程中可能未自动加载）
                # 先显式导入整个模块，确保装饰器执行
                import opencompass.utils.text_postprocessors  # noqa: F401
                # 显式导入后处理器函数，确保注册装饰器执行
                try:
                    from opencompass.utils.text_postprocessors import parse_multi_choice_answer  # noqa: F401
                except ImportError:
                    pass
                # 尝试获取后处理器
                proc = TEXT_POSTPROCESSORS.get(proc_name)
                # 如果仍未找到，尝试重新导入并再次获取
                if proc is None:
                    import importlib
                    import sys
                    # 如果模块已经在 sys.modules 中，先移除再重新导入
                    if 'opencompass.utils.text_postprocessors' in sys.modules:
                        del sys.modules['opencompass.utils.text_postprocessors']
                    import opencompass.utils.text_postprocessors  # noqa: F401
                    from opencompass.utils.text_postprocessors import parse_multi_choice_answer  # noqa: F401
                    proc = TEXT_POSTPROCESSORS.get(proc_name)
                if proc is None:
                    raise ValueError(
                        f"Postprocessor '{proc_name}' not found in TEXT_POSTPROCESSORS. "
                        f"Available postprocessors: {list(TEXT_POSTPROCESSORS._module_dict.keys())}"
                    )
            if proc is None:
                raise ValueError("Postprocessor is None. Please check the configuration.")
            if pred_list_flag:
                pred_strs = [[proc(s, **kwargs) for s in preds]
                             for preds in pred_strs]
"""
task = replace_once(task, old_pred_proc_2, new_pred_proc_2, "eval pred_postprocessor")

extract_method = """
    def _extract_question_from_prompt(self, origin_prompt):
        \"\"\"从完整的 prompt 中提取问题文本和选项，去除示例和说明。
        
        Args:
            origin_prompt: 原始的完整 prompt，可能是一个列表（包含 role 和 prompt）或字符串。
        
        Returns:
            dict: 包含提取出的问题文本和选项的字典，如果提取失败则返回 None。
        \"\"\"
        import re
        
        # 处理 origin_prompt 可能是列表的情况
        if isinstance(origin_prompt, list) and len(origin_prompt) > 0:
            prompt_text = origin_prompt[0].get('prompt', '') if isinstance(origin_prompt[0], dict) else str(origin_prompt[0])
        elif isinstance(origin_prompt, str):
            prompt_text = origin_prompt
        else:
            return None
        
        # 方法1: 查找 "现在请回答：" 之后的内容（标准格式）
        # 使用更精确的正则表达式，确保能匹配到最后一个 Question 后面的内容
        match = re.search(r'现在请回答：\\s*\\n\\s*Question:\\s*(.+?)\\s*\\n\\s*A\\.\\s*(.+?)\\s*\\n\\s*B\\.\\s*(.+?)\\s*\\n\\s*C\\.\\s*(.+?)\\s*\\n\\s*D\\.\\s*(.+?)\\s*\\n\\s*Answer:', prompt_text, re.DOTALL)
        
        if match:
            return {
                'question': match.group(1).strip(),
                'A': match.group(2).strip(),
                'B': match.group(3).strip(),
                'C': match.group(4).strip(),
                'D': match.group(5).strip(),
            }
        
        # 方法2: 如果没有 "现在请回答："，尝试提取最后一个 Question 之后的内容
        # 查找最后一个 "Question:" 后面的内容（避免匹配到示例中的 Question）
        matches = list(re.finditer(r'Question:\\s*(.+?)\\s*\\n\\s*A\\.\\s*(.+?)\\s*\\n\\s*B\\.\\s*(.+?)\\s*\\n\\s*C\\.\\s*(.+?)\\s*\\n\\s*D\\.\\s*(.+?)(?:\\s*\\n\\s*Answer:|$)', prompt_text, re.DOTALL))
        
        if matches:
            # 使用���后一个匹配（通常是实际的问题，而不是示例）
            match = matches[-1]
            return {
                'question': match.group(1).strip(),
                'A': match.group(2).strip(),
                'B': match.group(3).strip(),
                'C': match.group(4).strip(),
                'D': match.group(5).strip(),
            }
        
        # 如果都找不到，返回 None（保留完整 prompt）
        return None
"""

if "def _extract_question_from_prompt(self, origin_prompt):" not in task:
    marker = "    def format_details(\n"
    if marker not in task:
        raise RuntimeError("[PATCH ERROR] cannot find format_details marker for extractor insertion")
    task = task.replace(marker, extract_method + "\n" + marker, 1)

old_fmt_block = """                results['type'] = 'GEN'
                result['prompt'] = origin_prediction['origin_prompt']
                result['origin_prediction'] = pred_dicts[i]['prediction']
                result['predictions'] = details[i]['pred']
                result['references'] = details[i]['answer']
                result['correct'] = details[i]['correct']
"""
new_fmt_block = """                results['type'] = 'GEN'
                # 尝试从 prompt 中提取问题和选项，减少冗余
                extracted_info = self._extract_question_from_prompt(origin_prediction.get('origin_prompt'))
                if extracted_info:
                    # 如果成功提取，只保存问题和选项，不保存完整的 prompt
                    result['question'] = extracted_info['question']
                    result['options'] = {
                        'A': extracted_info['A'],
                        'B': extracted_info['B'],
                        'C': extracted_info['C'],
                        'D': extracted_info['D'],
                    }
                else:
                    # 如果提取失败，保留完整 prompt（向后兼容）
                    result['prompt'] = origin_prediction['origin_prompt']
                result['origin_prediction'] = pred_dicts[i]['prediction']
                result['predictions'] = details[i]['pred']
                result['references'] = details[i]['answer']
                result['correct'] = details[i]['correct']
"""
task = replace_once(task, old_fmt_block, new_fmt_block, "format_details(details)")

old_fmt_block_2 = """                results['type'] = 'GEN'
                result['prompt'] = origin_prediction['origin_prompt']
                result['origin_prediction'] = pred_dicts[i]['prediction']
                result['predictions'] = str(predictions[i])
                result['references'] = str(references[i])
"""
new_fmt_block_2 = """                results['type'] = 'GEN'
                # 尝试从 prompt 中提取问题和选项，减少冗余
                extracted_info = self._extract_question_from_prompt(origin_prediction.get('origin_prompt'))
                if extracted_info:
                    # 如果成功提取，只保存问题和选项，不保存完整的 prompt
                    result['question'] = extracted_info['question']
                    result['options'] = {
                        'A': extracted_info['A'],
                        'B': extracted_info['B'],
                        'C': extracted_info['C'],
                        'D': extracted_info['D'],
                    }
                else:
                    # 如果提取失败，保留完整 prompt（向后兼容）
                    result['prompt'] = origin_prediction['origin_prompt']
                result['origin_prediction'] = pred_dicts[i]['prediction']
                result['predictions'] = str(predictions[i])
                result['references'] = str(references[i])
"""
task = replace_once(task, old_fmt_block_2, new_fmt_block_2, "format_details(no_details)")

old_main = """if __name__ == '__main__':
    args = parse_args()
    cfg = Config.fromfile(args.config)
"""
new_main = """if __name__ == '__main__':
    args = parse_args()
    # 确保后处理器模块被加载（在加载配置之前）
    # 强制导入整个模块以确保所有装饰器执行
    import opencompass.utils.text_postprocessors  # noqa: F401
    # 显式导入后处理器函数，确保注册
    try:
        from opencompass.utils.text_postprocessors import parse_multi_choice_answer  # noqa: F401
    except ImportError:
        pass
    cfg = Config.fromfile(args.config)
"""
task = replace_once(task, old_main, new_main, "__main__ preload")

tp_path.write_text(tp, encoding="utf-8")
task_path.write_text(task, encoding="utf-8")

print("[OK] patched text_postprocessors.py and openicl_eval.py")
PY

python - <<'PY' "${OPENCOMPASS_DIR}"
import sys
from pathlib import Path

root = Path(sys.argv[1])
sys.path.insert(0, str(root))

from opencompass.utils.text_postprocessors import parse_multi_choice_answer  # noqa: F401
from opencompass.registry import TEXT_POSTPROCESSORS

print("[CHECK] parse_multi_choice_answer import: OK")
print(f"[CHECK] registry contains parse_multi_choice_answer: {'parse_multi_choice_answer' in TEXT_POSTPROCESSORS.module_dict}")
PY

echo "[DONE] OpenCompass multi-choice postprocess patch applied at: ${OPENCOMPASS_DIR}"
