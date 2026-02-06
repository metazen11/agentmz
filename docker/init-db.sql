-- Database initialization script for wfhub-v2
-- This runs on first container startup when data volume is empty

-- Enable pgvector extension (if not already enabled by image)
CREATE EXTENSION IF NOT EXISTS vector;

-- Refresh collation version to prevent warnings on systems with different glibc
-- This is safe to run and handles version mismatches gracefully
DO $$
BEGIN
    EXECUTE 'ALTER DATABASE ' || current_database() || ' REFRESH COLLATION VERSION';
EXCEPTION
    WHEN OTHERS THEN
        RAISE NOTICE 'Collation refresh skipped: %', SQLERRM;
END $$;
