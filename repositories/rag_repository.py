"""提供 带用户隔离的数据访问；本文件负责 `rag_repository` 相关实现。"""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from db.models import RagChunk, RagDocument, RagIngestionJob, RagSource


class RagRepository:
    """封装 `RagRepository` 对应实体的数据访问和作用域隔离。"""

    def __init__(self, session: Session) -> None:
        """初始化 RagRepository 及其运行依赖。"""
        self.session = session

    def get_source(self, source_id: str) -> RagSource | None:
        """获取知识来源并返回符合当前作用域的结果。"""
        return self.session.get(RagSource, source_id)

    def get_visible_source(self, user_id: str, source_id: str) -> RagSource | None:
        """获取当前用户可见的、知识来源并返回符合当前作用域的结果。"""
        source = self.get_source(source_id)
        if source is None or source.owner_user_id not in {None, user_id}:
            return None
        return source

    def get_owned_source(self, user_id: str, source_id: str) -> RagSource | None:
        """获取当前用户拥有的、知识来源并返回符合当前作用域的结果。"""
        source = self.get_source(source_id)
        if source is None or source.owner_user_id != user_id:
            return None
        return source

    def list_sources(self, owner_user_id: str | None = None) -> list[RagSource]:
        """列出知识来源列表并返回符合当前作用域的结果。"""
        statement = select(RagSource)
        if owner_user_id is not None:
            statement = statement.where(RagSource.owner_user_id == owner_user_id)
        return list(self.session.scalars(statement.order_by(RagSource.created_at)))

    def list_visible_sources(self, user_id: str) -> list[RagSource]:
        """列出当前用户可见的、知识来源列表并返回符合当前作用域的结果。"""
        statement = select(RagSource).where(
            or_(RagSource.owner_user_id.is_(None), RagSource.owner_user_id == user_id)
        )
        return list(self.session.scalars(statement.order_by(RagSource.created_at)))

    def delete_source(self, source_id: str) -> bool:
        """删除知识来源，并保持相关状态或持久化数据一致。"""
        source = self.get_source(source_id)
        if source is None:
            return False
        self.session.delete(source)
        self.session.flush()
        return True

    def get_document(self, document_id: str) -> RagDocument | None:
        """获取文档并返回符合当前作用域的结果。"""
        return self.session.get(RagDocument, document_id)

    def get_visible_document(self, user_id: str, document_id: str) -> RagDocument | None:
        """获取当前用户可见的、文档并返回符合当前作用域的结果。"""
        document = self.get_document(document_id)
        if document is None or document.owner_user_id not in {None, user_id}:
            return None
        return document

    def get_owned_document(self, user_id: str, document_id: str) -> RagDocument | None:
        """获取当前用户拥有的、文档并返回符合当前作用域的结果。"""
        document = self.get_document(document_id)
        if document is None or document.owner_user_id != user_id:
            return None
        return document

    def list_documents(self, source_id: str) -> list[RagDocument]:
        """列出文档列表并返回符合当前作用域的结果。"""
        return list(
            self.session.scalars(
                select(RagDocument)
                .where(RagDocument.source_id == source_id)
                .order_by(RagDocument.created_at)
            )
        )

    def list_visible_documents(self, user_id: str) -> list[RagDocument]:
        """列出当前用户可见的、文档列表并返回符合当前作用域的结果。"""
        statement = select(RagDocument).where(
            or_(RagDocument.owner_user_id.is_(None), RagDocument.owner_user_id == user_id)
        )
        return list(self.session.scalars(statement.order_by(RagDocument.created_at.desc())))

    def delete_owned_document(self, user_id: str, document_id: str) -> bool:
        """删除当前用户拥有的、文档，并保持相关状态或持久化数据一致。"""
        document = self.get_owned_document(user_id, document_id)
        if document is None:
            return False
        self.session.delete(document)
        self.session.flush()
        return True

    def delete_document(self, document_id: str) -> bool:
        """删除文档，并保持相关状态或持久化数据一致。"""
        document = self.get_document(document_id)
        if document is None:
            return False
        self.session.delete(document)
        self.session.flush()
        return True

    def list_chunks(self, document_id: str) -> list[RagChunk]:
        """列出chunks并返回符合当前作用域的结果。"""
        return list(
            self.session.scalars(
                select(RagChunk)
                .where(RagChunk.document_id == document_id)
                .order_by(RagChunk.created_at)
            )
        )

    def list_jobs(self, source_id: str) -> list[RagIngestionJob]:
        """列出jobs并返回符合当前作用域的结果。"""
        return list(
            self.session.scalars(
                select(RagIngestionJob)
                .where(RagIngestionJob.source_id == source_id)
                .order_by(RagIngestionJob.started_at)
            )
        )

    def chunks_missing_embeddings(self) -> list[RagChunk]:
        """列出尚未生成向量的知识切片，用于批量回填。"""
        return list(
            self.session.scalars(
                select(RagChunk)
                .where(RagChunk.embedding.is_(None))
                .order_by(RagChunk.created_at)
            )
        )
