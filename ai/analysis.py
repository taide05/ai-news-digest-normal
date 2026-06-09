def build_exploration_prompt(title: str, summary: str, user_concepts: list[str]) -> tuple[str, str]:
    concepts_str = ", ".join(user_concepts[:20]) if user_concepts else "无"
    system = "你是一个信息探索助手。判断一篇文章是否值得深入探索。"
    user = (
        f"用户已了解的概念：{concepts_str}\n\n"
        f"文章标题：{title}\n"
        f"文章摘要：{summary}\n\n"
        f"这篇文章是否包含用户尚未接触过的新概念、新技术、新趋势？\n"
        f"只回答「是」或「否」。"
    )
    return system, user


def build_cluster_label_prompt(titles: str) -> tuple[str, str]:
    system = "你是一个信息分类助手。"
    user = f"为以下一组相关文章生成一个简短的中文标签（不超过15个字）：\n\n{titles}\n\n标签："
    return system, user


_EXTRACTION_ERRORS = ("[原文无法访问]", "[原文加载超时]", "[正文提取失败，请查看原网页]")

def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n（原文过长，已截断）"


def build_core_insight_prompt(full_text: str) -> tuple[str, str]:
    system = "你是一个专业的科技内容摘要助手。"
    user = f"用 2-3 句话概括下面这篇文章的核心内容。直接说重点，不要铺垫。\n\n文章：{_truncate(full_text, 6000)}"
    return system, user


def build_what_it_means_prompt(full_text: str, concepts: list[str],
                                user_topics: list[str] | None = None,
                                read_titles: list[str] | None = None) -> tuple[str, str]:
    filtered = [c for c in concepts if c and c.strip()]
    concepts_str = ", ".join(filtered[:30]) if filtered else "暂无记录"
    topics = [t for t in (user_topics or []) if t and t.strip()]
    topics_str = ", ".join(topics[:10]) if topics else "暂无记录"
    titles = read_titles or []
    total_read = len(titles)
    read_str = "\n".join(f"- {t}" for t in titles[:10]) or "暂无记录"
    if total_read > 10:
        read_str += f"\n（最近10篇，共{total_read}篇已读）"

    system = "你是一位 AI 领域的资深分析师。用户正在学习 AI，读了一篇文章后想全面理解它的含义。请用中文回答。"

    user = f"""用户已了解的概念：{concepts_str}
用户感兴趣的方向：{topics_str}
用户最近阅读的文章：
{read_str}

文章内容：
{_truncate(full_text, 4000)}

请从以下 5 个维度分析这篇文章（每段以维度标题开头）：

**1. 技术意义**
这项技术/产品/事件对AI技术栈和工程实践有什么实质影响？是渐进改进还是突破？

**2. 商业影响**
谁会受益？谁会受损？市场格局会发生什么变化？

**3. 行业趋势**
这是孤立事件还是更大趋势的信号？和最近的其他事件如何串联？

**4. 反方观点**
谁在反对或质疑这件事？反对的理由有多强？有什么局限性和风险没有被广泛讨论？

**5. 与你相关**
结合你最近读过的文章和感兴趣的方向，这篇文章对你意味着什么？是否填补了你之前的某个知识空白？

用通俗中文，避免术语堆砌。每段控制在3-5句。"""
    return system, user


def build_translation_prompt(full_text: str) -> tuple[str, str]:
    system = "你是一个专业的技术翻译助手。"
    user = f"将以下英文文章翻译为中文。保留技术术语的准确性，保持原文结构和风格。\n\n文章：{_truncate(full_text, 8000)}"
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


def build_cross_comparison_prompt(cluster_articles: list[dict]) -> tuple[str, str]:
    """Generate cross-article comparison for articles in the same cluster.
    Only uses titles + source + cached core_insight (no what_it_means dependency).
    """
    if not cluster_articles:
        raise ValueError("cluster_articles must not be empty")

    total = len(cluster_articles)
    displayed = cluster_articles[:10]

    parts = []
    for i, art in enumerate(displayed, 1):
        insight = art.get("insight", "") or "暂无观点"
        parts.append(
            f"[{i}] {art.get('title', '')}\n"
            f"    来源: {art.get('source_id', '')}\n"
            f"    核心观点: {insight[:200]}\n\n"
        )
    articles_text = "".join(parts)

    header = f"以下是关于同一话题的 {total} 篇文章"
    if total > 10:
        header += "（以下展示前10篇）"
    header += "："

    system = "你是一个信息对比分析助手。帮助用户理解同一话题下不同报道的异同。"
    user = f"""{header}

{articles_text}
请从以下角度对比这些文章：
1. **观点异同** — 各家报道的观点一致还是冲突？主要分歧在哪？
2. **事实一致性** — 关键数据和事实是否一致？有没有某家的数据明显异常？
3. **信息源质量** — 哪家更可信？谁在说事实、谁在发表观点？
4. **推荐阅读顺序** — 如果只能读 2 篇，应该读哪两篇？为什么？

用中文回答，简洁直接。"""
    return system, user


def build_concept_extraction_prompt(full_text: str) -> tuple[str, str]:
    system = "你是一个技术术语提取助手。只输出术语，不要解释。"
    user = f"""从以下文章中提取最多 5 个 AI/技术领域的关键概念术语。
只输出逗号分隔的术语列表，不要解释。
如果文章不包含值得提取的概念，输出"无"。

文章：
{_truncate(full_text, 4000)}"""
    return system, user
