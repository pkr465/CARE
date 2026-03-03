-- CARE — Codebase Analysis & Repair Engine
-- Quick PGVector setup runner

psql -U postgres -d postgres -f db/pgvector_roles_and_extensions.sql
psql -U postgres -d postgres -c \
"CREATE DATABASE care_analytics_db OWNER care_analytics_user;"
psql -U postgres -d care_analytics_db -f db/schema_care_analytics.sql