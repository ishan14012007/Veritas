-- Initialise schema boundaries for VERITAS platform
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS accord;
CREATE SCHEMA IF NOT EXISTS argus;

-- Ensure UUID and crypto extensions are available
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

