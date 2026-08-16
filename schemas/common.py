from datetime import datetime

from pydantic import BaseModel, Field

# 定义 StoredRecord 模型，用于保存记录的元数据，包括模式版本、创建时间和更新时间。
class StoredRecord(BaseModel):
    schema_version: str = "1.0"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
