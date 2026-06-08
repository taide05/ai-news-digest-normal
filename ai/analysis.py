def build_core_insight_prompt(full_text: str) -> tuple[str, str]:
    system = "你是一个专业的科技内容摘要助手。"
    user = f"用 2-3 句话概括下面这篇文章的核心内容。直接说重点，不要铺垫。\n\n文章：{full_text}"
    return system, user


def build_what_it_means_prompt(full_text: str, concepts: list[str]) -> tuple[str, str]:
    concepts_str = ", ".join(concepts) if concepts else "暂无记录"
    system = "你是一位 AI 领域的资深分析师。用户正在学习 AI，读了一篇文章后想理解它到底意味着什么。"
    user = f"""用户已了解的概念：{concepts_str}

文章内容：
{full_text}

请从以下维度分析：
1. 这件事在 AI 领域有多重要？（从"噪音"到"里程碑"给出判断）
2. 可信度如何？（有数据支撑还是 PR 宣传？）
3. 为什么会发生？（技术、商业还是政策在推动？）
4. 长期看意味着什么？（半年后回头看）

用通俗中文回答，避免术语堆砌。若原文为英文，用中文输出分析。"""
    return system, user


def build_translation_prompt(full_text: str) -> tuple[str, str]:
    system = "你是一个专业的技术翻译助手。"
    user = f"将以下英文文章翻译为中文。保留技术术语的准确性，保持原文结构和风格。\n\n文章：{full_text}"
    return system, user


def build_concept_lookup_prompt(term: str, context: str = "") -> tuple[str, str]:
    system = "你是一个 AI 技术词典。"
    ctx = f"\n\n上下文：{context[:500]}" if context else ""
    user = f"用简短的中文解释以下 AI 相关概念。一句话定义即可。\n\n概念：{term}{ctx}"
    return system, user


def build_review_prompt(read_articles: list[dict], concepts: list[str],
                        interested_topics: list[str], not_interested_topics: list[str]) -> tuple[str, str]:
    articles_text = "\n".join(
        f"- [{a.get('title', '')}] {a.get('insight', '')}" for a in read_articles[:30]
    )
    system = "你是一个 AI 学习教练，帮助用户回顾一周的学习进展。"
    user = f"""用户本周阅读的文章：
{articles_text}

用户新学的概念：{', '.join(concepts) if concepts else '无'}
用户感兴趣的方向：{', '.join(interested_topics) if interested_topics else '暂无'}
用户不太感兴趣的方向：{', '.join(not_interested_topics) if not_interested_topics else '暂无'}

请生成一份周报：
1. 本周阅读内容的主题分类（2-3 个主题）
2. 本周最值得记住的 3 件事
3. 用户的学习进展和知识空白
4. 下周建议关注的方向

用通俗中文，像导师跟学生说话的语气。"""
    return system, user
