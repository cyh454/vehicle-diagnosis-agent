-- 数据库初始化脚本（容器首次启动时由 postgres 入口脚本自动执行）
-- 业务表由应用启动时 Base.metadata.create_all() 自动创建，这里只负责扩展。
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
