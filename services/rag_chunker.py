"""提供 核心领域服务和外部服务适配；本文件负责 `rag_chunker` 相关实现。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RagChunkInput:
    """封装 `RagChunkInput` 的核心数据与行为。"""

    chunk_text: str
    chunk_type: str
    metadata: dict[str, Any] = field(default_factory=dict)


class RagChunker:
    """封装 `RagChunker` 的核心数据与行为。"""

    def chunk(self, content: str, document_type: str, metadata: dict[str, Any] | None = None) -> list[RagChunkInput]:
        """根据文档类型选择规则并返回结构化知识切片。"""
        base_metadata = dict(metadata or {})
        content = content.lstrip("\ufeff")
        if document_type == "template":
            return self._chunk_template(content, base_metadata)
        if document_type == "guide":
            return self._chunk_guide(content, base_metadata)
        return self._chunk_facts(content, base_metadata)

    def _chunk_facts(self, content: str, metadata: dict[str, Any]) -> list[RagChunkInput]:
        """按段落切分事实型文档并保留最近标题。"""
        paragraphs = self._paragraphs(content)
        return [
            RagChunkInput(
                chunk_text=text,
                chunk_type="fact",
                metadata={**metadata, "heading": heading},
            )
            for heading, text in self._with_headings(paragraphs)
            if text
        ]

    def _chunk_guide(self, content: str, metadata: dict[str, Any]) -> list[RagChunkInput]:
        """按 Markdown 标题切分攻略型文档。"""
        chunks: list[RagChunkInput] = []
        current_heading = ""
        buffer: list[str] = []
        for line in content.splitlines():
            if line.startswith("#"):
                if buffer:
                    chunks.append(
                        RagChunkInput(
                            chunk_text="\n".join(buffer).strip(),
                            chunk_type="guide",
                            metadata={**metadata, "heading": current_heading},
                        )
                    )
                    buffer = []
                current_heading = line.lstrip("# ").strip()
            buffer.append(line)
        if buffer:
            chunks.append(
                RagChunkInput(
                    chunk_text="\n".join(buffer).strip(),
                    chunk_type="guide",
                    metadata={**metadata, "heading": current_heading},
                )
            )
        return [chunk for chunk in chunks if chunk.chunk_text]

    def _chunk_template(self, content: str, metadata: dict[str, Any]) -> list[RagChunkInput]:
        """按 Day 标记切分多日行程模板。"""
        chunks: list[RagChunkInput] = []
        current_day = "overview"
        buffer: list[str] = []
        for line in content.splitlines():
            match = re.match(r"\s*(?:#|\*\*)?\s*Day\s*(\d+)", line, re.IGNORECASE)
            if match:
                if buffer:
                    chunks.append(
                        RagChunkInput(
                            chunk_text="\n".join(buffer).strip(),
                            chunk_type="template",
                            metadata={**metadata, "day": current_day},
                        )
                    )
                    buffer = []
                current_day = match.group(1)
            buffer.append(line)
        if buffer:
            chunks.append(
                RagChunkInput(
                    chunk_text="\n".join(buffer).strip(),
                    chunk_type="template",
                    metadata={**metadata, "day": current_day},
                )
            )
        return [chunk for chunk in chunks if chunk.chunk_text]

    @staticmethod
    def _paragraphs(content: str) -> list[str]:
        """按空行拆分并清理非空文本段落。"""
        return [part.strip() for part in re.split(r"\n\s*\n", content) if part.strip()]

    @staticmethod
    def _with_headings(paragraphs: list[str]) -> list[tuple[str, str]]:
        """将段落与最近出现的 Markdown 标题关联。"""
        result: list[tuple[str, str]] = []
        heading = ""
        for paragraph in paragraphs:
            if paragraph.startswith("#"):
                heading = paragraph.lstrip("# ").strip()
                continue
            result.append((heading, paragraph))
        return result
