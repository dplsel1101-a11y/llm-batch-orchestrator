import json
import re
import logging

logger = logging.getLogger(__name__)

class PipelineLogic:
    
    @staticmethod
    def clean_and_parse_json(text: str):
        """
        Antigravity Rule #6: 强力清洗 Markdown 代码块
        """
        if not text:
            return {}
            
        # 1. 移除 ```json 和 ``` 标记
        text = re.sub(r'^```json\s*', '', text, flags=re.MULTILINE)
        text = re.sub(r'^```\s*', '', text, flags=re.MULTILINE)
        
        # 2. 尝试提取最外层的 JSON 对象
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end != 0:
            text = text[start:end]
            
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning(f"JSON Parse Failed for text: {text[:50]}...")
            return None

    @staticmethod
    def _extract_text(vertex_output: dict) -> str:
        """从 Gemini 原始输出中提取文本"""
        try:
            # 兼容 Gemini Batch 输出结构
            return vertex_output['prediction']['candidates'][0]['content']['parts'][0]['text']
        except (KeyError, IndexError, TypeError):
            return ""

    @staticmethod
    def build_input_for_stage(stage_num: int, previous_output: dict = None, original_request: dict = None):
        """
        构建下一阶段的 Prompt
        """
        custom_id = original_request.get("id") if original_request else previous_output.get("custom_id")
        prompt_text = ""

        # --- 业务 Prompt 逻辑 (示例) ---
        if stage_num == 1:
            topic = original_request.get("topic", "Unknown Topic")
            prompt_text = f"Role: Editor. Task: Create a 5-chapter outline for '{topic}'. Output JSON only."
        
        elif stage_num == 2:
            prev_text = PipelineLogic._extract_text(previous_output)
            prompt_text = f"Role: Writer. Task: Write Chapter 1 based on outline:\n{prev_text}"
            
        # ... (此处省略 Stage 3-6，逻辑同上) ...
        # 为了完整性，我补充中间的阶段逻辑，避免运行时逻辑缺失
        elif stage_num in [3, 4, 5, 6]:
             prev_text = PipelineLogic._extract_text(previous_output)
             prompt_text = f"Role: Writer. Task: Write Chapter {stage_num-1} continuing from previous content:\n{prev_text[:200]}..."

        elif stage_num == 7:
            prev_text = PipelineLogic._extract_text(previous_output)
            prompt_text = f"Role: Reviewer. Task: Final polish and format as JSON metadata.\nContext: {prev_text[:500]}..."

        # --- 构造 Gemini 标准请求 ---
        return {
            "request": {
                "contents": [
                    {"role": "user", "parts": [{"text": prompt_text}]}
                ]
            },
            "custom_id": custom_id
        }

    @staticmethod
    def validate_output(stage_num: int, output_item: dict):
        """链式验证"""
        text = PipelineLogic._extract_text(output_item)
        if not text:
            return False, "Empty text generated"
        
        # 简单规则：拒绝词检查
        if "I cannot" in text or "As an AI" in text:
            return False, "Refusal detected"
            
        return True, "OK"
